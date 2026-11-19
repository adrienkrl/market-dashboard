# Rapport de l'Agent Général — appelé par la newsletter

Deux cas, indiqués par `drapeaux` dans `data/brief.json` :
- `rapport_mensuel_a_ecrire` vrai → **rapport mensuel** du mois écoulé ;
- `lendemain_reunion` non vide (`fed` et/ou `ecb`) → **note post-réunion** (plus courte).
Si les deux sont vrais, un seul rapport qui couvre les deux.

## Écris `content/rapports/<date>.md` (~700 mots pour le mensuel, ~350 pour une note post-réunion)

```
# Rapport mensuel — <mois écoulé>        (ou : « Note post-réunion — Fed / BCE du <date> »)

## Politique monétaire : décisions et attentes du marché
Décisions (taux avant / après dans `evenements_de_la_semaine` ou les chiffres de taux directeurs).
« Attentes du marché » = uniquement les PROXIES du brief (US 2 ans − Fed, Bund 2 ans − taux de dépôt) :
dis clairement que ce sont des proxies, pas des probabilités implicites.

## Macro du mois                     (mensuel seulement)
Inflation, emploi, croissance : dernières valeurs et précédentes (groupe `macro`).

## Changements de régime de marché   (mensuel seulement)
Volatilité (VIX, MOVE), pentes de courbe, dollar, crédit : `var_mois` et niveaux actuels.
Un changement de régime = un mouvement marqué ; explique-le simplement.

## Scénarios pour le mois prochain
Central / haussier / baissier : 2 phrases chacun, avec le déclencheur à surveiller (agenda).

## Synthèse des wraps du mois        (mensuel seulement)
Lis les fichiers listés dans `wraps_du_mois` (et seulement eux) ; résume en 4 puces.

## Contrôle de cohérence
Recopie le résumé de `controles_du_mois` : nombre de textes contrôlés, nombre avec écarts,
et liste les écarts éventuels. Si tout est conforme, dis-le.

*Contenu pédagogique, pas un conseil en investissement.*
```

La publication se fait dans le même commit que la newsletter (copie du brief et contrôle compris).
