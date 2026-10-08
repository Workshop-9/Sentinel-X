"""Point d'entrée unique : python -m sentinel_ai <commande>   (depuis le dossier ai/)"""
from __future__ import annotations

import argparse
import logging
import sys

from . import __version__

log = logging.getLogger("sentinel_ai")

EPILOG = """exemples :
  python -m sentinel_ai doctor                    vérifier l'installation avant la démo
  python -m sentinel_ai collect normal --minutes 15
  python -m sentinel_ai train                     entraîner + rapport + mise en production
  python -m sentinel_ai anomaly                   IA anomalies en direct (MQTT)
  python -m sentinel_ai vision                    IA vision webcam en direct
  python -m sentinel_ai simulate --offline        démo de l'IA sans boîtier ni réseau
  python -m sentinel_ai alarm off                 couper la sirène
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m sentinel_ai", epilog=EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                description="Sentinel-X — IA locale (anomalies capteurs + vision)")
    p.add_argument("--config", help="fichier TOML (défaut : config/settings.toml)")
    p.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    p.add_argument("--version", action="version", version=f"sentinel_ai {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="commande")

    c = sub.add_parser("collect", help="enregistrer la télémétrie MQTT dans data/telemetry.csv")
    c.add_argument("label", choices=["normal", "anomalie"], help="étiquette de la session")
    c.add_argument("--minutes", type=float, help="durée (défaut : jusqu'à Ctrl+C)")

    t = sub.add_parser("train", help="entraîner, évaluer et versionner le modèle d'anomalies")
    t.add_argument("--no-promote", action="store_true", help="ne pas mettre en production")
    t.add_argument("--no-report", action="store_true", help="sans figures ni rapport HTML")

    m = sub.add_parser("models", help="lister les modèles / changer celui en production")
    m.add_argument("action", nargs="?", choices=["list", "promote"], default="list")
    m.add_argument("version", nargs="?", help="version à promouvoir")

    a = sub.add_parser("anomaly", help="détection d'anomalies en direct (MQTT)")
    a.add_argument("--no-alarm", action="store_true", help="ne pas déclencher la sirène")

    v = sub.add_parser("vision", help="détection d'intrus par webcam en direct")
    v.add_argument("--camera", type=int, help="numéro de caméra (défaut : config)")
    v.add_argument("--source", help="fichier vidéo à la place de la webcam (tests)")
    v.add_argument("--headless", action="store_true", help="sans fenêtre d'affichage")
    v.add_argument("--no-stream", action="store_true", help="sans flux vidéo HTTP")

    b = sub.add_parser("vision-bench", help="mesurer la latence YOLO (budget 100 ms)")
    b.add_argument("--frames", type=int, default=60)
    b.add_argument("--camera", type=int, help="utiliser la webcam plutôt que des images d'exemple")

    s = sub.add_parser("simulate", help="boîtier virtuel avec panne simulée")
    s.add_argument("--scenario", default="fuite_gaz",
                   help="fuite_gaz | surchauffe_lente | choc_thermique | infiltration_humidite | none")
    s.add_argument("--at", type=float, default=60, help="début de la panne (s)")
    s.add_argument("--duration", type=float, default=300, help="durée totale (s)")
    s.add_argument("--device", default="SX-SIM")
    s.add_argument("--offline", action="store_true", help="sans réseau : IA locale uniquement")
    s.add_argument("--speed", type=float, default=1.0, help="accélération (0 = maximum)")

    al = sub.add_parser("alarm", help="allumer / éteindre la sirène du boîtier")
    al.add_argument("state", choices=["on", "off"])
    al.add_argument("--device", help="boîtier (défaut : config)")

    sub.add_parser("cameras", help="trouver le numéro de la webcam USB")
    sub.add_parser("doctor", help="diagnostic complet avant la démo")
    return p


def list_models(settings) -> None:
    from .anomaly.registry import Registry, SUBDIR
    from .paths import read_locations
    for base in read_locations(settings.paths.artifacts_dir):
        reg = Registry(base / SUBDIR)
        data = reg.read()
        if not data["models"]:
            continue
        print(f"\n{reg.root}")
        for ver, e in sorted(data["models"].items()):
            star = "★" if ver == data.get("production") else " "
            s = e.get("summary", {})
            print(f"  {star} {ver:28s} {e['algorithm']:18s} test FPR {s.get('test_fpr', 0):.1%}  "
                  f"gates {'OK' if s.get('gates_passed') else 'KO'}")


def main(argv: list[str] | None = None) -> int:
    from .config import load_settings
    from .log import setup_logging
    setup_logging()                              # UTF-8 avant d'afficher l'aide
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)
    settings = load_settings(args.config)

    try:
        cmd = args.command
        if cmd == "collect":
            from .tools.collector import run
            run(settings, args.label, args.minutes)
        elif cmd == "train":
            from .anomaly.train import train
            res = train(settings, promote=not args.no_promote, make_report=not args.no_report)
            return 0 if res.gates_passed else 2
        elif cmd == "models":
            if args.action == "promote":
                if not args.version:
                    raise ValueError("précise la version : python -m sentinel_ai models promote <version>")
                from .anomaly.registry import Registry
                Registry.for_writing(settings.paths.artifacts_dir).promote(args.version)
                log.info("%s est maintenant en production", args.version)
            else:
                list_models(settings)
        elif cmd == "anomaly":
            from .anomaly.service import run
            run(settings, auto_alarm=False if args.no_alarm else None)
        elif cmd == "vision":
            from .vision.service import run
            run(settings, camera=args.camera, source=args.source, headless=args.headless,
                stream=False if args.no_stream else None)
        elif cmd == "vision-bench":
            from .vision.benchmark import run
            run(settings, n=args.frames, camera=args.camera)
        elif cmd == "simulate":
            from .tools.simulate import run
            run(settings, None if args.scenario == "none" else args.scenario, args.at,
                args.duration, args.device, args.offline, args.speed)
        elif cmd == "alarm":
            from .tools.alarm import run
            run(settings, args.state, args.device)
        elif cmd == "cameras":
            from .tools.cameras import run
            run()
        elif cmd == "doctor":
            from .tools.doctor import run
            return 0 if run(settings) else 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        from .anomaly.registry import IntegrityError
        from .mqtt import MqttConfigError
        if args.verbose or not isinstance(
                exc, (MqttConfigError, ConnectionError, FileNotFoundError, IntegrityError,
                      ValueError, RuntimeError)):
            log.exception("Erreur inattendue")
        else:
            log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
