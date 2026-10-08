# Model card — iforest-20261008-112651

**Tâche** : détection d'anomalies cinétiques (maintenance prédictive) sur la télémétrie du boîtier Sentinel-X (température, humidité, gaz MQ-2, une mesure / 2 s).  
**Algorithme** : Isolation Forest (scikit-learn 1.8.0), non supervisé, entraîné sur le fonctionnement normal uniquement.  
**Statut** : en production · SHA-256 `ec8b6b2c39abb0f7…`

## Entrées
Features calculées en flux (fenêtre 15 mesures, ligne de base demi-vie 150 mesures) : `temp_dev`, `hum_dev`, `gas_dev`, `d_temp`, `d_hum`, `d_gas`, `gas_std`.

## Sortie (topic `sentinel/<id>/anomaly`)
`score` (< 0 = anormal), `is_anomaly`, `streak`, `level` (normal/suspect/alarm), `causes` (features les plus anormales). Alarme confirmée après 3 anomalies consécutives.

## Données
1125 mesures valides (normal : 987, anomalie : 100, transition : 38), empreinte `8eb47cd2c8d825d5`. Split chronologique : train 583, calibration 194, test 195.

## Performances (données jamais vues)
- Alarmes confirmées à tort : 0 sur 6.5 min (5.1 % de mesures isolées suspectes)
- Session anomalie réelle : 100 % des mesures signalées, AUC 1.000
- Surchauffe lente + micro-dérive du gaz : 5/5, délai médian 26 s (règle fixe : 0/5)
- Fuite de gaz : 5/5, délai médian 6 s (règle fixe : 0/5)
- Départ de feu / choc thermique : 5/5, délai médian 8 s (règle fixe : 0/5)
- Infiltration d'eau / condensation : 5/5, délai médian 8 s (règle fixe : 0/5)
- Changement de salle : 5.1 % de mesures suspectes (ancienne version à niveaux absolus : 100.0 %)
- Retour à la normale après incident : 36 s
- Alerte maintenue pendant un incident qui dure : 100 % (sans enveloppe : 45 %)

## Enveloppe apprise
Chaque feature est bornée à 7.2 écarts-types (1,5 × le plus grand écart observé en fonctionnement normal) pour compenser la saturation de l'Isolation Forest hors de son domaine d'entraînement.

## Limites
- Peu de données (une seule salle, une matinée) ; scénarios de panne synthétiques.
- Gaz = valeur ADC brute non calibrée ; ne remplace pas un détecteur de gaz certifié.
- Le modèle détecte un écart au comportement habituel, pas la cause physique exacte.

## Contrôles qualité
- Alarmes à tort / heure (test) : 0.000 <= 2.0 → OK
- Mesures suspectes (test) : 0.051 <= 0.1 → OK
- Détection anomalie réelle : 1.000 >= 0.8 → OK
- Scénarios détectés : 1.000 >= 0.75 → OK
- Alerte maintenue (incident) : 1.000 >= 0.9 → OK
