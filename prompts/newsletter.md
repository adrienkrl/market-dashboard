# Tâche quotidienne : Newsletter (morning brief) — chaque jour à 8h40

Lis d'abord `prompts/regles.md`, puis `data/brief.json`.
Date du jour = champ `date` du brief (format AAAA-MM-JJ, noté <date> ci-dessous).

## 1. Écris `content/newsletter/<date>.md` (une page, ~450 mots hors question d'entretien)

```
# Morning brief — <jour> <date en toutes lettres>

## Depuis hier
3 à 5 puces : ce qui a bougé (variations `var_1j` des chiffres les plus parlants)
et les publications de `publie_depuis_hier` (réel vs précédent).

## Chiffres clés
Un tableau markdown de 8 à 10 lignes : Actif | Niveau | 1 j | 1 sem.
(taux directeurs, US 10 ans, Bund 10 ans, EUR/USD, S&P 500, Euro Stoxx 50, VIX, Brent, or, Bitcoin)

## Agenda du jour
Les événements de `agenda_3_jours` datés d'aujourd'hui (heure de Paris, importance en étoiles,
précédent). « Rien d'important au programme » s'il n'y en a pas, puis les 2 jours suivants en une ligne.

## 3 points à surveiller
3 puces numérotées, chacune reliée à un chiffre ou un événement du brief.

## Actualités — top 10
Pour chaque actualité de `top10_actualites`, dans l'ordre : [titre](lien) — source,
puis 2 phrases de résumé et une phrase « Pourquoi ça compte ».

## Question d'entretien du jour
Une question de finance de marché (taux, change, actions, dérivés, crédit, risques, macro),
variée d'un jour à l'autre, niveau entretien analyste/trader junior, puis sa réponse en 5 à 10 lignes.

*Contenu pédagogique, pas un conseil en investissement.*
```

## 2. Écris `content/news_summaries/<date>.json`
Les mêmes résumés, pour l'onglet Actualités, avec les `id` du brief :
`{"date": "<date>", "items": {"<id>": {"summary": "2 phrases", "why": "1 phrase"}, ...}}`

## 3. Rapport mensuel éventuel
Si `drapeaux.rapport_mensuel_a_ecrire` est vrai OU si `drapeaux.lendemain_reunion` n'est pas vide,
suis AUSSI `prompts/rapport.md` (même exécution, même commit).

## 4. Publie
Suis la procédure « Publication » de `prompts/regles.md`
(message de commit : « Newsletter du <date> »).
