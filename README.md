# SENTINEL-X

SENTINEL-X est un prototype de supervision pour un boîtier de capteurs connecté. Le boîtier transmet ses mesures par MQTT sécurisé; une API les stocke dans PostgreSQL et les diffuse au tableau de bord Vue en temps réel. Le tableau de bord présente aussi l’état du boîtier, les alertes et les commandes des LED et du buzzer.

## Fonctionnalités

- Tableau de bord Vue 3 : état du boîtier, température, humidité, gaz, mouvement, graphique des mesures, alertes et commandes.
- API REST FastAPI avec documentation Swagger et validation des données par Pydantic.
- PostgreSQL pour conserver télémétrie, événements, commandes et dernière activité des appareils. Les tables et index sont initialisés au démarrage de l’API.
- WebSocket (`/ws/live`) pour diffuser télémétrie, alertes et mises à jour de commandes.
- Pont MQTT TLS : réception des mesures sur `sentinel/+/telemetry` et publication des commandes vers `sentinel/<device_id>/cmd`.
- Flux webcam USB en MJPEG (`/video/stream` et `/video`), fourni par OpenCV et affiché dans le tableau de bord.
- Firmware ESP8266 (DHT22, capteur de gaz analogique, PIR et écran OLED), avec commande du buzzer et des LED verte et rouge.

Sans données, les valeurs du panneau d’état restent à « – » et le graphique ne contient pas de courbes. Les boutons de commande restent utilisables en aperçu : hors ligne, le clic change uniquement leur apparence locale et aucune commande n’est transmise. En ligne, les boutons envoient les commandes à l’API. Pour repérer l’action sélectionnée, « On » est vert, « Off » est rouge, « Clignote » reprend la couleur de la LED, et les commandes du buzzer deviennent rouges lorsqu’elles sont sélectionnées.

## Architecture

| Chemin | Rôle |
| --- | --- |
| `backend/main.py` | Application FastAPI et démarrage/arrêt du pont MQTT et de PostgreSQL. |
| `backend/routes/` | Routes REST pour l’état, la télémétrie, les alertes/événements et les commandes; WebSocket et routes vidéo. |
| `backend/models.py` | Validation des formats de télémétrie, d’alerte et de commande. |
| `backend/db.py` | Pool PostgreSQL, initialisation du schéma et gestion des appareils. |
| `backend/mqtt_bridge.py` | Abonnement aux mesures MQTT et publication des commandes MQTT en TLS. |
| `backend/docker-compose.yml` | Services Mosquitto, PostgreSQL, API et frontend conteneurisé. |
| `frontend/src/` | Application Vue, composants, état partagé et client API/WebSocket. |
| `firmware/sketch_oct6c/` | Programme de l’ESP8266 et modèle de configuration Wi-Fi/MQTT. |
| `Dockerfile`, `Dockerfile.front` | Images conteneurisées de l’API et du frontend. |

## Prérequis

- Python 3.12 recommandé (également utilisé par l’image Docker du backend).
- Une webcam USB accessible depuis le processus backend pour utiliser le flux vidéo.
- Node.js 20+ et npm pour le frontend.
- PostgreSQL 16, localement ou via Docker.
- Un broker MQTT accessible en TLS pour recevoir les mesures et piloter le boîtier.
- Pour flasher le boîtier : environnement Arduino ESP8266 et bibliothèques utilisées dans le sketch (PubSubClient, ArduinoJson, DHT sensor library, Adafruit GFX et Adafruit SSD1306).

## Développement local

### 1. Configurer PostgreSQL et l’API

Créez `backend/.env` avec l’URL PostgreSQL et, si nécessaire, la configuration du broker. Ne mettez pas de vrais identifiants dans le dépôt.

```dotenv
DATABASE_URL=postgresql://<utilisateur>:<mot-de-passe>@localhost:5432/sentinel_x
MQTT_BROKER_HOST=192.168.137.1
MQTT_BROKER_PORT=8883
CAMERA_INDEX=0
# Autorité de certification privée, si nécessaire :
# MQTT_TLS_CA_CERT=C:/chemin/vers/ca.crt
# Authentification MQTT facultative :
# MQTT_USERNAME=<utilisateur>
# MQTT_PASSWORD=<mot-de-passe>
```

