# Market Dashboard — marchés & macro, alimenté par des agents

**Site : https://adrienkrl.github.io/market-dashboard/**

Dashboard personnel et pédagogique, mis à jour **toutes les heures de 8h à 23h (heure de Paris)** :
taux, change, actions, volatilité, crédit, matières premières, macro, calendrier économique,
actualités classées, newsletter quotidienne, market wrap hebdomadaire et rapport mensuel.

> Usage personnel et pédagogique. Ce n'est pas un conseil en investissement.

---

## En une phrase (pour un entretien)
Un pipeline de données gratuit et automatisé : **des agents Python sans IA** collectent et contrôlent
les chiffres chaque heure sur GitHub Actions, et **des agents Claude** rédigent les textes à partir de
ces seuls chiffres. **Un contrôle automatique vérifie ensuite chaque chiffre cité.**

## Architecture

```
                        ┌──────────── GitHub Actions (gratuit, sans IA) ────────────┐
   API officielles      │  cron horaire (UTC) → orchestrator.py (vérifie l'heure de Paris) │
   FRED, BCE, Eurostat, │                                                                  │
   Bundesbank, BoE,  ──►│  1. Agent Données     → data/latest.json + data/history/         │
   BoJ, MoF Japon,      │  2. Agent Calendrier  → data/calendar.json                       │
   TreasuryDirect,      │  3. Agent Actualités  → data/news.json                           │
   Yahoo, flux RSS      │  4. Dossier de brief  → data/brief.json  (+ empreinte SHA-256)   │
                        │  5. Site statique     → GitHub Pages                             │
                        └───────────────────────────────┬──────────────────────────────────┘
                                                        │ lit data/brief.json uniquement
                        ┌───────────── Tâches Claude programmées (abonnement Pro) ──────────┐
                        │  Newsletter  : chaque jour 8h40 (+ rapport mensuel si drapeau)     │
                        │  Market Wrap : vendredi 22h30                                      │
                        │  → écrivent content/…  → checks/coherence.py → git push → site     │
                        └────────────────────────────────────────────────────────────────────┘
```

| Dossier / fichier | Rôle |
|---|---|
| `orchestrator.py` | Décide quels agents tournent selon l'heure, isole les erreurs, tient le journal `data/logs/runs.jsonl` |
| `agents/sources.py` | Un connecteur par source de données (avec nouvelles tentatives) |
| `agents/catalog.py` | Les 66 données suivies : source, unité, fréquence, règles d'affichage |
| `agents/data.py` | **Agent Données** : collecte, historique, variations 1 j / 1 sem. / YTD, mini-graphique 3 mois |
| `agents/calendar.py` | **Agent Calendrier** : événements à 14 jours, précédent, réel, réel − précédent |
| `agents/news.py` | **Agent Actualités** : RSS, dédoublonnage, note 1-5 par règles |
| `agents/brief.py` | Dossier de chiffres pour les textes, avec empreinte anti-modification |
| `checks/coherence.py` | **Contrôle de cohérence** : tout chiffre cité doit exister dans le brief |
| `prompts/` | Consignes des tâches Claude (modifiables sans recréer les tâches) |
| `content/` | Textes rédigés (newsletter, wraps, rapports, résumés) + copie du brief utilisé |
| `config/central_banks.json` | Dates officielles des réunions Fed, BCE, BoE, BoJ |
| `web/` | Générateur du site (HTML/CSS, mini-graphiques SVG sans bibliothèque) |
| `tests/` | 25 tests automatiques |

## Sources de données
| Données | Source | Accès | Fréquence réelle |
|---|---|---|---|
| Fed (fourchette), SOFR, Treasuries 2/10/30 ans, 2s10s US, point mort 10 ans, CPI, PCE, NFP, chômage, PIB US | FRED (Fed de St. Louis) | API gratuite, clé dans GitHub Secrets | quotidienne (J+1) / à la publication |
| Spreads OAS IG/HY US, HY euro | FRED / ICE BofA | idem — **licence ICE : seules les variations sont affichées** | quotidienne |
| Taux de dépôt BCE, €STR, Euribor 3M, taux longs OAT/BTP/Bund | ECB Data Portal | API sans clé | quotidienne / **mensuelle** (Euribor, OAT, BTP) |
| Bund 2 et 10 ans | Bundesbank | API sans clé | quotidienne |
| Bank Rate, Gilt 10 ans | Bank of England (IADB) | CSV sans clé | quotidienne |
| Taux call BoJ / JGB 10 ans | Banque du Japon (API 2026) / ministère des Finances japonais | sans clé | quotidienne |
| HICP, inflation France (IPCH), chômage et PIB zone euro | Eurostat | API sans clé | à la publication |
| Change, indices actions, VIX, MOVE, matières premières, Bitcoin | Yahoo Finance via `yfinance` | non officiel, usage personnel | différé ~15 min |
| Calendrier banques centrales | Sites officiels Fed, BCE, BoE, BoJ | — | annuelle |
| Calendrier macro | FRED (US), Eurostat (iCal) | — | — |
| Adjudications US | TreasuryDirect | API sans clé | à l'annonce / au résultat |
| Actualités | 15 flux RSS (Fed, BCE, BoE, BoJ, FT, CNBC, MarketWatch, BBC, Guardian, Le Monde, La Tribune, BFM) | titre + lien uniquement | horaire |

