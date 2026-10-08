"""Client MQTT commun : TLS + authentification + statut « online/offline » (last will)."""
from __future__ import annotations

import logging
import ssl

import paho.mqtt.client as mqtt

from .config import Settings
from .paths import resolve

log = logging.getLogger(__name__)


class MqttConfigError(RuntimeError):
    pass


def create_client(settings: Settings, service: str, device: str | None = None) -> mqtt.Client:
    """Client prêt à connecter. `service` sert d'identifiant et de topic de statut."""
    m = settings.mqtt
    if not m.has_credentials:
        raise MqttConfigError(
            "Identifiants MQTT absents : renseigne SENTINEL_MQTT_USER et SENTINEL_MQTT_PASS "
            "dans ai/.env (voir .env.example)")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"sentinel-ai-{service}",
                         reconnect_on_failure=True)
    client.username_pw_set(m.username, m.password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    if m.tls:
        ca = resolve(m.ca_cert)
        if not ca.exists():
            raise MqttConfigError(f"Certificat CA introuvable : {ca}")
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = m.tls_check_hostname
        client.tls_set_context(context)

    status_topic = settings.topic("ai_status", device=device, service=service)
    client.will_set(status_topic, "offline", qos=1, retain=True)
    client.user_data_set({"status_topic": status_topic})
    return client


def announce_online(client: mqtt.Client) -> None:
    topic = client.user_data_get()["status_topic"]
    client.publish(topic, "online", qos=1, retain=True)


def announce_offline(client: mqtt.Client) -> None:
    topic = client.user_data_get()["status_topic"]
    try:
        client.publish(topic, "offline", qos=1, retain=True).wait_for_publish(timeout=2)
    except (RuntimeError, ValueError):
        pass  # déjà déconnecté : le last will publiera « offline »


def describe(settings: Settings) -> str:
    m = settings.mqtt
    return f"{'mqtts' if m.tls else 'mqtt'}://{m.host}:{m.port}"


def explain_error(exc: BaseException) -> str:
    """Traduit les erreurs de connexion courantes en piste de résolution."""
    text = str(exc)
    if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in text:
        if "mismatch" in text or "match" in text:
            return (f"{text}\n→ Le certificat du broker ne contient pas son adresse IP. Mettre "
                    "tls_check_hostname = false dans config/settings.toml (le certificat reste "
                    "vérifié par la CA) ou régénérer le certificat avec l'IP en SAN.")
        return f"{text}\n→ Mauvais fichier certs/ca.crt : demande la CA à INFRA/CYBER."
    if isinstance(exc, ConnectionRefusedError):
        return f"{text}\n→ Broker arrêté ou mauvais port (8883 = TLS, 1883 = sans TLS)."
    if isinstance(exc, (TimeoutError, OSError)):
        return (f"{text}\n→ Broker injoignable : es-tu bien connecté au Wi-Fi de l'équipe "
                "(SENTIENLX-G9) ? Le PC serveur est-il allumé ?")
    return text


def connect(client: mqtt.Client, settings: Settings) -> None:
    """Première connexion explicite (erreurs lisibles), reconnexion auto ensuite."""
    m = settings.mqtt
    log.info("Connexion au broker %s ...", describe(settings))
    try:
        client.connect(m.host, m.port, keepalive=m.keepalive)
    except (OSError, ssl.SSLError) as exc:
        raise ConnectionError(explain_error(exc)) from exc


def on_connect_logger(name: str):
    """Callback on_connect qui journalise un refus (mauvais identifiants, ACL...)."""
    def _cb(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("[%s] Connexion refusée par le broker : %s → vérifie "
                      "SENTINEL_MQTT_USER / SENTINEL_MQTT_PASS dans .env", name, reason_code)
        else:
            log.info("[%s] Connecté à %s", name, describe_from_client(client))
    return _cb


def describe_from_client(client: mqtt.Client) -> str:
    return f"{client.host}:{client.port}"
