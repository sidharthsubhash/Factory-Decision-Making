"""
Actionable Worker Recommendation Engine for Two-Stage Reciprocating Air Compressor.
Directly implements:
- Worker Action & Machine Decision Guide (Two_Stage_Reciprocating_Compressor_Worker_Decision_Guide.docx)
- Section 4 Severity Model (NORMAL, WARNING, CRITICAL ADVISORY, SENSOR/DATA FAULT, PROTECTIVE TRIP)
- Section 5 Individual Sensor Decision Tables
- Section 6 Combined Sensor Decision Matrix
- Section 8 Recommended Dashboard Alert Format
- Section 9 Operator Response Workflow (RECEIVE -> VERIFY -> REVIEW -> ACT -> ESCALATE -> ACKNOWLEDGE -> CLOSE)

Advisory-First Principle:
This application detects abnormal measurements and suggests checks; it does not prove a
particular component has failed. It must not automatically stop, start, unload, change speed,
or actuate equipment. Existing OEM controls and site procedures remain authoritative.
"""

from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timezone

# Structured Knowledge Base matching Section 5 & Section 6 of Worker Decision Guide
RECOMMENDATION_MATRIX: Dict[str, Dict[str, Dict[str, Any]]] = {
    "temperature": {
        "HIGH_TEMPERATURE": {
            "title": "INTERCOOLER TEMPERATURE WARNING",
            "possible_causes": [
                "Reduced cooling efficiency or high compressor load",
                "Fouled or blocked intercooler radiator tubes",
                "Inadequate cooling medium / fan air flow restriction",
                "Discharge valve leakage / blow-by causing re-compression",
                "Sensor placement or thermal contact resistance"
            ],
            "worker_actions": [
                "Verify the temperature reading with a handheld calibrated infrared pyrometer.",
                "Check cooling fan operation, cooler inlet/outlet air paths, and louvers for dust fouling.",
                "Inspect intercooler condensate drain trap for blockages.",
                "Compare with OEM intercooler temperature limit (nominal: 60–95 °C).",
                "Notify plant maintenance personnel if temperature remains above warning limit for > 5 minutes."
            ],
            "maintenance_followup": "Schedule inspection of stage 1 and stage 2 discharge reed valves and clean intercooler tubes.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "RAPID_TEMPERATURE_RISE": {
            "title": "TEMPERATURE RISE ALERT",
            "possible_causes": [
                "Cooling performance deteriorating or sudden loss of cooling medium circulation",
                "Severe discharge valve breakage or unseated valve plate",
                "Abnormal stage compression ratio or high mechanical friction",
                "Sudden compressor load change"
            ],
            "worker_actions": [
                "Check temperature trend and current compressor operating load.",
                "Inspect intercooler and cooling fan supply immediately.",
                "Listen for localized valve hissing or cylinder head knocking.",
                "Confirm the reading with an approved independent instrument."
            ],
            "maintenance_followup": "Urgent mechanical inspection of cylinder lubrication feed and discharge valves.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "TEMPERATURE_CRITICAL": {
            "title": "CRITICAL TEMPERATURE ADVISORY",
            "possible_causes": [
                "Extreme thermal runaway or complete intercooler cooling failure",
                "High risk of lubricating oil flashover or thermal breakdown",
                "Severe stage 2 re-compression"
            ],
            "worker_actions": [
                "Notify the responsible operator immediately.",
                "Follow the manufacturer's alarm and controlled shutdown procedure.",
                "Do not wait for AI/ML model if an OEM safety trip or alarm is active.",
                "Prepare standby air compressor if plant air header pressure must be sustained."
            ],
            "maintenance_followup": "Mandatory teardown, valve chamber inspection, and crankcase oil change before restart.",
            "machine_decision": "CRITICAL ADVISORY – immediate operator escalation required. Follow OEM site emergency procedure."
        },
        "TEMPERATURE_SENSOR_FAULT": {
            "title": "TEMPERATURE SENSOR FAULT",
            "possible_causes": [
                "Open circuit, wiring disconnection, or faulty thermocouple/RTD lead",
                "Transmitter hardware error or channel disconnected"
            ],
            "worker_actions": [
                "Do not use this channel for a normal/critical decision.",
                "Mark temperature channel unavailable in monitoring log.",
                "Verify sensor wiring terminal box and inspect for physical cable damage.",
                "Use an approved handheld pyrometer for manual periodic verification."
            ],
            "maintenance_followup": "Test sensor resistance with multimeter and replace thermocouple probe if defective.",
            "machine_decision": "SENSOR FAULT – instrument inspection required. Machine remains under independent OEM protection."
        }
    },
    "vibration": {
        "HIGH_VIBRATION": {
            "title": "CRANKCASE VIBRATION WARNING",
            "possible_causes": [
                "Loose foundation mounting bolts or anchor fastener slack",
                "Belt drive or motor-to-crankshaft coupling misalignment",
                "Dynamic mechanical unbalance in flywheel or reciprocating piston assembly",
                "Early-stage bearing track deterioration or clearance degradation"
            ],
            "worker_actions": [
                "Confirm the vibration sensor is firmly mounted and the reading is repeatable.",
                "Inspect foundation mounting bolts and hold-down hardware for looseness.",
                "Inspect V-belt drive condition, tension, and alignment under safe inspection procedure.",
                "Listen for localized metallic clicking in crankshaft bearing housings.",
                "Do not identify a failed bearing from RMS alone; schedule vibration spectrum / FFT analysis."
            ],
            "maintenance_followup": "Schedule vibration spectrum / FFT analysis to distinguish mechanical unbalance from bearing race frequencies.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "RAPID_VIBRATION_INCREASE": {
            "title": "VIBRATION SIGNAL CHANGE ALERT",
            "possible_causes": [
                "Sudden mechanical component looseness or broken valve plate fragment in cylinder",
                "Drive belt delamination, belt whip, or flywheel keyway slipping",
                "Local sensor movement or loose mounting stud"
            ],
            "worker_actions": [
                "Stand clear of rotating drive elements and observe machine stability.",
                "Check if vibration increases with pressure loading.",
                "Check sensor mounting stud and accelerometer cable for physical damage.",
                "Compare with a second handheld vibration measurement before diagnosing machine fault."
            ],
            "maintenance_followup": "Immediate inspection of valve chamber, flywheel assembly, and motor mountings.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "PERSISTENT_VIBRATION": {
            "title": "PERSISTENT VIBRATION WARNING",
            "possible_causes": [
                "Sustained structural resonance or foundation degradation",
                "Progressive bearing wear or clearance deterioration",
                "Chronic pulley or shaft misalignment"
            ],
            "worker_actions": [
                "Review vibration trend history over the last operating shifts.",
                "Check bearing housing temperature using infrared pyrometer.",
                "Log persistent vibration in maintenance logbook.",
                "Escalate to mechanical maintenance supervisor for scheduled overhaul."
            ],
            "maintenance_followup": "Perform full alignment check and bearing clearance measurement.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "VIBRATION_CRITICAL": {
            "title": "CRITICAL VIBRATION ADVISORY",
            "possible_causes": [
                "Severe mechanical loose assembly, impending bearing seizure, or structural crack",
                "Broken crankshaft counterweight or loose flywheel"
            ],
            "worker_actions": [
                "Notify operator immediately and follow OEM/site procedure for controlled shutdown.",
                "Keep clear of rotating parts; NEVER remove guards while running.",
                "Do not restart until mechanical maintenance completes visual and torque checks."
            ],
            "maintenance_followup": "Complete mechanical teardown of reciprocating assembly and bearing inspection.",
            "machine_decision": "CRITICAL ADVISORY – immediate operator escalation required. Follow OEM emergency procedure."
        },
        "VIBRATION_SENSOR_FAULT": {
            "title": "VIBRATION SENSOR FAULT",
            "possible_causes": [
                "Accelerometer cable disconnect, BNC connector loose, or sensor detachment",
                "Transmitter bias voltage out of specification"
            ],
            "worker_actions": [
                "Verify accelerometer mounting stud and cable integrity.",
                "Check 4-20mA loop / IEPE signal conditioner power.",
                "Do not assume machine is healthy when vibration channel is unavailable."
            ],
            "maintenance_followup": "Calibrate or replace vibration transmitter probe.",
            "machine_decision": "SENSOR FAULT – instrument inspection required."
        }
    },
    "pressure": {
        "HIGH_PRESSURE": {
            "title": "HIGH DISCHARGE PRESSURE WARNING",
            "possible_causes": [
                "Downstream distribution line isolation valve closed or header pipe restriction",
                "Pressure regulator / unloader pilot valve stuck in loaded position",
                "Demand/load mismatch with receiver capacity",
                "Pressure transmitter calibration drift"
            ],
            "worker_actions": [
                "Verify the pressure gauge reading on local analog dial at receiver tank.",
                "Check downstream plant air header discharge isolation valve position.",
                "Confirm pressure-control and pressure-relief devices are available and unobstructed.",
                "NEVER isolate, plug, or obstruct a pressure-relief safety valve."
            ],
            "maintenance_followup": "Test unloader valve pilot operation and verify safety relief valve certification tag.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "LOW_PRESSURE": {
            "title": "LOW DISCHARGE PRESSURE WARNING",
            "possible_causes": [
                "Excessive downstream plant air demand or major pipeline distribution leak",
                "Inlet air filter heavily clogged / intake air starved",
                "Intake unloader stuck open (compressor running continuously unloaded)",
                "Broken or leaking suction/discharge reed valves in LP or HP cylinder"
            ],
            "worker_actions": [
                "Verify delivery pressure against plant demand schedule.",
                "Inspect accessible distribution piping joints for air leakage using ultrasonic leak detector.",
                "Check intake air filter differential pressure indicator.",
                "Request maintenance personnel check compressor intake unloader and valve plates."
            ],
            "maintenance_followup": "Inspect and overhaul compressor cylinder valves and replace worn piston rings.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "PRESSURE_FLUCTUATION": {
            "title": "PRESSURE FLUCTUATION ALERT",
            "possible_causes": [
                "Unstable plant demand or hunting in electronic/pneumatic pressure switch",
                "Broken valve plate on one cylinder causing uneven stroke compression",
                "Receiver tank check valve chatter or condensate drain stuck open"
            ],
            "worker_actions": [
                "Review pressure trend and compressor cycling frequency.",
                "Verify local transmitter and analog dial gauge reading.",
                "Inspect unloader pilot mechanism and receiver check valve for rapid chattering."
            ],
            "maintenance_followup": "Inspect pilot control valves and receiver check valve internal disc.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "PRESSURE_CRITICAL": {
            "title": "CRITICAL PRESSURE ADVISORY",
            "possible_causes": [
                "Dangerous overpressure condition exceeding receiver or pipework rating",
                "Unloader failure combined with safety relief valve failure to lift"
            ],
            "worker_actions": [
                "Immediately notify operator and follow site pressure-system emergency procedure.",
                "Verify receiver tank safety relief valve status.",
                "Initiate controlled emergency shutdown per OEM safety protocol.",
                "Existing pressure-relief systems must remain active; do NOT manually adjust relief valves."
            ],
            "maintenance_followup": "Mandatory formal re-inspection and recertification of pressure system and relief valves.",
            "machine_decision": "CRITICAL ADVISORY – immediate operator escalation required. Follow pressure emergency procedure."
        },
        "PRESSURE_SENSOR_FAULT": {
            "title": "PRESSURE SENSOR FAULT",
            "possible_causes": [
                "Pressure transmitter diaphragm plugged with oil sludge / moisture",
                "Loop wiring open circuit or supply voltage failure"
            ],
            "worker_actions": [
                "Immediately check local mechanical Bourdon tube pressure gauge on receiver tank.",
                "Verify 4-20mA transmitter loop power.",
                "Do not make pressure decisions solely on a faulted transmitter."
            ],
            "maintenance_followup": "Clean pressure impulse tube, purge condensate, and calibrate transmitter.",
            "machine_decision": "SENSOR FAULT – check local analog gauge immediately."
        }
    },
    "current": {
        "HIGH_CURRENT": {
            "title": "HIGH MOTOR CURRENT WARNING",
            "possible_causes": [
                "Compressor driving against excessive discharge head pressure",
                "Mechanical binding / piston tightness in cylinder bore",
                "Electrical supply voltage sag causing proportional 3-phase current rise",
                "High lubricating oil viscosity or cold oil startup drag"
            ],
            "worker_actions": [
                "Verify 3-phase current readings at the motor control center (MCC).",
                "Check line voltage with qualified electrical staff to verify balanced 3-phase supply.",
                "Check compressor discharge pressure gauge (high pressure causes high current).",
                "Inspect crankcase oil level, oil pressure, and motor surface temperature."
            ],
            "maintenance_followup": "Request qualified electrician test motor insulation resistance (megger) and overload relay trip setpoint.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "LOW_CURRENT": {
            "title": "LOW MOTOR CURRENT WARNING",
            "possible_causes": [
                "Compressor operating permanently unloaded (intake unloader stuck open)",
                "Broken V-belt drive causing motor to spin with zero mechanical compression load",
                "Severe loss of compression due to broken intake valves"
            ],
            "worker_actions": [
                "Check drive belts through guard to verify compressor crankshaft is actually turning.",
                "Check whether compressor is building pressure or cycling continuously unloaded.",
                "Have qualified electrical technician verify electrical phase connections."
            ],
            "maintenance_followup": "Inspect unloader solenoid mechanism and inspect V-belt drive integrity.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "CURRENT_FLUCTUATION": {
            "title": "CURRENT FLUCTUATION ALERT",
            "possible_causes": [
                "Phase voltage imbalance or loose motor power terminal connection",
                "Cyclic load variation caused by broken compressor valve on one cylinder",
                "Compressor unloader hunting rapidly between loaded and unloaded states"
            ],
            "worker_actions": [
                "Listen for rhythmic motor humming or uneven stroke loading sound.",
                "Check motor terminal enclosure for abnormal warmth (DO NOT open live enclosure).",
                "Request qualified electrical personnel measure individual 3-phase currents."
            ],
            "maintenance_followup": "Inspect motor contactor contacts, terminal lugs, and check cylinder compression balance.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "CURRENT_CRITICAL": {
            "title": "CRITICAL CURRENT ADVISORY",
            "possible_causes": [
                "Severe electrical overload or mechanical lockup / impending motor stall",
                "Single-phasing condition with motor drawing locked-rotor current"
            ],
            "worker_actions": [
                "Notify operator immediately; motor thermal overload protection may trip soon.",
                "Inspect compressor immediately for burning electrical or rubber odors.",
                "Follow site electrical overload response procedure."
            ],
            "maintenance_followup": "Perform electrical insulation test and mechanical rotation check by hand under lockout/tagout.",
            "machine_decision": "CRITICAL ADVISORY – electrical overload escalation required."
        },
        "CURRENT_SENSOR_FAULT": {
            "title": "CURRENT SENSOR FAULT",
            "possible_causes": [
                "Current transformer (CT) open circuit or burden resistor fault",
                "Analog current transducer wiring disconnected"
            ],
            "worker_actions": [
                "Verify motor run indicator light on MCC panel.",
                "Inspect CT secondary wiring harness for loose terminal block screws."
            ],
            "maintenance_followup": "Inspect CT wiring harness and calibrate current transmitter.",
            "machine_decision": "SENSOR FAULT – verify motor status locally at MCC."
        }
    },
    "speed": {
        "HIGH_SPEED": {
            "title": "HIGH SHAFT SPEED WARNING",
            "possible_causes": [
                "VFD / Inverter speed reference setpoint incorrect (overspeed condition)",
                "Incorrect motor pulley installed on drive shaft",
                "Tachometer sensor scaling or frequency-to-voltage calibration error"
            ],
            "worker_actions": [
                "Verify shaft RPM using a handheld non-contact optical tachometer.",
                "Check VFD speed reference setpoint on drive display.",
                "Follow OEM procedure: avoid continuous overspeed to prevent inertial fatigue on reciprocating parts."
            ],
            "maintenance_followup": "Inspect VFD frequency output and speed control parameter configuration.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "LOW_SPEED": {
            "title": "LOW SHAFT SPEED WARNING",
            "possible_causes": [
                "V-belt slippage due to belt wear, slack, or oil contamination on pulleys",
                "Severe motor overload or low grid supply frequency",
                "Severe mechanical drag in cylinder or main crankshaft bearings"
            ],
            "worker_actions": [
                "Verify RPM with handheld optical tachometer on crankshaft.",
                "Inspect V-belt drive for signs of slipping, burning rubber odor, or loose tension (under safe isolation).",
                "Check motor temperature and current loading.",
                "Confirm whether reading represents motor speed or crankshaft speed."
            ],
            "maintenance_followup": "Clean pulley grooves, re-tension or replace V-belt matched set.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "SPEED_FLUCTUATION": {
            "title": "SPEED FLUCTUATION ALERT",
            "possible_causes": [
                "Variable belt slip or pulley wobbling",
                "Unstable motor drive / VFD hunting",
                "Intermittent optical or proximity speed sensor triggering"
            ],
            "worker_actions": [
                "Inspect speed pickup sensor gap and alignment with target gear/keyway.",
                "Observe belt drive visually under running conditions (clear of rotating parts).",
                "Check VFD output stability on drive display."
            ],
            "maintenance_followup": "Clean speed pickup sensor face, check target wheel runout, and check V-belt tension.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "UNEXPECTED_ZERO_SPEED": {
            "title": "ZERO SPEED / SENSOR CHECK",
            "possible_causes": [
                "Machine stopped unexpectedly or breaker tripped",
                "Speed sensor disconnected, wiring fault, or loss of sensor target alignment",
                "Broken drive belt or sheared coupling key"
            ],
            "worker_actions": [
                "Confirm actual physical machine operating state independently.",
                "If compressor is visibly running, inspect speed sensor and pickup wiring immediately.",
                "Do NOT infer a machine stop from one failed sensor alone."
            ],
            "maintenance_followup": "Inspect speed sensor bracket rigidity, cable continuity, and drive belts.",
            "machine_decision": "SENSOR / ZERO CHECK – confirm machine physical state independently."
        },
        "SPEED_SENSOR_FAULT": {
            "title": "SPEED SENSOR FAULT",
            "possible_causes": [
                "Proximity sensor / tachometer signal loss or damaged cable",
                "Pulse counter module configuration error"
            ],
            "worker_actions": [
                "Verify sensor LED indicator pulses as shaft rotates.",
                "Inspect sensor connector and cable routing away from high-voltage motor leads."
            ],
            "maintenance_followup": "Test sensor pulse output with handheld oscilloscope / multimeter.",
            "machine_decision": "SENSOR FAULT – verify shaft rotation physically."
        }
    },
    # Section 6: Combined Sensor Decision Matrix
    "multi_sensor": {
        "MULTI_PARAMETER_CRITICAL": {
            "title": "MULTI-PARAMETER CRITICAL ADVISORY",
            "possible_causes": [
                "Compressor operating under severe combined thermal, pressure, and electrical overload",
                "Restricted discharge path combined with intercooler failure and excessive drive loading",
                "Impending catastrophic mechanical damage if sustained"
            ],
            "worker_actions": [
                "Notify operator and plant supervisor immediately.",
                "Verify receiver tank pressure, cylinder temperature, and motor current locally.",
                "Follow OEM/site emergency operating procedure; prepare for controlled unloading and shutdown.",
                "Confirm certified pressure-relief valves and electrical trip devices are active."
            ],
            "maintenance_followup": "Mandatory full system overhaul, safety relief inspection, and motor electrical diagnostic.",
            "machine_decision": "CRITICAL ADVISORY – immediate operator escalation required. Follow site emergency procedure."
        },
        "HIGH_LOAD_PRESSURE": {
            "title": "HIGH LOAD / PRESSURE ALERT",
            "possible_causes": [
                "Downstream distribution restriction combined with high motor load",
                "Pressure unloader failing to open while machine operates against maximum receiver pressure",
                "Compressor delivery capacity exceeding plant consumption rate"
            ],
            "worker_actions": [
                "Verify both discharge pressure and motor current on plant instruments.",
                "Check downstream discharge flow path and receiver isolation valves.",
                "Check unloader pilot valve mechanism and pressure regulator.",
                "Have electrical and maintenance staff investigate drive motor loading."
            ],
            "maintenance_followup": "Test unloader pilot valve calibration and inspect motor current draw under load.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "MECHANICAL_LOAD": {
            "title": "MECHANICAL LOAD ALERT",
            "possible_causes": [
                "Increased internal mechanical resistance in crankshaft, connecting rods, or pistons",
                "Motor-to-compressor drive misalignment causing excessive bearing side loads",
                "Early-stage bearing raceway spalling causing simultaneous friction and vibration rise"
            ],
            "worker_actions": [
                "Verify vibration and motor current readings across operating cycle.",
                "Check crankcase and bearing housing temperatures using infrared pyrometer.",
                "Inspect foundation mounting bolts and coupling/belt alignment under safe isolation.",
                "Arrange maintenance inspection of main bearings and connecting rod assemblies."
            ],
            "maintenance_followup": "Schedule vibration FFT spectrum analysis and check crankcase oil for metallic wear debris.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "DRIVE_OVERLOAD": {
            "title": "DRIVE / OVERLOAD ALERT",
            "possible_causes": [
                "Severe V-belt slippage under high torque load",
                "Severe mechanical binding in compression cylinders or crankshaft",
                "Low electrical supply line voltage causing induction motor slip and current surge"
            ],
            "worker_actions": [
                "Verify rotational speed and motor current.",
                "Inspect V-belt drive through guard for slack, smoking, or burning rubber odor.",
                "Request qualified electrical personnel check supply voltage and motor protection.",
                "Follow approved site motor overload response procedure."
            ],
            "maintenance_followup": "Re-tension or replace V-belt set; inspect motor terminal connections.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "LOW_OUTPUT_SPEED": {
            "title": "LOW OUTPUT / SPEED ALERT",
            "possible_causes": [
                "Severe V-belt slippage leading to low compressor RPM and inadequate compression",
                "Intake unloader stuck open while drive speed is compromised",
                "Severe plant distribution piping rupture or open blow-down valve"
            ],
            "worker_actions": [
                "Verify crankshaft RPM and discharge pressure.",
                "Check drive belt tension and condition under safe procedure.",
                "Inspect receiver tank drains and plant header piping for open valves or leaks.",
                "Check compressor intake unloader mechanism."
            ],
            "maintenance_followup": "Inspect compressor cylinder valves and re-tension drive belts.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "ROTATING_EQUIPMENT": {
            "title": "ROTATING EQUIPMENT ALERT",
            "possible_causes": [
                "Drive train instability, loose flywheel keyway, or severe belt flap",
                "Dynamic unbalance in rotating assembly coupled with speed hunting",
                "Loose vibration or speed sensor mounting bracket"
            ],
            "worker_actions": [
                "Verify both vibration and speed channels.",
                "Inspect sensor mounting studs and sensor brackets for looseness.",
                "Inspect flywheel, pulleys, and belt tension under lockout/tagout procedure."
            ],
            "maintenance_followup": "Perform mechanical runout and dynamic balance inspection on compressor flywheel.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        },
        "PRESSURE_TEMPERATURE": {
            "title": "PRESSURE + TEMPERATURE ALERT",
            "possible_causes": [
                "Compressor operating against high head pressure with restricted interstage cooling",
                "High ambient temperature combined with intercooler radiator tube dust clogging",
                "HP stage discharge valve leakage causing re-compression of already compressed air"
            ],
            "worker_actions": [
                "Verify both temperature and pressure readings.",
                "Check cooling fan operation and inspect intercooler exterior for fouling.",
                "Inspect discharge line and receiver tank valves.",
                "Escalate if either parameter approaches approved OEM critical trip limits."
            ],
            "maintenance_followup": "Clean intercooler heat exchanger and inspect HP discharge reed valve plates.",
            "machine_decision": "WARNING – operator review required. No automatic control action."
        }
    }
}

# Sensor category mapping and unit formatting
SENSOR_DISPLAY_NAMES = {
    "temperature": "Intercooler temperature",
    "vibration": "Crankcase vibration",
    "pressure": "Discharge pressure",
    "current": "Drive motor current",
    "speed": "Shaft speed",
    "multi_sensor": "Multi-Sensor Correlation"
}

REFERENCE_BASELINES = {
    "temperature": "Baseline: 78.5 °C | OEM Normal: 60.0–95.0 °C | Warning: > 95.0 °C | Critical: > 105.0 °C",
    "vibration": "Baseline: 0.180 g RMS | OEM Normal: 0.05–0.30 g | Warning: > 0.30 g | Critical: > 0.45 g",
    "pressure": "Baseline: 8.00 bar | OEM Normal: 6.5–9.5 bar | Warning: > 9.5 bar | Critical: > 10.5 bar",
    "current": "Baseline: 18.0 A | OEM Normal: 14.0–22.0 A | Warning: > 22.0 A | Critical: > 26.0 A",
    "speed": "Baseline: 1450 RPM | OEM Normal: 1420–1480 RPM | Warning: < 1420 / > 1480 RPM | Critical: < 1350 / > 1520 RPM",
    "multi_sensor": "OEM Combined Operating Envelope (Thermal, Pressure & Electrical limits)"
}


class RecommendationEngine:
    """
    Actionable Worker Recommendation Generator implementing Section 8 of the Decision Guide.
    """

    def build_recommendation(
        self,
        alert_type: str,
        sensor_name: str,
        measured_value: Any,
        unit: str,
        normal_range: List[float],
        severity: str,
        machine_id: str = "COMPRESSOR_01",
        timestamp: Optional[str] = None,
        evidence: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build an alert record compliant with Section 8 of the Decision Guide.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        prefix = sensor_name[:3].upper() if sensor_name != "multi_sensor" else "COR"
        alert_id = f"ALT-{prefix}-{uuid.uuid4().hex[:6].upper()}"

        sensor_matrix = RECOMMENDATION_MATRIX.get(sensor_name, {})
        data = sensor_matrix.get(alert_type, {})

        display_name = SENSOR_DISPLAY_NAMES.get(sensor_name, sensor_name)
        ref_baseline = REFERENCE_BASELINES.get(sensor_name, f"Normal: {normal_range} {unit}")
        alert_title = data.get("title", f"{display_name.upper()} ALERT ({alert_type.replace('_', ' ')})")

        # Fallback defaults if exact alert type is unmapped
        default_causes = [
            f"Observed measurement of {measured_value} {unit} is outside configured operating baseline",
            "Developing process, electrical, or mechanical anomaly",
            "Instrument calibration drift or sensor mounting issue"
        ]
        default_actions = [
            f"Verify the {display_name} locally using calibrated plant instrumentation.",
            f"Inspect the compressor {display_name} area under site safe procedures.",
            "Compare reading with approved OEM manual limits before diagnosing machine fault.",
            "Notify plant maintenance personnel if the condition persists."
        ]
        default_maint = "Log condition in plant maintenance management system for follow-up review."
        default_decision = f"{severity} – operator review required. No automatic control action."

        possible_causes = data.get("possible_causes", default_causes)
        worker_actions = data.get("worker_actions", default_actions)
        maintenance_followup = data.get("maintenance_followup", default_maint)
        machine_decision = data.get("machine_decision", default_decision)

        # Build evidence string
        if not evidence:
            evidence = f"Reading: {measured_value} {unit}. Evaluated against {ref_baseline}."

        return {
            "alert_id": alert_id,
            "timestamp": ts,
            "machine": "Two-Stage Industrial Reciprocating Air Compressor",
            "machine_id": machine_id,
            "sensor": display_name,
            "sensor_key": sensor_name,
            "alert_type": alert_type,
            "alert_title": alert_title,
            "measured_value": measured_value,
            "unit": unit,
            "normal_range": normal_range,
            "reference": ref_baseline,
            "evidence": evidence,
            "severity": "CRITICAL ADVISORY" if severity == "CRITICAL" else severity,
            "possible_causes": possible_causes,
            "recommended_worker_actions": worker_actions,
            "machine_decision": machine_decision,
            "maintenance_followup": maintenance_followup,
            "workflow_stage": "RECEIVE -> VERIFY -> REVIEW -> ACT",
            "acknowledged": False,
            "acknowledged_by": None,
            "acknowledged_at": None
        }

    def process_evaluations(
        self,
        rule_evaluations: Dict[str, Any],
        machine_id: str = "COMPRESSOR_01",
        timestamp: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process the output from the compressor rule engine and generate recommendations for all alerts.
        """
        recommendations = []
        sensor_evals = rule_evaluations.get("sensor_evaluations", {})
        raw_alerts = rule_evaluations.get("alerts", [])

        # Process individual sensor alerts
        for s_name, eval_data in sensor_evals.items():
            alerts = eval_data.get("alerts", [])
            val = eval_data.get("value")
            unit = eval_data.get("unit", "")
            norm_range = eval_data.get("normal_range", [])
            rate = eval_data.get("rate_of_change", 0.0)
            rate_description = f"{rate:+.2f} {unit}/sample" if rate is not None else "outside numeric precision"
            persistence = eval_data.get("persistence", 0)

            for alert in alerts:
                a_type = alert.get("alert_type", "GENERIC_ALERT")
                a_sev = alert.get("severity", "WARNING")
                evidence_str = (
                    f"Measured value: {val} {unit}. "
                    f"Rate of change: {rate_description}. "
                    f"Persistence: {persistence} consecutive sample(s)."
                )

                rec = self.build_recommendation(
                    alert_type=a_type,
                    sensor_name=s_name,
                    measured_value=val,
                    unit=unit,
                    normal_range=norm_range,
                    severity=a_sev,
                    machine_id=machine_id,
                    timestamp=timestamp,
                    evidence=evidence_str
                )
                recommendations.append(rec)

        # Process multi-sensor combined alerts (Section 6)
        multi_alerts = [a for a in raw_alerts if a.get("sensor") == "multi_sensor"]
        for m_alert in multi_alerts:
            a_type = m_alert.get("alert_type", "MULTI_SENSOR_ALERT")
            a_sev = m_alert.get("severity", "WARNING")
            val_str = m_alert.get("value", "")
            msg = m_alert.get("message", "")

            rec = self.build_recommendation(
                alert_type=a_type,
                sensor_name="multi_sensor",
                measured_value=val_str,
                unit="",
                normal_range=[],
                severity=a_sev,
                machine_id=machine_id,
                timestamp=timestamp,
                evidence=msg
            )
            # Insert multi-sensor combined alerts at top of list (highest priority)
            recommendations.insert(0, rec)

        return recommendations


recommendation_engine_instance = RecommendationEngine()

def generate_recommendations(rule_evals: Dict[str, Any], machine_id: str = "COMPRESSOR_01", timestamp: Optional[str] = None):
    """Helper wrapper for generating worker recommendations."""
    return recommendation_engine_instance.process_evaluations(rule_evals, machine_id, timestamp)
