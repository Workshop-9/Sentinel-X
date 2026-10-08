import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

from . import db
from .models import TelemetryIn
from .routes.formatters import iso_timestamp
from .ws import manager

load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger(__name__)
TELEMETRY_TOPIC = "sentinel/+/telemetry"
DEVICE_TOPIC = re.compile(r"^sentinel/([A-Za-z0-9_.-]+)/telemetry$")
DEVICE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class MqttBridge:
    def __init__(self):
        self.client = None
        self.loop = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        host = os.getenv("MQTT_BROKER_HOST", "192.168.137.1")
        port = int(os.getenv("MQTT_BROKER_PORT", "8883"))
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")
        certfile = os.getenv("MQTT_CLIENT_CERT") or None
        keyfile = os.getenv("MQTT_CLIENT_KEY") or None

        if bool(certfile) != bool(keyfile):
            raise RuntimeError("MQTT_CLIENT_CERT and MQTT_CLIENT_KEY must be set together")
        if bool(username) != bool(password):
            raise RuntimeError("MQTT_USERNAME and MQTT_PASSWORD must be set together")

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=os.getenv("MQTT_CLIENT_ID", "sentinel-x-backend"),
        )
        if username:
            client.username_pw_set(username, password)

        client.tls_set(
            ca_certs=os.getenv("MQTT_TLS_CA_CERT") or None,
            certfile=certfile,
            keyfile=keyfile,
        )
        client.tls_insecure_set(False)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self.client = client
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        logger.info("MQTT TLS bridge started for %s:%s", host, port)

    def stop(self):
        if self.client is not None:
            self.client.disconnect()
            self.client.loop_stop()
            self.client = None

    def publish_command(self, device_id: str, payload: dict) -> bool:
        # Empêche l'injection de topic (+, #, /) via device_id
        if not DEVICE_ID.fullmatch(device_id):
            return False
        if self.client is None or not self.client.is_connected():
            return False
        info = self.client.publish(
            f"sentinel/{device_id}/command",
            json.dumps(payload),
            qos=1,
        )
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    @staticmethod
    def _on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            logger.error("MQTT connection rejected: %s", reason_code)
            return
        result, _ = client.subscribe(TELEMETRY_TOPIC, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Could not subscribe to MQTT telemetry topic: %s", result)
            return
        logger.info("Subscribed to MQTT topic %s", TELEMETRY_TOPIC)

    @staticmethod
    def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
        if reason_code.is_failure:
            logger.warning("MQTT connection lost: %s", reason_code)

    def _on_message(self, client, userdata, message):
        match = DEVICE_TOPIC.fullmatch(message.topic)
        if not match:
            logger.warning("Ignoring unexpected MQTT topic: %s", message.topic)
            return

        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("device_id") != match.group(1):
                raise ValueError("MQTT topic and payload device_id do not match")

            received_at = int(time.time())
            telemetry = TelemetryIn.model_validate({**payload, "timestamp": received_at})
            with db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO telemetry(device_id, ts, temperature, gas, humidity, motion, label) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        telemetry.device_id,
                        received_at,
                        telemetry.temperature,
                        telemetry.gas,
                        telemetry.humidity,
                        telemetry.motion,
                        telemetry.label,
                    ),
                )
                db.touch_device(conn, telemetry.device_id)

            event = {
                "type": "telemetry",
                "data": {
                    "received_at": iso_timestamp(received_at),
                    "sensors": {
                        "temperature_c": telemetry.temperature,
                        "gas_ppm": telemetry.gas,
                        "humidity_pct": telemetry.humidity,
                        "motion": telemetry.motion,
                    },
                    "label": telemetry.label,
                },
            }
            future = asyncio.run_coroutine_threadsafe(manager.broadcast(event), self.loop)
            future.add_done_callback(self._log_broadcast_error)
        except Exception:
            logger.exception("Could not process MQTT telemetry from %s", message.topic)

    @staticmethod
    def _log_broadcast_error(future):
        error = future.exception()
        if error:
            logger.error("Could not broadcast MQTT telemetry", exc_info=error)


mqtt_bridge = MqttBridge()