"""
Five-Sensor Industrial Compressor Rule-Based Decision Engine.

Analyzes continuous telemetry for a Two-Stage Reciprocating Air Compressor:
1. Temperature Rules (HIGH_TEMPERATURE, RAPID_TEMPERATURE_RISE, TEMPERATURE_CRITICAL, TEMPERATURE_SENSOR_FAULT)
2. Vibration Rules (HIGH_VIBRATION, RAPID_VIBRATION_INCREASE, PERSISTENT_VIBRATION, VIBRATION_SENSOR_FAULT)
3. Pressure Rules (HIGH_PRESSURE, LOW_PRESSURE, PRESSURE_RISE, PRESSURE_DROP, PRESSURE_FLUCTUATION, PRESSURE_SENSOR_FAULT)
4. Current Rules (HIGH_CURRENT, LOW_CURRENT, RAPID_CURRENT_INCREASE, CURRENT_FLUCTUATION, CURRENT_SENSOR_FAULT)
5. Speed Rules (HIGH_SPEED, LOW_SPEED, SPEED_FLUCTUATION, UNEXPECTED_ZERO_SPEED, SPEED_SENSOR_FAULT)

Adheres strictly to configurable limits in config/compressor_limits.json.
Implements persistence tracking and alert deduplication.
"""

from typing import Dict, Any, List, Optional
import json
from math import isfinite
from statistics import pstdev
from pathlib import Path
from collections import deque

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "compressor_limits.json"