L’API charge ce fichier depuis `backend/.env`. Les options MQTT correspondent au pont TLS; les identifiants utilisateur/mot de passe doivent être fournis ensemble, de même que le certificat et la clé du client.

Si PostgreSQL est disponible par Docker et que le fichier `backend/.env` contient aussi les variables attendues par le service `db` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`), démarrez-le depuis la racine du dépôt :

```powershell
docker compose -f backend/docker-compose.yml up -d db
```

Installez ensuite les dépendances et lancez l’API dans un terminal :

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload
```

L’API répond sur `http://127.0.0.1:8000`; Swagger est disponible à `http://127.0.0.1:8000/docs`. La connexion à un broker MQTT est lancée au démarrage; elle est nécessaire pour les échanges avec le boîtier, mais les mesures peuvent aussi être envoyées directement à l’API.

Le flux vidéo s’ouvre à la première requête et réutilise une capture webcam pour tous les clients. `CAMERA_INDEX` sélectionne la caméra OpenCV (défaut `0`; essayez `1` si plusieurs caméras sont connectées). Si aucune caméra ne peut être ouverte, l’API reste disponible et `GET /video/stream` répond `503 Service Unavailable` avec le détail de l’erreur. La webcam doit être accessible par le processus qui exécute l’API.

### 2. Installer et lancer le frontend

Dans un autre terminal :

```powershell
cd frontend
npm install
npm run dev
```

Ouvrez l’adresse affichée par Vite (en général `http://localhost:5173`). Par défaut, le frontend contacte le port `8000` de la même machine. Pour utiliser une autre adresse API, créez `frontend/.env.local` :

```dotenv
VITE_API_URL=http://localhost:8000
```

Redémarrez Vite après toute modification du fichier d’environnement. Il n’y a pas de mode démo dans le code actuel.

### 3. Configurer et flasher l’ESP8266 (facultatif)

Dans `firmware/sketch_oct6c/`, copiez `secrets.example.h` en `secrets.h`, puis renseignez le SSID/mot de passe Wi-Fi et l’utilisateur/mot de passe MQTT fournis pour votre installation. `secrets.h` ne doit pas être publié.

Le sketch utilise actuellement l’identifiant `SX-001`, l’adresse MQTT `192.168.137.1:8883`, une adresse IP fixe pour le boîtier et un certificat CA intégré au firmware. Adaptez ces paramètres et le certificat au réseau et au broker de votre environnement. Le boîtier publie ses mesures environ toutes les deux secondes et s’abonne à son topic de commandes.

## Lancement conteneurisé

`backend/docker-compose.yml` définit les services `db`, `mosquitto`, `api` et `frontend`. Ce déploiement attend un `backend/.env` avec les paramètres PostgreSQL et MQTT utilisés par Compose (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `MQTT_USER`, `MQTT_PASS`), ainsi que la configuration Mosquitto et les certificats montés sous `backend/mosquitto/`. Les chemins de certificats, le compte/passwd et les ACL doivent correspondre au broker; ces secrets et certificats ne doivent pas être ajoutés au dépôt.

Les ports HTTP exposés dans le compose sont liés à `192.168.99.10`, tandis que le sketch du boîtier est configuré pour `192.168.137.x`. Vérifiez et alignez ces adresses avec le réseau réel avant le lancement. Une fois cette configuration prête, depuis la racine :

```powershell
docker compose -f backend/docker-compose.yml up --build -d
docker compose -f backend/docker-compose.yml ps
```

L’image backend écoute sur le port `8000`; l’image frontend est servie par Nginx sur le port `80`. L’API initialise les tables PostgreSQL à son premier démarrage. Le volume `db_data` conserve les données après l’arrêt des conteneurs.

## API

Toutes les routes REST sont préfixées par `/api/v1`, sauf `/health`. Les paramètres numériques avec limites sont validés par l’API.

