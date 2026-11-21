"""Optional ThingsBoard summary publishing for the local edge service."""

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote

import requests

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "cloud_config.json"
ENDPOINTS = {
    "eu": "https://eu.thingsboard.cloud/api/v1",
    "us": "https://thingsboard.cloud/api/v1",
}


class ThingsBoardCloudSync:
    def __init__(self, config_path: Path = CONFIG_PATH):
        self.config = json.loads(config_path.read_text()) if config_path.exists() else {}
        self.region = os.environ.get("THINGSBOARD_REGION", "eu").lower()
        if self.region not in ENDPOINTS:
            self.region = "eu"
        self._token = os.environ.get("THINGSBOARD_DEVICE_TOKEN", "").strip()
        self.enabled = bool(self._token)
        self.last_sync_status = "WAITING_FOR_TELEMETRY" if self.enabled else "DISABLED"
        self.last_sync_message = "Cloud configuration is kept in memory."
        self.last_sync_time = 0.0
        self.total_synced_count = 0
        self._latest = None
        self._revision = 0
        self._sent_revision = 0
        self._generation = 0
        self._last_status = None
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._wake = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    def set_token(self, token: str, region: str = "eu"):
        with self._lock:
            self._token = token.strip()
            self.region = region
            self.enabled = bool(self._token)
            self._generation += 1
            self._sent_revision = 0
            self.total_synced_count = 0
            self.last_sync_time = 0.0
            self.last_sync_status = "READY" if self.enabled else "DISABLED"
            self.last_sync_message = (
                "ThingsBoard enabled for this API session." if self.enabled
                else "Cloud sync disabled. Local monitoring continues."
            )

    def record_decision(self, telemetry, decision):
        readings = telemetry.get("sensors", {})
        status = decision["overall_status"]
        recommendations = decision.get("worker_recommendations", [])
        values = {name: readings[name]["value"] for name in
                  ("temperature", "vibration", "pressure", "current", "speed")}
        values.update({
            "machine_status": status,
            "active_alerts_count": len(recommendations),
            "latest_alert": ((recommendations[0].get("alert_title") or
                              recommendations[0].get("alert_type")) if recommendations else "None"),
            "edge_latency_ms": decision["timing"]["edge_processing_latency_ms"],
            "data_source": telemetry["source"],
            "machine_id": telemetry["machine_id"],
        })
        with self._lock:
            previous = self._last_status
            self._last_status = status
            self._revision += 1
            self._latest = {"ts": int(time.time() * 1000), "values": values}
            if self.enabled and previous != status and status in ("WARNING", "CRITICAL"):
                self._wake.set()

    def _upload(self, *, manual=False):
        with self._send_lock:
            with self._lock:
                if not self.enabled:
                    return self._result(False, "DISABLED", "Enable ThingsBoard first.")
                if self._latest is None:
                    return self._result(False, "NO_TELEMETRY", "Start the simulator first.")
                if not manual and self._revision == self._sent_revision:
                    return self._result(False, "NO_NEW_TELEMETRY", "No new summary to send.")
                payload = self._latest
                revision = self._revision
                generation = self._generation
                endpoint = ENDPOINTS[self.region]
                token = self._token

            url = f"{endpoint}/{quote(token, safe='')}/telemetry"
            try:
                response = requests.post(url, json=payload,
                                         timeout=self.config.get("timeout_seconds", 5),
                                         verify=True, allow_redirects=False)
                code = response.status_code
                success = 200 <= code < 300
                status = "SYNCED" if success else f"HTTP_{code}"
                message = ("ThingsBoard accepted the telemetry." if success else
                           f"ThingsBoard returned HTTP {code}. Check the device access token and region.")
            except requests.RequestException:
                success, status = False, "NETWORK_ERROR"
                message = "Could not reach ThingsBoard. The latest summary is available for retry."

            with self._lock:
                if generation != self._generation:
                    return self._result(False, "CONFIG_CHANGED", "Cloud settings changed during the request.")
                self.last_sync_status, self.last_sync_message = status, message
                if success:
                    self._sent_revision = revision
                    self.last_sync_time = time.time()
                    self.total_synced_count += 1
                return self._result(success, status, message)

    @staticmethod
    def _result(success: bool, status: str, message: str):
        return {"success": success, "status": status, "message": message}

    def sync_now(self):
        return self._upload(manual=True)

    def _worker(self):
        while True:
            self._wake.wait(timeout=self.interval)
            self._wake.clear()
            self._upload()

    @property
    def interval(self):
        return max(5, self.config.get("periodic_interval_seconds", 30))

    def get_status(self):
        with self._lock:
            return {
                "enabled": self.enabled,
                "provider": "ThingsBoard Cloud",
                "region": self.region,
                "endpoint": ENDPOINTS[self.region],
                "token_configured": bool(self._token),
                "periodic_interval_seconds": self.interval,
                "total_synced_packets": self.total_synced_count,
                "last_sync_status": self.last_sync_status,
                "last_sync_message": self.last_sync_message,
                "last_sync_timestamp": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_sync_time))
                                        if self.last_sync_time else None),
            }


cloud_sync_instance = ThingsBoardCloudSync()
