"""Commande manuelle de la sirène du boîtier : python -m sentinel_ai alarm on|off"""
from __future__ import annotations

import json
import logging

from ..config import Settings

log = logging.getLogger(__name__)


def run(settings: Settings, state: str, device: str | None = None) -> None:
    from .. import mqtt as mq

    device = device or settings.device_id
    client = mq.create_client(settings, "alarm")
    client.on_connect = mq.on_connect_logger("alarm")
    mq.connect(client, settings)
    client.loop_start()
    try:
        topic = settings.topic("cmd", device)
        info = client.publish(topic, json.dumps({"alarm": state}), qos=1)
        info.wait_for_publish(timeout=5)
        if not info.is_published():
            raise ConnectionError("Commande non confirmée par le broker (droits ACL ?)")
        log.info("Alarme %s envoyée à %s (%s)", state.upper(), device, topic)
    finally:
        client.loop_stop()
        client.disconnect()