| Méthode | Route | Description |
| --- | --- | --- |
| `GET` | `/health` | Indique si le processus API répond (`{"ok": true}`). |
| `GET` | `/api/v1/status` | Dernier appareil connu, son état et s’il est en ligne; `offline_after_s` (défaut 30 s) règle le délai d’inactivité. |
| `GET` | `/api/v1/telemetry` | Mesures historiques; paramètres `limit` (1–2000) et `since` (date ISO 8601). |
| `POST` | `/api/v1/telemetry` | Enregistre une mesure et la diffuse sur le WebSocket. |
| `GET` | `/api/v1/alerts` | Liste les alertes récentes (`limit`, défaut 50). |
| `POST` | `/api/v1/alerts` | Enregistre un événement et le diffuse sur le WebSocket. |
| `GET` | `/api/v1/events` | Liste les événements; filtres `type`, `state` et `limit` (1–1000). |
| `POST` | `/api/v1/commands` | Enregistre et tente de publier une commande MQTT. |
| `GET` | `/api/v1/commands/pending?device_id=SX-001` | Récupère les commandes en attente pour l’appareil. Le firmware fourni utilise MQTT et ne poll pas actuellement cette route. |
| `WS` | `/ws/live` (alias `/ws`) | Flux des messages `telemetry`, `alert` et `command`. |
| `GET` | `/video/stream` (alias `/video`) | Flux webcam MJPEG (`multipart/x-mixed-replace`); répond `503` si aucune webcam utilisable n’est disponible. |

Exemple de mesure :

```json
{
  "device_id": "SX-001",
  "temperature": 24.3,
  "gas": 180,
  "humidity": 51.2,
  "motion": 0
}
```

`timestamp` est optionnel dans la télémétrie. Les alias acceptés sont `time` pour `timestamp`, `temp` pour `temperature` et `hum` pour `humidity`. Si le timestamp manque, l’heure de réception par l’API est utilisée.

Exemple d’alerte :

```json
{
  "device_id": "SX-001",
  "timestamp": 1760000000,
  "type": "temperature",
  "state": "WARNING",
  "value": 42.5,
  "unit": "C"
}
```

Les types d’alerte acceptés sont `gas`, `temperature`, `humidity`, `intrusion` et `cyber`; les états sont `OK`, `WARNING` et `CRITICAL`. Un événement `OK` est présenté comme une alerte résolue.

Exemple de commande :

```json
{
  "device_id": "SX-001",
  "target": "led_red",
  "action": "blink",
  "duration_ms": 5000
}
```

Les cibles disponibles sont `buzzer`, `led_green` et `led_red`; les actions sont `on`, `off` et `blink`. `duration_ms` est optionnel et limité à 60 000 ms. Le buzzer accepte `on`/`blink` pour activer l’alarme et `off` pour l’arrêter. Le pont publie sur MQTT lorsque le broker est connecté; sinon la commande est enregistrée avec l’état `queued`. Le firmware actuel reçoit les commandes par MQTT.

## Données et limites connues

- Le statut en ligne est déterminé à partir de l’activité la plus récente enregistrée pour un appareil; le tableau de bord rafraîchit ce statut périodiquement.
- Les alertes proviennent des événements persistés dans PostgreSQL. Le firmware présenté publie la télémétrie, mais ne génère pas lui-même de requêtes d’alerte HTTP.
- Le flux vidéo utilise la webcam accessible au backend. En exécution dans Docker, la webcam de l’hôte doit être explicitement passée au conteneur; sous Linux, cela nécessite généralement un mapping de périphérique tel que `/dev/video0`. Docker Desktop sous Windows ne transmet pas automatiquement les webcams USB aux conteneurs Linux; lancez l’API directement sur Windows ou configurez une source vidéo accessible depuis le conteneur.
- Le backend actuel n’implémente pas d’authentification API. CORS autorise toutes les origines dans `backend/main.py`. Ne publiez pas l’API telle quelle sur Internet; limitez son accès au réseau de confiance ou ajoutez une authentification et une politique CORS adaptées avant tout déploiement.
- La configuration du broker utilise TLS avec validation du certificat. N’activez pas de contournement de validation TLS en production et protégez les mots de passe/certificats.

## Arrêt

Pour le développement local, arrêtez l’API et Vite avec `Ctrl+C`, puis arrêtez PostgreSQL si vous l’avez lancé avec Docker :

```powershell
docker compose -f backend/docker-compose.yml down
```

Pour arrêter le déploiement conteneurisé, utilisez la même commande. `down` conserve les volumes de données; pour supprimer aussi les volumes PostgreSQL/MQTT et leurs données, utilisez `docker compose -f backend/docker-compose.yml down -v`.
