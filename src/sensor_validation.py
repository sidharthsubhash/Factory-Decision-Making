"""
Sensor Validation Module for Two-Stage Reciprocating Air Compressor Telemetry.

Enforces strict physical and communication integrity checks:
1. Missing fields & incorrect types
2. NaN, null, and infinity checks
3. Unknown sensor units
4. Duplicate message IDs & out-of-order sequence numbers
5. Stale message detection (> 60s skew)
Never fabricates missing measurements.
"""

from typing import Dict, Any, Tuple, List, Optional
import math
from collections import OrderedDict
from threading import Lock
import json
from pathlib import Path
from datetime import datetime, timezone

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "compressor_limits.json"

class SensorValidator:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.limits = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                self.limits = cfg.get("sensors", {})
        
        self.seen_message_ids = OrderedDict()
        self._lock = Lock()
        self.max_seen_history = 5000
        self.last_sequences = OrderedDict()
        
    def reset_state(self):
        """Reset sequence and deduplication cache (useful for testing)."""
        self.seen_message_ids.clear()
        self.last_sequences.clear()

    def validate_reading_structure(self, payload: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
        errors: List[str] = []
        clean_data: Dict[str, Any] = {}

        if not isinstance(payload, dict):
            return False, ["Payload must be a JSON object"], {}

        # 1. Header Validation
        msg_id = payload.get("message_id")
        if not msg_id or not isinstance(msg_id, str):
            errors.append("Invalid or missing 'message_id'")
        clean_data["message_id"] = msg_id

        machine_id = payload.get("machine_id", "UNKNOWN")
        clean_data["machine_id"] = machine_id

        source = payload.get("source", "UNKNOWN")
        clean_data["source"] = source

        seq = payload.get("sequence")
        if seq is not None:
            if type(seq) is not int:
                errors.append("'sequence' must be an integer")
            elif seq < 0:
                errors.append("'sequence' must be non-negative")
        clean_data["sequence"] = seq

        # Timestamp validation
        ts_raw = payload.get("timestamp")
        parsed_ts = None
        if not ts_raw:
            errors.append("Missing 'timestamp'")
        else:
            try:
                # Accept ISO-8601 string or numeric unix epoch
                if isinstance(ts_raw, (int, float)):
                    parsed_ts = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                elif isinstance(ts_raw, str):
                    parsed_ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if parsed_ts is None or parsed_ts.tzinfo is None:
                    raise ValueError("Timestamp must include a time zone")
                age = (datetime.now(timezone.utc) - parsed_ts).total_seconds()
                if age > 60 or age < -10:
                    errors.append("Timestamp outside allowed window (60 seconds old or 10 seconds ahead)")
                clean_data["timestamp"] = parsed_ts.astimezone(timezone.utc).isoformat()
            except Exception as e:
                errors.append(f"Invalid timestamp format: {ts_raw} ({e})")
        clean_data["parsed_timestamp"] = parsed_ts

        # 2. Sensor Block Validation
        sensors = payload.get("sensors")
        if not sensors or not isinstance(sensors, dict):
            return False, errors + ["Missing or invalid 'sensors' object in telemetry"], {}

        clean_sensors: Dict[str, Dict[str, Any]] = {}
        required_sensors = ["temperature", "vibration", "pressure", "current", "speed"]

        for s_name in required_sensors:
            s_block = sensors.get(s_name)
            if not s_block:
                errors.append(f"Missing required sensor block: '{s_name}'")
                continue
            
            if not isinstance(s_block, dict):
                errors.append(f"Sensor block '{s_name}' must be an object with 'value' and 'unit'")
                continue

            val = s_block.get("value")
            unit = s_block.get("unit")

            # Validate numeric value
            if val is None or not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(f"Sensor '{s_name}' has non-numeric value: {val}")
                continue

            val = float(val)
            if math.isnan(val) or math.isinf(val):
                errors.append(f"Sensor '{s_name}' has NaN or Infinity value")
                continue

            # Validate unit
            expected_cfg = self.limits.get(s_name, {})
            expected_unit = expected_cfg.get("unit", "")
            if expected_unit and unit != expected_unit:
                errors.append(f"Sensor '{s_name}' unit mismatch: received '{unit}', expected '{expected_unit}'")

            clean_sensors[s_name] = {
                "value": val,
                "unit": unit or expected_unit,
                "name": expected_cfg.get("name", s_name)
            }

        clean_data["sensors"] = clean_sensors
        if not errors:
            stream = (machine_id, source, payload.get("stream_id") or "")
            key = (machine_id, source, msg_id)
            with self._lock:
                last_seq = self.last_sequences.get(stream, 0)
                if key in self.seen_message_ids:
                    errors.append(f"Duplicate message_id detected: {msg_id}")
                elif seq and seq <= last_seq:
                    errors.append(f"Out-of-order sequence received: {seq} (expected > {last_seq})")
                else:
                    self.seen_message_ids[key] = None
                    if len(self.seen_message_ids) > self.max_seen_history:
                        self.seen_message_ids.popitem(last=False)
                    if seq:
                        self.last_sequences[stream] = seq
                        self.last_sequences.move_to_end(stream)
                        if len(self.last_sequences) > self.max_seen_history:
                            self.last_sequences.popitem(last=False)
        is_valid = not errors
        return is_valid, errors, clean_data


validator_instance = SensorValidator()

def validate_telemetry(payload: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Helper wrapper for sensor validation."""
    return validator_instance.validate_reading_structure(payload)

