# Tâche hebdomadaire : Market Wrap — chaque vendredi à 22h30

Lis d'abord `prompts/regles.md`, puis `data/brief.json`.
Date = champ `date` du brief (<date>). Utilise surtout `var_1sem` (performances de la semaine),
`evenements_de_la_semaine` et `top10_actualites`.

## Écris `content/wraps/<date>.md` (une page, ~600 mots)

```
# Market Wrap — semaine du <lundi> au <date>

## En une phrase
Le thème dominant de la semaine.

## Performances de la semaine
Tableau markdown : Classe d'actifs | Actif | Niveau | Semaine | Depuis le 1er janvier
(2 à 3 lignes par classe, valeurs `valeur`, `var_1sem`, `var_ytd` recopiées du brief).

## Taux
## Change
## Actions
## Crédit
## Matières premières
## Volatilité
(un paragraphe de 3 à 5 phrases par classe : ce qui a bougé, et le moteur principal
— publication macro, banque centrale, actualité — tiré du brief. Crédit : seules les variations
sont disponibles (licence ICE), ne donne pas de niveau.)

## Moteurs de la semaine
3 puces : les événements qui ont fait le marché (avec réel vs précédent quand il y en a).

## Idée de trade pédagogique
- **Thèse** : …
- **Instrument** : … (ex. future, swap, option, ETF — sans recommandation personnalisée)
- **Risque principal** : …
- **Niveau d'invalidation** : … (niveau actuel recopié du brief ; seuil hypothétique signalé comme tel)

*Contenu pédagogique, pas un conseil en investissement.*
```

## Publie
Procédure « Publication » de `prompts/regles.md` (commit : « Market Wrap du <date> »).
