from datetime import datetime, timezone

from ..models import AlertIn


def iso_timestamp(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_alert(alert: AlertIn, event_id: int):
    return {
        "id": event_id,
        "type": alert.type,
        "severity": {"OK": "info", "WARNING": "warning", "CRITICAL": "critical"}[alert.state],
        "event": "cleared" if alert.state == "OK" else "raised",
        "source": alert.device_id,
        "received_at": iso_timestamp(alert.timestamp),
        "acknowledged": False,
        "value": alert.value,
        "unit": alert.unit,
    }