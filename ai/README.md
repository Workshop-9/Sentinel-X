# Sentinel-X — IA locale

Partie **Intelligence Artificielle** du boîtier Sentinel-X (Workshop EPSI M1 2026) :

| Brique | Ce qu'elle fait | Technologie |
|---|---|---|
| **Maintenance prédictive** | détecte les dérives anormales des capteurs (température, humidité, gaz) **sans seuil fixe**, explique la cause et déclenche la sirène | scikit-learn — Isolation Forest + enveloppe apprise |
| **Vision** | repère une présence humaine sur la webcam USB, envoie une alerte avec photo, diffuse la vidéo au dashboard | YOLOv8n (ultralytics) + OpenCV |
| **MLOps** | entraînement reproductible, évaluation, contrôles qualité, modèles versionnés et signés, rapport automatique | `python -m sentinel_ai train` |

## Résultats du modèle en production

Modèle `iforest-20261008-112651` — rapport complet : [`artifacts/anomaly/iforest-20261008-112651/report.html`](artifacts/anomaly/iforest-20261008-112651/report.html)

| Indicateur (données jamais vues à l'entraînement) | Résultat |
|---|---|
| Alarmes confirmées à tort sur la période de test (6,5 min) | **0** |
| Session anomalie réelle (gaz + chaleur) détectée | **100 %** des mesures, AUC 1,000 |
| Pannes simulées détectées (4 scénarios × 5 injections) | **20/20** — règle fixe `temp > 40 °C ou gaz > 400` : **0/20** |
| Surchauffe lente +2 °C en 3 min (exemple du cahier des charges) | alarme en **26 s** (médiane), à +0,3 °C seulement |
| Fuite de gaz / départ de feu / infiltration d'eau | **6 s / 8 s / 8 s** |
| Alerte maintenue tant que l'incident dure | **100 %** (Isolation Forest seul : 45 %) |
| Changement de salle (+3 °C, −10 % HR, +25 gaz) | 5 % de mesures suspectes (ancienne version : **100 %**) |
| Retour à la normale après un incident | **36 s** |
| Latence vision YOLOv8n 640×480 sur le CPU i5 | **≈ 50 ms**/image, p95 57 ms (budget sujet : 100 ms) |

Les figures prêtes pour le dossier PDF et les slides sont dans
[`artifacts/anomaly/iforest-20261008-112651/figures/`](artifacts/anomaly/iforest-20261008-112651/figures/)
et [`artifacts/vision/`](artifacts/vision/).

---

## 1. Architecture

```
 ESP8266 SX-001 ──MQTTS 8883──▶  Broker Mosquitto TLS (PC serveur 192.168.137.1)  ◀──MQTTS── Dashboard
   capteurs                       │ sentinel/SX-001/telemetry      ▲ anomaly / vision / cmd
                                  ▼                                │
                 ┌──────────── PC IA (ce dossier) ─────────────────┴──────────┐
                 │  python -m sentinel_ai anomaly                              │
                 │    télémétrie → features en flux → Isolation Forest         │
                 │    + enveloppe → confirmation 3 mesures → anomaly (+ cmd)    │
                 │  python -m sentinel_ai vision                               │
                 │    webcam C270 → YOLOv8n → confirmation 3/5 images          │
                 │    → vision + photo  ;  flux http://127.0.0.1:8081/video    │
                 └─────────────────────────────────────────────────────────────┘
```

## 2. Installation (Windows, PowerShell, depuis le dossier `ai`)

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env          # puis renseigner SENTINEL_MQTT_USER / SENTINEL_MQTT_PASS
```

À placer à la main (jamais dans Git) :

- `certs/ca.crt` — certificat de la CA « SentinelX-CA-G9 » (fourni par INFRA/CYBER) ;
- `models/yolov8n.pt` — poids YOLO ([téléchargement](https://github.com/ultralytics/assets/releases)).

Puis vérifier que tout est prêt :

```powershell
python -m sentinel_ai doctor
```

> **Windows bloque l'écriture de Python dans `Documents`** (« Contrôle d'accès aux dossiers »).
> Le programme le détecte et écrit alors ses sorties (données collectées, nouveaux modèles)
> dans `C:\Users\<toi>\sentinel_x`. Pour écrire directement dans `ai/` : Sécurité Windows →
> Protection contre les virus et menaces → Protection contre les ransomware → Autoriser une
> application → ajouter `python.exe`.

## 3. Commandes

Toutes les commandes se lancent depuis le dossier `ai` : `python -m sentinel_ai <commande>`
(`--help` sur chaque commande pour les options).

| Commande | Rôle | Ancien script |
|---|---|---|
| `doctor` | diagnostic complet avant la démo (libs, modèle, secrets, certificat, broker, flux) | — |
| `collect normal --minutes 15` | enregistre la télémétrie dans `data/telemetry.csv` (`normal` ou `anomalie`) | `collector.py` |
| `train` | entraîne, évalue, versionne le modèle et génère le rapport | `train_anomaly.py` |
| `models` / `models promote <version>` | liste les versions / change le modèle en production | — |
| `anomaly` (`--no-alarm`) | maintenance prédictive en direct sur MQTT | `anomaly_live.py` |
| `vision` (`--camera 1`, `--headless`) | détection d'intrus en direct | `vision_live.py` |
| `vision-bench` | mesure la latence YOLO (exigence < 100 ms) | `test_yolo.py` |
| `simulate --offline` | boîtier virtuel + panne simulée, **sans réseau** (démo de secours) | — |
| `simulate --scenario fuite_gaz` | idem mais publie sur MQTT (`sentinel/SX-SIM/telemetry`) pour tester le dashboard | — |
| `alarm on` / `alarm off` | commande manuelle de la sirène | `alarm.py` |
| `cameras` | trouve le numéro de la webcam USB | `find_camera.py` |

## 4. Contrat MQTT

| Topic | Sens | Contenu |
|---|---|---|
| `sentinel/<id>/telemetry` | ESP → IA | `{"device_id":"SX-001","ts":…,"temp":26.1,"hum":48.0,"gas":60,"motion":0}` |
| `sentinel/<id>/anomaly` | IA → dashboard | `{"device_id","ts","score","is_anomaly","streak","level","causes","model"}` |
| `sentinel/<id>/vision` | IA → dashboard | `{"device_id","source":"vision","type":"intrusion","severity":"high","confidence","persons","inference_ms","snapshot","ts"}` |
| `sentinel/<id>/cmd` | IA → ESP | `{"alarm":"on"}` (QoS 1), envoyé une seule fois par incident confirmé |
| `sentinel/<id>/ai/<service>/status` | IA → dashboard | `online` / `offline` (retained + last will) |

Exemple de message `anomaly` :

```json
{"device_id": "SX-001", "ts": "2026-10-09T10:12:04", "score": -0.0731, "is_anomaly": true,
 "streak": 3, "level": "alarm", "causes": ["gaz au-dessus de la normale", "gaz en hausse rapide"],
 "model": "iforest-20261008-112651"}
```

- `score` < 0 = anormal (même convention que la version précédente) ;
- `level` : `normal` → `suspect` (1–2 mesures anormales) → `alarm` (≥ 3 d'affilée) ;
- les champs historiques (`score`, `is_anomaly`, `streak`, `ts`) sont inchangés : le dashboard existant continue de fonctionner.
- l'identité du boîtier est prise dans le **topic** (protégé par les ACL du broker), pas dans le JSON.

## 5. Maintenance prédictive — méthode

Le cahier des charges interdit les règles `if temp > 40`. Le modèle apprend donc, **sans étiquettes**, le fonctionnement normal du boîtier et signale ce qui s'en écarte.

1. **Données** — `data/telemetry.csv` (1 125 mesures du 07/10). Contrôles : plages physiques des capteurs, doublons, coupures. Les corrections d'étiquettes sont tracées dans `data/annotations.csv` (ex. 38 mesures de manipulation du boîtier étiquetées « normal » par erreur), les CSV bruts ne sont jamais modifiés.
2. **Features en flux** (`sentinel_ai/anomaly/features.py`) — le **même code** sert à l'entraînement et en direct (zéro écart entraînement/production) :
   - `temp_dev`, `hum_dev`, `gas_dev` : écart à une ligne de base qui s'adapte au site (moyenne exponentielle, demi-vie 5 min) ;
   - `d_temp`, `d_hum`, `d_gas` : variation sur 30 s (anomalies *cinétiques*) ;
   - `gas_std` : instabilité du gaz sur 30 s.

   On n'apprend pas des niveaux (24 °C) mais des dynamiques : le modèle fonctionne dans la salle de soutenance sans réapprentissage.
3. **Découpage chronologique** 60 / 20 / 20 (entraînement / calibration / test) — jamais aléatoire sur une série temporelle.
4. **Modèle** — `StandardScaler` + Isolation Forest (200 arbres, graine fixe), entraîné uniquement sur le normal.
5. **Seuil calibré** sur la période de calibration (1 % de mesures normales au-dessus), pas choisi à la main.
6. **Enveloppe apprise** — un Isolation Forest sature hors de son domaine d'entraînement (un écart de +100 écarts-types sur une seule feature n'est pas mieux isolé qu'un point de bordure). Chaque feature est donc aussi bornée à 1,5 × le plus grand écart observé en fonctionnement normal (7,2 σ). Sans elle, l'alerte retombait pendant un incident qui dure (45 % de maintien au lieu de 100 %).
7. **Confirmation** — alarme après 3 mesures anormales consécutives (6 s) : filtre les glitchs ponctuels de l'ADC du MQ-2 (le gaz saute parfois de 50 à 42 sur une seule mesure).
8. **Gel de la ligne de base** pendant un incident (une fuite ne devient pas « la nouvelle normale ») ; réapprentissage seulement si la situation dure plus de 5 min.
9. **Explicabilité** — chaque alerte contient les features les plus éloignées de la normale (en écarts-types), traduites en français : « température en hausse rapide », « gaz instable »…

### Évaluation

- **Test** : 6,5 min de fonctionnement normal jamais vues → taux de mesures suspectes et d'alarmes confirmées à tort.
- **Anomalie réelle** : session « anomalie » du 07/10 rejouée dans le détecteur de production.
- **Pannes simulées** : des dérives réalistes (surchauffe lente, fuite de gaz, choc thermique, infiltration d'eau) sont **ajoutées à de vraies mesures normales** (le bruit capteur est conservé) à 5 instants différents ; on mesure le délai avant alarme et le maintien de l'alerte, comparés à une règle à seuils fixes.
- **Robustesse** : même période de test transposée dans une « autre salle » (+3 °C, −10 % HR, +25 gaz).
- **Benchmark** : Isolation Forest, Local Outlier Factor, One-Class SVM et covariance robuste, mêmes données et même protocole. Isolation Forest est retenu : sans alarme à tort, c'est lui qui détecte le plus tôt la surchauffe lente.

### Contrôles qualité (gates)

`train` ne met un modèle en production que s'il passe tous les contrôles de `config/settings.toml` → `[anomaly.gates]` : alarmes à tort ≤ 2/h, mesures suspectes ≤ 10 %, anomalie réelle ≥ 80 %, scénarios ≥ 75 %, alerte maintenue ≥ 90 %. Sinon le modèle précédent reste en production (code de sortie 2).

## 6. Vision

- YOLOv8n pré-entraîné COCO, classe `person` uniquement, confiance ≥ 0,5, images redimensionnées en 640×480.
- **Confirmation temporelle** : intrus confirmé s'il est vu sur ≥ 3 des 5 dernières images (élimine les faux positifs d'une image).
- Alerte MQTT au plus toutes les 10 s, avec photo `intrus_AAAAMMJJ_HHMMSS.jpg` dans `C:\Users\<toi>\sentinel_captures`.
- **RGPD** : les photos de plus de 7 jours sont supprimées au démarrage (`captures_retention_days`).
- `vision.auto_alarm = true` dans la config pour que la vision déclenche aussi la sirène.

### Flux vidéo pour le dashboard

`http://127.0.0.1:8081/video` (MJPEG), `/snapshot.jpg`, `/health` (JSON : fps, latence, personnes, état MQTT).
Par défaut le flux n'écoute **que sur cette machine**. Si le dashboard tourne sur un autre PC :

1. définir `SENTINEL_STREAM_TOKEN` dans `.env` ;
2. mettre `host = "0.0.0.0"` dans `[vision.stream]` ;
3. utiliser `http://<ip-du-pc-ia>:8081/video?token=<jeton>` dans le dashboard.

## 7. MLOps et reproductibilité

```
artifacts/anomaly/
├── registry.json                  version en production + historique + empreintes SHA-256
└── iforest-20261008-112651/
    ├── model.joblib               pipeline + seuil + enveloppe + paramètres des features
    ├── metrics.json               toutes les métriques, gates, splits, versions des libs
    ├── benchmark.csv              comparaison des 4 algorithmes
    ├── data_profile.json          profil et empreinte des données d'entraînement
    ├── real_anomaly_timeline.csv  décisions du détecteur seconde par seconde
    ├── model_card.md              fiche du modèle (usage, limites)
    ├── report.html                rapport autonome (s'ouvre dans un navigateur, imprimable en PDF)
    └── figures/                   10 graphiques PNG pour le dossier et les slides
```

- Toute la configuration est dans `config/settings.toml` ; graine aléatoire fixe → mêmes résultats à chaque entraînement.
- **Intégrité** : l'empreinte SHA-256 du modèle est vérifiée avant chaque chargement ; un fichier remplacé ou altéré est refusé (un `joblib` malveillant pourrait exécuter du code).

## 8. Sécurité (avant le pentest)

- Aucun secret dans le code ni dans Git : identifiants dans `.env`, certificat dans `certs/` (tous deux dans `.gitignore`).
- MQTT en **TLS 1.2+** avec vérification du certificat par la CA ; identifiants propres au service IA.
- Messages entrants validés (JSON, plages physiques) : un message malformé est ignoré, jamais fatal.
- Identité du boîtier lue dans le topic (ACL broker) et non dans le JSON (usurpation impossible).
- Flux vidéo : 127.0.0.1 par défaut, jeton comparé en temps constant, 4 clients max, pas de bannière de version.
- Modèle signé SHA-256, photos purgées après 7 jours.

## 9. Tests

```powershell
python -m pytest
```

49 tests (≈ 30 s) : features (y compris invariance au changement de salle), détecteur (alarme unique, gel, enveloppe), validation des messages, configuration et secrets, service MQTT, registre et intégrité, scénarios, serveur vidéo (jeton, en-têtes), pipeline d'entraînement complet sur les vraies données, et **intégration MQTT de bout en bout** (simulateur → broker de test → service anomalies → commande sirène, collecte CSV, mauvais mot de passe).

## 10. Structure

```
ai/
├── README.md, requirements.txt, pyproject.toml, .env.example, .gitignore
├── config/settings.toml         tous les réglages (aucun secret)
├── data/telemetry.csv           données collectées + annotations.csv
├── artifacts/                   modèles versionnés, rapports, figures, benchmark vision
├── models/yolov8n.pt            poids YOLO (non versionné)
├── docs/DEMO.md                 déroulé de la démo + questions probables du jury
├── sentinel_ai/
│   ├── __main__.py              ligne de commande
│   ├── config.py, paths.py, mqtt.py, log.py, plotting.py
│   ├── data/                    schéma des messages, chargement, scénarios de panne
│   ├── anomaly/                 features, modèles, détecteur, entraînement, évaluation, rapport, registre, service
│   ├── vision/                  détecteur YOLO, serveur vidéo, service, benchmark
│   └── tools/                   collecte, alarme, simulateur, caméras, diagnostic
└── tests/                       49 tests + mini-broker MQTT de test
```

## 11. Dépannage

| Symptôme | Solution |
|---|---|
| `Identifiants MQTT absents` | copier `.env.example` en `.env` et le remplir |
| `certificate verify failed: IP address mismatch` | `tls_check_hostname = false` dans `[mqtt]` (la CA reste vérifiée) ou régénérer le certificat avec l'IP en SAN |
| `Broker injoignable` / timeout | être sur le Wi-Fi **SENTIENLX-G9**, PC serveur allumé, port 8883 |
| `Connexion refusée par le broker` | mauvais identifiants ou ACL : voir INFRA/CYBER |
| `Caméra 1 introuvable` | `python -m sentinel_ai cameras`, puis `camera_index` dans la config |
| Sorties dans `C:\Users\<toi>\sentinel_x` | normal si `Documents` est protégé (voir Installation) |
| Trop d'alertes dans une nouvelle salle | laisser tourner 1 min (ligne de base), sinon `collect normal --minutes 15` puis `train` |

## 12. Limites et perspectives

- 34 minutes de données dans une seule salle : le taux de fausses alarmes est estimé sur 6,5 min seulement. Plusieurs heures de collecte (jour/nuit) affineraient le seuil.
- Les pannes sont simulées par-dessus du signal réel : elles mesurent la sensibilité, pas la physique exacte d'un incendie.
- Le MQ-2 n'est pas calibré : « gaz » est une valeur ADC brute (0–1024), pas des ppm.
- Perspectives : fusion capteurs + PIR + vision dans un score de risque unique, réentraînement planifié, suivi de dérive des données, export OpenVINO pour accélérer YOLO sur CPU Intel.
