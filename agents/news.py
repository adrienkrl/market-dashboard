"""AGENT ACTUALITÉS — sans IA.

1. Lit les flux RSS (banques centrales et médias économiques).
2. Supprime les doublons (même lien, ou titres très proches d'une source à l'autre).
3. Note chaque actualité de 1 à 5 avec des règles transparentes (voir score()).
4. Conserve 48 h dans data/news.json.

Droit d'auteur : on ne garde que titre, lien, source et heure — jamais le texte de l'article.
Les résumés du top 10 sont ajoutés le matin par la tâche Newsletter (content/news_summaries/).
"""
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import feedparser

from agents.sources import _get

PARIS = ZoneInfo("Europe/Paris")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "news.json")
KEEP_HOURS = 48

# Fiabilité : 3 = source officielle, 2 = grand média économique, 1 = autre média
FEEDS = [
    ("Fed – communiqués", 3, "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("Fed – discours", 3, "https://www.federalreserve.gov/feeds/speeches.xml"),
    ("BCE – communiqués", 3, "https://www.ecb.europa.eu/rss/press.html"),
    ("BCE – blog", 3, "https://www.ecb.europa.eu/rss/blog.html"),
    ("Bank of England", 3, "https://www.bankofengland.co.uk/rss/news"),
    ("Banque du Japon", 3, "https://www.boj.or.jp/en/rss/whatsnew.xml"),
    ("Financial Times", 2, "https://www.ft.com/markets?format=rss"),
    ("CNBC – marchés", 2, "https://www.cnbc.com/id/15839069/device/rss/rss.html"),
    ("CNBC – économie", 2, "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("MarketWatch", 2, "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("BBC Business", 2, "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("The Guardian – business", 2, "https://www.theguardian.com/uk/business/rss"),
    ("Le Monde – économie", 2, "https://www.lemonde.fr/economie/rss_full.xml"),
    ("La Tribune", 1, "https://www.latribune.fr/feed.xml"),
    ("BFM Bourse", 1, "https://www.tradingsat.com/rssbourse.xml"),
]

# Mots-clés (minuscules, sans accents). Chaque thème rapporte des points une seule fois.
THEMES = {
    "Banque centrale": (1.5, ["fed", "fomc", "powell", "ecb", "bce", "lagarde", "bank of england", "boe",
                              "bank of japan", "boj", "ueda", "rate cut", "rate hike", "baisse des taux",
                              "hausse des taux", "taux directeur", "monetary policy", "politique monetaire",
                              "interest rate", "central bank", "banque centrale", "quantitative"]),
    "Inflation": (1.0, ["inflation", "cpi", "pce", "hicp", "ipch", "prix a la consommation", "consumer prices",
                        "deflation", "desinflation", "disinflation"]),
    "Emploi & croissance": (1.0, ["payrolls", "nfp", "jobs report", "unemployment", "chomage", "emploi",
                                  "labor market", "labour market", "gdp", "pib", "growth", "croissance", "pmi",
                                  "retail sales", "ventes au detail"]),
    "Risque & crédit": (1.5, ["default", "defaut", "recession", "crisis", "crise", "bankruptcy", "faillite",
                              "downgrade", "degradation", "contagion", "bailout", "sell-off", "selloff", "krach",
                              "crash", "credit spread", "junk", "high yield"]),
    "Marchés": (0.5, ["stocks", "shares", "equities", "wall street", "ipo", "earnings", "bourse", "actions",
                      "marches", "markets", "rally", "investors", "investisseurs"]),
    "Budget & souverains": (0.5, ["bond", "treasury", "treasuries", "yield", "obligat", "oat", "bund", "gilt",
                                  "deficit", "budget", "dette", "debt"]),
}
# Publications qui font bouger les marchés : gros bonus
KEY_EVENTS = ["minutes of the federal open market", "fomc statement", "monetary policy decision",
              "decision de politique monetaire", "rate decision", "monetary policy statement",
              "press conference", "conference de presse", "monetary policy report", "financial stability review",
              "outlook report", "statement on monetary policy", "beige book", "testimony", "semiannual monetary"]
# Contenus peu utiles pour un desk (administratif, conseils perso, podcasts) : malus
NOISE = ["podcast", "enforcement action", "consultation", "careers", "should i ", "should we ", "how to ",
         "quiz", "obituary", "recette", "appoint", "nomination", "museum", "banknote", "billet de banque",
         "market participants group", "interiors", "video:", "live:", "newsletter"]
ASSETS = ["s&p 500", "nasdaq", "dow jones", "cac 40", "dax", "stoxx", "ftse", "nikkei", "hang seng",
          "dollar", "euro", "yen", "yuan", "sterling", "livre sterling", "bitcoin", "brent", "wti", "oil",
          "petrole", "gold", "copper", "cuivre", "gas", "gaz", "vix"]


def _norm(text):
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def _tokens(title):
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(title))}


def score(item):
    """Note de 1 à 5 = fiabilité de la source + thèmes de marché + actifs cités + reprise par plusieurs sources."""
    text = " " + _norm(item["title"] + " " + item.get("summary_hint", "")) + " "
    pts = {3: 1.5, 2: 1.0, 1: 0.5}[item["reliability"]]
    themes = []
    for name, (w, words) in THEMES.items():
        if any(re.search(r"(?<![a-z])" + re.escape(k), text) for k in words):
            pts += w
            themes.append(name)
    assets = [a for a in ASSETS if re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", text)]
    pts += min(len(assets), 2) * 0.5
    if any(k in text for k in KEY_EVENTS):
        pts += 1.5
        themes.insert(0, "Événement clé")
    if any(k in text for k in NOISE) or _norm(item["title"]).rstrip().endswith("?") and item["reliability"] < 3:
        pts -= 1.5
    if item.get("also"):
        pts += 0.5  # reprise par une autre source = sujet important
    item["themes"] = themes
    item["assets"] = assets[:4]
    return max(1, min(5, round(pts)))


def _when(entry):
    for k in ("published_parsed", "updated_parsed"):
        if entry.get(k):
            return datetime(*entry[k][:6], tzinfo=timezone.utc)
    return None


def collect(errors):
    items = []
    for name, rel, url in FEEDS:
        try:
            feed = feedparser.parse(_get(url).content)
            if not feed.entries:
                raise RuntimeError("flux vide ou illisible")
        except Exception as e:  # noqa: BLE001 — une source en panne n'arrête pas les autres
            errors[name] = str(e)[:120]
            continue
        for en in feed.entries[:40]:
            link, title = en.get("link"), (en.get("title") or "").strip()
            when = _when(en)
            if not (link and title and when):
                continue
            # On lit le chapô du flux uniquement pour détecter des mots-clés ; il n'est PAS stocké.
            hint = re.sub(r"<[^>]+>", " ", en.get("summary", ""))[:300]
            items.append(dict(id=hashlib.sha1(link.encode()).hexdigest()[:12], title=title, link=link,
                              source=name, reliability=rel, published=when.astimezone(PARIS).isoformat(timespec="minutes"),
                              summary_hint=hint))
    return items


def dedupe(items):
    """Garde un seul exemplaire par sujet : priorité à la source la plus fiable, puis la plus ancienne."""
    items.sort(key=lambda i: (-i["reliability"], i["published"]))
    kept = []
    for it in items:
        toks = _tokens(it["title"])
        dup = None
        for k in kept:
            if k["link"] == it["link"]:
                dup = k
                break
            kt = k["_tok"]
            if toks and kt and len(toks & kt) / len(toks | kt) >= 0.6:
                dup = k
                break
        if dup:
            if it["source"] != dup["source"] and it["source"] not in dup.setdefault("also", []):
                dup["also"].append(it["source"])
            continue
        it["_tok"] = toks
        kept.append(it)
    for k in kept:
        k.pop("_tok", None)
    return kept


def run(log=print):
    now = datetime.now(PARIS)
    cutoff = (now - timedelta(hours=KEEP_HOURS)).isoformat()
    errors = {}
    fresh = [i for i in collect(errors) if i["published"] >= cutoff]

    old = []
    if os.path.exists(OUT):
        with open(OUT) as f:
            old = [i for i in json.load(f).get("items", []) if i["published"] >= cutoff]
    # Une actualité déjà notée garde sa note (son chapô n'est plus stocké) ;
    # les nouvelles sont notées avec leur titre + chapô.
    prev = {i["id"]: i for i in old}
    by_id = {i["id"]: i for i in old}
    for i in fresh:
        if i["id"] not in by_id:
            by_id[i["id"]] = i
    items = dedupe(list(by_id.values()))
    for it in items:
        if "score" not in it:
            it["score"] = score(it)
            it["first_seen"] = now.isoformat(timespec="minutes")
        elif it.get("also") and not prev.get(it["id"], {}).get("also"):
            it["score"] = min(5, it["score"] + 1)  # nouvellement reprise par une autre source
        it.pop("summary_hint", None)
    # Classement : note décroissante, puis la plus récente d'abord
    items.sort(key=lambda i: (i["score"], i["published"]), reverse=True)

    out = {"updated_at": now.isoformat(timespec="minutes"), "keep_hours": KEEP_HOURS,
           "items": items, "errors": errors, "feeds": [f[0] for f in FEEDS]}
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"[actualités] {len(items)} actualités sur 48 h, {len(errors)} flux en erreur")
    return out


if __name__ == "__main__":
    run()