**Affiché « n.d. » faute de source gratuite fiable** : VSTOXX, OAS IG euro / iTraxx, PIB Chine, PMI,
consensus des économistes (la colonne « surprise » est donc *réel − précédent*), calendrier INSEE.
**Proxies signalés comme tels** : anticipations de taux = 2 ans − taux directeur ; MSCI EM = ETF EEM.

## Calendrier d'exécution (heure de Paris)
| Quand | Quoi | Où |
|---|---|---|
| Toutes les heures, 8h17 → 23h17 | Données, actualités, résultats du calendrier, brief, site | GitHub Actions |
| 8h17 | + reconstruction complète du calendrier | GitHub Actions |
| 8h40 | Newsletter (+ rapport mensuel le 1er jour ouvré, note le lendemain d'une réunion Fed/BCE) | Tâche Claude |
| Vendredi 22h30 | Market Wrap | Tâche Claude |
| 0h → 8h | Rien | — |

Le cron GitHub est en UTC (`17 6-22 * * *`) : l'orchestrateur vérifie l'heure de Paris, ce qui gère
l'heure d'été/hiver. Minute 17 : GitHub retarde les tâches lancées pile à l'heure.

## Garanties « aucun chiffre inventé »
1. Les chiffres viennent **uniquement des API** ; une source en panne → « n.d. » + bandeau d'alerte.
2. Une valeur publiée n'est attribuée à un événement que si la source affiche **une nouvelle période**.
3. Claude ne lit que `data/brief.json`. Chaque texte est publié avec la **copie du brief utilisé**,
   protégée par une **empreinte SHA-256**.
4. `checks/coherence.py` vérifie chaque chiffre cité ; le site affiche un badge vert ou orange.
5. Bandeau « site pas à jour » si l'automatisation s'arrête plus de 2 h 30 en journée.

## Comment vérifier que tout marche
- **Site** : l'horodatage « Dernière mise à jour » avance chaque heure.
- **GitHub → Actions** : « Mise à jour du dashboard » (une exécution par heure) et « Tests ».
- **Tâches Claude** : https://claude.ai/code/routines (historique des exécutions).
- **Journal** : `data/logs/runs.jsonl` (une ligne par passage, avec les erreurs éventuelles).
- **Tests en local** : `pip install -r requirements.txt pytest && python -m pytest -q`

## Modifier
- Ajouter une donnée : une ligne dans `agents/catalog.py`.
- Ajouter un flux d'actualités : une ligne dans `FEEDS` de `agents/news.py`.
- Changer le style d'un texte : modifier le fichier de `prompts/` correspondant.
- Nouvelles dates de banques centrales : `config/central_banks.json` (le calendrier prévient quand il s'épuise).
- Lancer une mise à jour à la main : GitHub → Actions → « Mise à jour du dashboard » → *Run workflow*.

## Budget
0 € : dépôt public (GitHub Actions et Pages gratuits), API gratuites, textes rédigés sur l'abonnement
Claude Pro (≈ 1 exécution par jour + 1 par semaine, modèle Sonnet, sans connecteur).

## Limites connues
- `yfinance` est non officiel : Yahoo peut le bloquer → tuiles « n.d. » jusqu'au retour.
- Les tâches Claude programmées sont en *research preview* : leur fonctionnement peut évoluer.
- La note des actualités est fondée sur des règles : explicable, mais elle rate les nuances.
- GitHub désactive les tâches planifiées après 60 jours sans activité du dépôt ; les commits
  horaires de données l'en empêchent.

## Concepts appris (glossaire d'entretien)
- **Agent** : programme autonome avec un rôle, des outils et des règles (ici 3 agents sans IA, 3 avec).
- **ETL** : *Extract* (API), *Transform* (variations, spreads), *Load* (JSON lu par le site).
- **API** : adresse web qui renvoie des données brutes au lieu d'une page.
- **CI/CD** : GitHub Actions exécute, teste et publie le code automatiquement.
- **Orchestration et idempotence** : l'ordre des agents est fixé ; relancer un passage ne casse rien.
- **Source unique de vérité** : chaque chiffre n'est produit qu'à un seul endroit.
- **Séparation génération / contrôle** : l'IA rédige, un contrôle indépendant vérifie (« quatre yeux »).
- **Système à règles vs apprentissage** : explicabilité contre performance.