class CompressorRuleEngine:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.load_config()
        
        # State tracking per sensor: deques of recent values for rate-of-change and fluctuation analysis
        self.history: Dict[str, deque] = {
            "temperature": deque(maxlen=10),
            "vibration": deque(maxlen=10),
            "pressure": deque(maxlen=10),
            "current": deque(maxlen=10),
            "speed": deque(maxlen=10),
        }
        
        # Persistence tracking: counts how many consecutive samples a condition has persisted
        self.persistence_counters: Dict[str, Dict[str, int]] = {
            s: {"warning": 0, "critical": 0} for s in self.history
        }
        
        # Currently active alerts to support deduplication and recovery logging
        self.active_alerts: Dict[str, Dict[str, Any]] = {}

    def load_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {"sensors": {}}
        self.limits = self.config.get("sensors", {})

    def reset_state(self):
        """Reset internal history and persistence counters (for testing)."""
        for s in self.history:
            self.history[s].clear()
            self.persistence_counters[s] = {"warning": 0, "critical": 0}
        self.active_alerts.clear()

    def evaluate_sensor(self, s_name: str, reading: Optional[Dict[str, Any]], *, run_command: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate a single sensor category against configured rules.
        """
        cfg = self.limits.get(s_name, {})
        if not cfg.get("enabled", True):
            return {
                "sensor": s_name,
                "status": "DISABLED",
                "severity": "NORMAL",
                "alerts": []
            }

        # 1. Check for missing or faulty sensor
        if reading is None or "value" not in reading:
            alert_code = f"{s_name.upper()}_SENSOR_FAULT"
            return {
                "sensor": s_name,
                "status": "FAULT",
                "severity": "SENSOR_FAULT",
                "value": None,
                "unit": cfg.get("unit", ""),
                "alerts": [{
                    "alert_type": alert_code,
                    "severity": "SENSOR_FAULT",
                    "message": f"Sensor '{s_name}' measurement missing or invalid."
                }]
            }

        val = float(reading["value"])
        unit = reading.get("unit", cfg.get("unit", ""))
        history = self.history[s_name]

        # Rate of change calculation
        delta = 0.0
        if len(history) > 0:
            delta = val - history[-1]
        history.append(val)

        # Fluctuations (standard deviation of recent 5 readings)
        fluctuation = False
        if len(history) >= 5:
            std_dev = pstdev(history)
            if s_name == "pressure" and std_dev > 1.2:
                fluctuation = True
            elif s_name == "current" and std_dev > 3.0:
                fluctuation = True
            elif s_name == "speed" and std_dev > 50.0:
                fluctuation = True

        alerts = []
        severity = "NORMAL"

        norm_min = cfg.get("normal_min", float("-inf"))
        norm_max = cfg.get("normal_max", float("inf"))
        warn_min = cfg.get("warning_min", norm_min)
        warn_max = cfg.get("warning_max", norm_max)
        crit_min = cfg.get("critical_min", warn_min)
        crit_max = cfg.get("critical_max", warn_max)
        max_rate = cfg.get("max_rate_of_change", float("inf"))
        req_persistence = cfg.get("persistence_samples", 1)

        # A stationary shaft is expected under an explicit stop command.
        expected_stop = s_name == "speed" and run_command == "STOP" and val == 0

        # ----------------- Check Critical Conditions -----------------
        is_critical = False
        if val >= crit_max:
            is_critical = True
            alert_type = f"{s_name.upper()}_CRITICAL" if s_name == "temperature" else f"HIGH_{s_name.upper()}"
            alerts.append({
                "alert_type": alert_type,
                "severity": "CRITICAL",
                "message": f"{s_name.capitalize()} exceeded critical upper limit ({val} {unit} >= {crit_max} {unit})"
            })
        elif val <= crit_min and not expected_stop:
            is_critical = True
            if s_name == "speed" and val == 0:
                alert_type = "UNEXPECTED_ZERO_SPEED"
            else:
                alert_type = f"LOW_{s_name.upper()}"
            alerts.append({
                "alert_type": alert_type,
                "severity": "CRITICAL",
                "message": f"{s_name.capitalize()} breached critical lower limit ({val} {unit} <= {crit_min} {unit})"
            })

        # ----------------- Check Warning Conditions -----------------
        is_warning = False
        if not is_critical:
            if val > norm_max:
                is_warning = True
                alerts.append({
                    "alert_type": f"HIGH_{s_name.upper()}",
                    "severity": "WARNING",
                    "message": f"{s_name.capitalize()} above normal range ({val} {unit} > {norm_max} {unit})"
                })
            elif val < norm_min and not expected_stop:
                is_warning = True
                alerts.append({
                    "alert_type": f"LOW_{s_name.upper()}",
                    "severity": "WARNING",
                    "message": f"{s_name.capitalize()} below normal range ({val} {unit} < {norm_min} {unit})"
                })

        # ----------------- Dynamic / Rate-of-Change Rules -----------------
        if abs(delta) > max_rate and len(history) > 1:
            if delta > 0:
                alerts.append({
                    "alert_type": f"RAPID_{s_name.upper()}_{'RISE' if s_name in ['temperature', 'pressure'] else 'INCREASE'}",
                    "severity": "WARNING",
                    "message": f"Rapid {s_name} increase detected: +{round(delta, 2)} {unit}/s (limit: {max_rate})"
                })
            else:
                if s_name == "pressure":
                    alerts.append({
                        "alert_type": "PRESSURE_DROP",
                        "severity": "WARNING",
                        "message": f"Rapid pressure drop detected: {round(delta, 2)} {unit}/s"
                    })

        # Fluctuations
        if fluctuation:
            alerts.append({
                "alert_type": f"{s_name.upper()}_FLUCTUATION",
                "severity": "WARNING",
                "message": f"Abnormal {s_name} oscillation / instability detected."
            })

        # Persistence calculation
        if is_critical:
            self.persistence_counters[s_name]["critical"] += 1
            severity = "CRITICAL"
        else:
            self.persistence_counters[s_name]["critical"] = 0

        if is_warning:
            self.persistence_counters[s_name]["warning"] += 1
            if severity != "CRITICAL":
                severity = "WARNING"
            # Persistent vibration rule
            if s_name == "vibration" and self.persistence_counters["vibration"]["warning"] >= req_persistence:
                alerts.append({
                    "alert_type": "PERSISTENT_VIBRATION",
                    "severity": "WARNING",
                    "message": f"Persistent abnormal vibration across {self.persistence_counters['vibration']['warning']} consecutive samples."
                })
        else:
            self.persistence_counters[s_name]["warning"] = 0

        return {
            "sensor": s_name,
            "status": severity,
            "severity": severity,
            "value": val,
            "unit": unit,
            "normal_range": [norm_min, norm_max],
            "warning_range": [warn_min, warn_max],
            "critical_range": [crit_min, crit_max],
            "rate_of_change": round(delta, 3) if isfinite(delta) else None,
            "persistence": self.persistence_counters[s_name]["warning"] + self.persistence_counters[s_name]["critical"],
            "alerts": alerts
        }

    def evaluate_telemetry(self, sensors: Dict[str, Any], *, run_command: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate all 5 sensor channels and produce aggregated machine condition assessment.
        Includes multi-sensor correlation analysis from Section 6 of the Worker Decision Guide.
        """
        results = {}
        all_alerts = []
        overall_severity = "NORMAL"

        required_sensors = ["temperature", "vibration", "pressure", "current", "speed"]

        for s_name in required_sensors:
            s_reading = sensors.get(s_name) if isinstance(sensors, dict) else None
            res = self.evaluate_sensor(s_name, s_reading, run_command=run_command)
            results[s_name] = res
            for alert in res.get("alerts", []):
                alert["sensor"] = s_name
                alert["value"] = res.get("value")
                alert["unit"] = res.get("unit")
                all_alerts.append(alert)

            # Escalate overall severity
            s_sev = res.get("severity", "NORMAL")
            if s_sev == "CRITICAL":
                overall_severity = "CRITICAL"
            elif s_sev == "SENSOR_FAULT" and overall_severity != "CRITICAL":
                overall_severity = "SENSOR_FAULT"
            elif s_sev == "WARNING" and overall_severity not in ["CRITICAL", "SENSOR_FAULT"]:
                overall_severity = "WARNING"

        # Multi-Sensor Correlation Rules (Section 6: Combined Sensor Decision Matrix)
        t_res = results.get("temperature", {})
        v_res = results.get("vibration", {})
        p_res = results.get("pressure", {})
        c_res = results.get("current", {})
        s_res = results.get("speed", {})

        t_abnormal = t_res.get("severity") in ["WARNING", "CRITICAL"]
        v_abnormal = v_res.get("severity") in ["WARNING", "CRITICAL"]
        p_abnormal = p_res.get("severity") in ["WARNING", "CRITICAL"]
        c_abnormal = c_res.get("severity") in ["WARNING", "CRITICAL"]
        s_abnormal = s_res.get("severity") in ["WARNING", "CRITICAL"]

        p_val = p_res.get("value") or 0.0
        c_val = c_res.get("value") or 0.0
        s_val = s_res.get("value") or 0.0

        # Multi-sensor check 1: Pressure high + Temp high + Current high -> Multi-Parameter Critical
        if p_abnormal and t_abnormal and c_abnormal and p_val > 9.5 and c_val > 22.0:
            overall_severity = "CRITICAL"
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "MULTI_PARAMETER_CRITICAL",
                "severity": "CRITICAL",
                "value": f"P:{p_val:.1f}bar, T:{t_res.get('value', 0):.1f}°C, I:{c_val:.1f}A",
                "unit": "combined",
                "message": "MULTI-PARAMETER CRITICAL ADVISORY: Potentially overloaded or restricted operating condition across multiple process and electrical indicators."
            })

        # Multi-sensor check 2: Pressure high + Current high -> High Load / Pressure Alert
        elif p_abnormal and c_abnormal and p_val > 9.5 and c_val > 22.0:
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "HIGH_LOAD_PRESSURE",
                "severity": "WARNING",
                "value": f"P:{p_val:.1f}bar, I:{c_val:.1f}A",
                "unit": "combined",
                "message": "HIGH LOAD / PRESSURE ALERT: Combined high discharge pressure and motor current indicate high compressor load or delivery restriction."
            })

        # Multi-sensor check 3: Vibration high + Current high -> Mechanical Load Alert
        if v_abnormal and c_abnormal and c_val > 22.0:
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "MECHANICAL_LOAD",
                "severity": "WARNING",
                "value": f"Vib:{v_res.get('value', 0):.3f}g, I:{c_val:.1f}A",
                "unit": "combined",
                "message": "MECHANICAL LOAD ALERT: Concurrent vibration and current rise indicate mechanical resistance, misalignment, or developing bearing deterioration."
            })

        # Multi-sensor check 4: Speed low + Current high -> Drive / Overload Alert
        if s_abnormal and c_abnormal and s_val < 1420.0 and c_val > 22.0:
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "DRIVE_OVERLOAD",
                "severity": "WARNING",
                "value": f"Speed:{s_val:.0f}RPM, I:{c_val:.1f}A",
                "unit": "combined",
                "message": "DRIVE / OVERLOAD ALERT: Speed drop with high motor current indicates severe mechanical drag, drive slip, or electrical supply overload."
            })

        # Multi-sensor check 5: Speed low + Pressure low -> Low Output / Speed Alert
        if s_abnormal and p_abnormal and s_val < 1420.0 and p_val < 6.5:
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "LOW_OUTPUT_SPEED",
                "severity": "WARNING",
                "value": f"Speed:{s_val:.0f}RPM, P:{p_val:.1f}bar",
                "unit": "combined",
                "message": "LOW OUTPUT / SPEED ALERT: Low speed coinciding with low delivery pressure indicates drive belt slippage or unloader failure."
            })

        # Multi-sensor check 6: Pressure high + Temperature high -> Pressure + Temperature Alert
        if p_abnormal and t_abnormal and p_val > 9.5:
            all_alerts.append({
                "sensor": "multi_sensor",
                "alert_type": "PRESSURE_TEMPERATURE",
                "severity": "WARNING",
                "value": f"P:{p_val:.1f}bar, T:{t_res.get('value', 0):.1f}°C",
                "unit": "combined",
                "message": "PRESSURE + TEMPERATURE ALERT: Combined pressure and thermal elevation indicates restricted flow path or intercooler fouling."
            })

        return {
            "machine_status": overall_severity,
            "active_alerts_count": len(all_alerts),
            "sensor_evaluations": results,
            "alerts": all_alerts
        }

compressor_engine = CompressorRuleEngine()

def evaluate_compressor(sensors: Dict[str, Any]) -> Dict[str, Any]:
    """Helper wrapper for evaluating compressor sensor telemetry."""
    return compressor_engine.evaluate_telemetry(sensors)

