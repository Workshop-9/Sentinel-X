# SENTINEL-X

SENTINEL-X est une application de supervision de capteurs connectés. Elle reçoit des alertes et des mesures, affiche l’état des appareils en temps réel et permet de leur envoyer des commandes.

## Fonctionnalités

- Tableau de bord Vue 3 avec état des appareils, historique des mesures et alertes.
- API REST FastAPI pour les alertes, la télémétrie, l’état et les commandes.
- Notifications temps réel via WebSocket.
- Stockage PostgreSQL des événements, mesures, commandes et appareils.
- Mode de démonstration frontend avec données simulées.

## Architecture

| Dossier           | Rôle                                                              |
| ----------------- | ----------------------------------------------------------------- |
| `backend/`        | API FastAPI, accès PostgreSQL et routes par ressource.            |
| `backend/routes/` | Routes `alerts`, `telemetry`, `commands`, `status` et `realtime`. |
| `frontend/`       | Application Vue 3 servie en développement par Vite.               |

Les tables PostgreSQL sont créées automatiquement au démarrage de l’API : `events`, `telemetry`, `commands` et `devices`.

## Prérequis

- Python 3.10 ou plus récent.
- Node.js et npm, compatibles avec la version de Vite du projet.
- Docker Desktop avec Docker Compose.

## Installation et lancement

Les commandes ci-dessous sont à exécuter depuis la racine du dépôt. Lancez chaque service dans un terminal séparé.

### 1. Configurer la base de données

Créez `backend/.env` avec la même configuration que le service PostgreSQL défini dans `backend/docker-compose.yml` :

```dotenv
DATABASE_URL=postgresql://sentinel:admin@localhost:5432/sentinel_x
API_KEY=remplacez-par-une-cle-aleatoire-de-32-caracteres-minimum
MQTT_BROKER_HOST=192.168.137.1
MQTT_BROKER_PORT=8883
# MQTT_TLS_CA_CERT=C:/chemin/vers/ca.crt
# MQTT_USERNAME=identifiant-du-backend
# MQTT_PASSWORD=mot-de-passe-du-backend
# MQTT_CLIENT_CERT=C:/chemin/vers/client.crt
# MQTT_CLIENT_KEY=C:/chemin/vers/client.key
```

Ces identifiants sont réservés au développement local. Changez-les avant tout déploiement.
Générez une clé avec `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
L'API refuse de démarrer si la clé est absente, trop courte ou invalide.
Le backend se connecte à Mosquitto en TLS et s'abonne à `sentinel/+/telemetry`.
La validation du certificat TLS reste activée; configurez `MQTT_TLS_CA_CERT` si le broker utilise une autorité privée. Si Mosquitto exige une authentification, configurez aussi `MQTT_USERNAME` et `MQTT_PASSWORD`; pour le TLS mutuel, renseignez ensemble `MQTT_CLIENT_CERT` et `MQTT_CLIENT_KEY`.
Les commandes ne sont pas encore publiées par MQTT : le mécanisme actuel de commandes reste inchangé.

Démarrez PostgreSQL :

```powershell
docker compose -f backend/docker-compose.yml up -d --wait
```

Vérifiez son état :

```powershell
docker compose -f backend/docker-compose.yml ps
```

### 2. Installer et démarrer l’API

```powershell
python -m pip install -r backend/requirements
python -m uvicorn backend.main:app --reload
```

L’API est disponible sur `http://127.0.0.1:8000`. La documentation interactive Swagger se trouve sur `http://127.0.0.1:8000/docs`.

Sous Windows, si `python` ne désigne pas l’interpréteur attendu, remplacez-le par le chemin de votre `python.exe`, par exemple :

```powershell
& "C:\Program Files\Python312\python.exe" -m pip install -r backend/requirements
& "C:\Program Files\Python312\python.exe" -m uvicorn backend.main:app --reload
```

### 3. Installer et démarrer le frontend

Dans un autre terminal :

```powershell
cd frontend
npm install
npm run dev
```

Vite affiche l’adresse locale du tableau de bord, généralement `http://localhost:5173`.

Par défaut, le frontend cherche l’API sur le port `8000` de la même machine. Pour modifier l’adresse, créez `frontend/.env.local` et définissez `VITE_API_URL`, par exemple :

```dotenv
VITE_API_URL=http://localhost:8000
VITE_API_KEY=la-meme-cle-que-dans-backend/.env
```

Pour afficher les données simulées du tableau de bord, ajoutez `VITE_DEMO_MODE=true` à `frontend/.env.local`, puis redémarrez Vite.

## Tester l’API

Utilisez Swagger sur `http://127.0.0.1:8000/docs`, ou testez les routes suivantes :

| Méthode | Route                                           | Description                                                       |
| ------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| `GET`   | `/health`                                       | Vérifie que l’API répond.                                         |
| `GET`   | `/api/v1/status`                                | État du dernier appareil connu.                                   |
| `GET`   | `/api/v1/events`                                | Liste les événements, filtrables avec `type`, `state` et `limit`. |
| `GET`   | `/api/v1/alerts`                                | Liste les alertes.                                                |
| `POST`  | `/api/v1/alerts`                                | Enregistre une alerte.                                            |
| `GET`   | `/api/v1/telemetry`                             | Lit les mesures; accepte `limit` et `since`.                      |
| `POST`  | `/api/v1/telemetry`                             | Enregistre des mesures.                                           |
| `POST`  | `/api/v1/commands`                              | Ajoute une commande pour un appareil.                             |
| `GET`   | `/api/v1/commands/pending?device_id=esp8266-01` | Récupère les commandes non livrées d’un appareil.                 |
| `WS`    | `/ws/live`                                      | Reçoit les événements diffusés en temps réel.                     |

Exemple de corps pour `POST /api/v1/alerts` :

```json
{
  "device_id": "esp8266-01",
  "timestamp": 1760000000,
  "type": "temperature",
  "state": "WARNING",
  "value": 42.5,
  "unit": "C"
}
```

`timestamp` est exprimé en secondes Unix. Les valeurs permises pour `type` sont `gas`, `temperature`, `humidity`, `intrusion` et `cyber`; les états sont `OK`, `WARNING` et `CRITICAL`.

Exemple de corps pour `POST /api/v1/telemetry` :

```json
{
  "device_id": "esp8266-01",
  "timestamp": 1760000000,
  "temperature": 24.3,
  "gas": 180.0,
  "humidity": 51.2
}
```

Les commandes acceptent les cibles `buzzer`, `led_green`, `led_orange` ou `led_red`, et les actions `on`, `off` ou `blink`.

## Arrêt

Arrêtez l’API et Vite avec `Ctrl+C` dans leurs terminaux, puis arrêtez PostgreSQL :

```powershell
docker compose -f backend/docker-compose.yml down
```

Le volume Docker conserve les données PostgreSQL entre les démarrages.

## Sécurité

- Les routes vidéo `/video` et `/video/stream` ne sont pas implémentées et répondent `501`.
- Toutes les routes API REST et les WebSockets exigent `API_KEY`. Configurez `CORS_ORIGINS` dans `backend/.env` avec les origines frontend autorisées, séparées par des virgules; les origines locales Vite sont les valeurs par défaut.
- `VITE_API_KEY` est incorporée au bundle livré par le navigateur. Cette authentification convient à un environnement local ou contrôlé, mais ne protège pas un frontend public contre l'extraction de la clé. Pour une exposition Internet, placez l'API derrière un proxy avec une authentification adaptée et utilisez des identifiants distincts par appareil.
- Les identifiants de l’exemple Docker sont uniquement adaptés à un environnement local.
