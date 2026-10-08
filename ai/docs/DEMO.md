# Démo IA — soutenance du vendredi

## La veille / le matin

```powershell
cd C:\Users\ordi\Documents\sentinel-x\ai
python -m sentinel_ai doctor          # tout doit être OK (sauf l'avertissement « Documents protégé »)
python -m sentinel_ai cameras         # vérifier que la Logitech est bien la caméra 1
```

Arriver tôt dans la salle : le boîtier allumé depuis ≥ 5 min (préchauffage du MQ-2) et le service
`anomaly` lancé depuis ≥ 1 min (la ligne de base s'adapte à la salle).

## Lancement (2 terminaux PowerShell dans `ai/`)

```powershell
python -m sentinel_ai anomaly         # terminal 1 : maintenance prédictive
python -m sentinel_ai vision          # terminal 2 : webcam (fenêtre + flux dashboard)
```

## Déroulé (minutes 3 à 5 de la soutenance)

| Temps | Action | Ce que le jury voit |
|---|---|---|
| 0:00 | Montrer le dashboard au calme | courbes en direct, statut « normal », IA online |
| 0:20 | Passer devant la webcam | cadre « INTRUS », photo, alerte vision dans le dashboard en < 1 s |
| 0:50 | Approcher un briquet **éteint** (gaz) du MQ-2 | `suspect` puis `alarm` en ~6 s, sirène + LED rouge, cause : « gaz en hausse rapide » |
| 1:30 | `python -m sentinel_ai alarm off` ou bouton du dashboard | sirène coupée |
| 1:45 | Souffler / mettre la main sur le DHT22 | « humidité en hausse rapide » |
| 2:15 | Ouvrir `report.html` | 0 fausse alarme, 20/20 pannes détectées, règle fixe 0/20 |

**Plan B si le réseau tombe** : `python -m sentinel_ai simulate --offline --scenario surchauffe_lente --speed 4`
montre l'IA détecter une surchauffe lente sur un boîtier virtuel, sans Wi-Fi ni broker.

## Questions probables du jury

**« Le sujet interdit les seuils. Votre score < 0, ce n'est pas un seuil ? »**
Le seuil n'est pas posé à la main sur un capteur : il est *appris* (quantile 1 % des scores normaux
sur une période de calibration) et porte sur un score multivarié. La preuve : la règle fixe
« temp > 40 ou gaz > 400 » ne détecte aucune de nos 20 pannes simulées, l'IA les détecte toutes.

**« Et l'enveloppe en écarts-types ? »**
Elle est apprise (1,5 × le plus grand écart vu en fonctionnement normal) et sur des dynamiques
relatives, pas sur des niveaux. Elle corrige une limite connue de l'Isolation Forest : il sature
hors de son domaine d'entraînement. Sans elle l'alerte retombait pendant un incident (45 % de maintien
contre 100 %) — c'est mesuré dans le rapport.

**« Pourquoi Isolation Forest ? »**
Benchmark de 4 algorithmes sur le même protocole : c'est le seul sans fausse alarme confirmée qui
détecte la surchauffe lente en moins de 30 s (LOF : 80 s, covariance robuste : 66 s, One-Class SVM :
plus rapide mais 18 fausses alarmes/heure).

**« Comment évaluez-vous sans vraies pannes ? »**
Session anomalie réelle (100 % détectée) + pannes simulées *ajoutées à de vraies mesures* (le bruit
réel du capteur est conservé), à 5 instants différents, sur une période jamais vue à l'entraînement.

**« Ça marchera dans une autre salle ? »**
Oui : le modèle apprend des écarts à une ligne de base adaptative, pas des niveaux absolus. Testé :
même période transposée à +3 °C / −10 % HR → toujours 5 % de mesures suspectes ; l'ancienne version
en déclenchait 100 %.

**« Et les fausses alertes ? »**
3 mesures anormales consécutives pour confirmer (6 s). Sur la période de test : 0 alarme à tort.
Les mesures isolées suspectes (5 %) viennent des glitchs de l'ADC du MQ-2, filtrés par la confirmation.

**« La vision tient le temps réel ? »**
YOLOv8n en 640×480 : ~50 ms par image sur le CPU (p95 57 ms), sous les 100 ms exigés. Confirmation
sur 3 images sur 5 contre les faux positifs. Benchmark dans `artifacts/vision/`.

**« Sécurité côté IA ? »**
MQTTS (TLS 1.2+, CA vérifiée), secrets hors Git (`.env`), identité du boîtier lue dans le topic,
messages validés, flux vidéo local par défaut ou avec jeton, modèle vérifié par SHA-256 avant
chargement, photos d'intrus supprimées après 7 jours (RGPD).
