"""
Persistent Local SQLite Event Historian for Industrial Compressor Monitoring.

Stores all telemetry readings, alerts, worker recommendations, ML outcomes, and
operator acknowledgements. Data survives restarts.
"""

from contextlib import closing
import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import csv
import io

DB_PATH = Path(__file__).resolve().parent.parent / "factory_edge_events.db"

class EventStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            # 1. Telemetry and Decision Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    temperature REAL,
                    vibration REAL,
                    pressure REAL,
                    current REAL,
                    speed REAL,
                    rule_status TEXT NOT NULL,
                    ml_status TEXT NOT NULL,
                    ml_probability REAL,
                    latency_ms REAL,
                    raw_payload TEXT
                )
            """)

            # 2. Alerts and Recommendations Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    machine_id TEXT NOT NULL,
                    sensor TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    measured_value REAL,
                    unit TEXT,
                    normal_range TEXT,
                    possible_causes TEXT,
                    worker_actions TEXT,
                    maintenance_followup TEXT,
                    acknowledged INTEGER DEFAULT 0,
                    acknowledged_at TEXT,
                    acknowledged_by TEXT
                )
            """)
            conn.commit()

    def log_event(
        self,
        machine_id: str,
        source: str,
        sensors: Dict[str, Any],
        rule_status: str,
        ml_status: str,
        ml_probability: Optional[float] = None,
        latency_ms: Optional[float] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None
    ) -> int:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        temp = sensors.get("temperature", {}).get("value") if isinstance(sensors.get("temperature"), dict) else sensors.get("temperature")
        vib = sensors.get("vibration", {}).get("value") if isinstance(sensors.get("vibration"), dict) else sensors.get("vibration")
        press = sensors.get("pressure", {}).get("value") if isinstance(sensors.get("pressure"), dict) else sensors.get("pressure")
        curr = sensors.get("current", {}).get("value") if isinstance(sensors.get("current"), dict) else sensors.get("current")
        spd = sensors.get("speed", {}).get("value") if isinstance(sensors.get("speed"), dict) else sensors.get("speed")

        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO telemetry_events (
                    timestamp, machine_id, source, temperature, vibration, pressure, current, speed,
                    rule_status, ml_status, ml_probability, latency_ms, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, machine_id, source, temp, vib, press, curr, spd,
                rule_status, ml_status, ml_probability, latency_ms,
                json.dumps(raw_payload) if raw_payload else None
            ))
            event_id = cur.lastrowid
            conn.commit()
            return event_id

    def log_alert(self, alert: Dict[str, Any]) -> str:
        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO alerts (
                    alert_id, timestamp, machine_id, sensor, alert_type, severity,
                    measured_value, unit, normal_range, possible_causes, worker_actions,
                    maintenance_followup, acknowledged, acknowledged_at, acknowledged_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert["alert_id"],
                alert.get("timestamp", datetime.now(timezone.utc).isoformat()),
                alert.get("machine_id", "COMPRESSOR_01"),
                alert.get("sensor", "UNKNOWN"),
                alert.get("alert_type", "GENERIC_ALERT"),
                alert.get("severity", "WARNING"),
                alert.get("measured_value"),
                alert.get("unit"),
                json.dumps(alert.get("normal_range", [])),
                json.dumps(alert.get("possible_causes", [])),
                json.dumps(alert.get("recommended_worker_actions", [])),
                alert.get("maintenance_followup", ""),
                1 if alert.get("acknowledged") else 0,
                alert.get("acknowledged_at"),
                alert.get("acknowledged_by")
            ))
            conn.commit()
            return alert["alert_id"]

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "Operator") -> bool:
        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE alerts
                SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ?
                WHERE alert_id = ?
            """, (datetime.now(timezone.utc).isoformat(), acknowledged_by, alert_id))
            conn.commit()
            return cur.rowcount > 0

    def get_recent_events(self, limit: int = 50, machine_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM telemetry_events
                WHERE (? IS NULL OR machine_id = ?)
                ORDER BY id DESC LIMIT ?
            """, (machine_id, machine_id, limit))
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_alerts(self, active_only: bool = False, limit: int = 50, machine_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with closing(self.get_connection()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM alerts
                WHERE (? IS NULL OR machine_id = ?) AND (? = 0 OR acknowledged = 0)
                ORDER BY timestamp DESC LIMIT ?
                """,
                (machine_id, machine_id, active_only, limit),
            )
            rows = cur.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["normal_range"] = json.loads(d["normal_range"]) if d["normal_range"] else []
                d["possible_causes"] = json.loads(d["possible_causes"]) if d["possible_causes"] else []
                d["recommended_worker_actions"] = json.loads(d["worker_actions"]) if d["worker_actions"] else []
                d["acknowledged"] = bool(d["acknowledged"])
                results.append(d)
            return results

    def export_events_csv(self) -> str:
        events = self.get_recent_events(limit=5000)
        output = io.StringIO()
        fieldnames = [
            "id", "timestamp", "machine_id", "source", "temperature", "vibration",
            "pressure", "current", "speed", "rule_status", "ml_status", "ml_probability", "latency_ms",
            "run_command", "local_action", "model_version"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for event in events:
            payload = json.loads(event["raw_payload"]) if event["raw_payload"] else {}
            decision = payload.get("edge_decision", {})
            writer.writerow({**event, "run_command": payload.get("run_command"),
                             "local_action": decision.get("local_action"),
                             "model_version": decision.get("model_version")})
        return output.getvalue()


event_store_instance = EventStore()

