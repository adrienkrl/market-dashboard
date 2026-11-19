"""Générateur du site statique.

Lit les JSON de data/ et les textes de content/, et écrit des pages HTML
dans _site/ (publié ensuite sur GitHub Pages). Les mini-graphiques sont des
SVG calculés ici : aucune bibliothèque à charger, la page s'affiche même sans JavaScript.
"""
import html
import json
import os
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
DATA = os.path.join(ROOT, "data")
CONTENT = os.path.join(ROOT, "content")

def _css_version():
    """Empreinte du fichier CSS : change à chaque modification -> le navigateur recharge le style."""
    import hashlib
    with open(os.path.join(ROOT, "web", "static", "style.css"), "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:8]


CSS_VERSION = _css_version()

TABS = [
    ("index.html", "Tableau de bord"),
    ("calendrier.html", "Calendrier"),
    ("actualites.html", "Actualités"),
    ("newsletter.html", "Newsletter"),
    ("wraps.html", "Market Wraps"),
    ("rapports.html", "Rapports mensuels"),
]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


# ------------------------------------------------------------ formatage FR
def num(v, dec=2):
    if v is None:
        return "n.d."
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", "−")


def fdate(iso, monthly=False):
    y, m, d = iso[:10].split("-")
    if monthly:
        return f"{MOIS[int(m) - 1]} {y}"
    return f"{int(d)} {MOIS[int(m) - 1]} {y}"


def chg(v, kind):
    """Variation formatée + classe CSS (vert = hausse, rouge = baisse)."""
    if v is None:
        return '<span class="flat">—</span>'
    v = round(v, 0 if kind == "rate" else 2) + 0.0  # arrondi d'affichage, évite « −0 pb »
    cls = "up" if v > 0 else "down" if v < 0 else "flat"
    sign = "+" if v > 0 else ""
    if kind == "rate":
        txt = f"{sign}{num(v, 0)} pb"
    else:
        txt = f"{sign}{num(v, 2)} %"
    return f'<span class="{cls}">{txt}</span>'


def sparkline(points, w=120, h=32):
    vals = [p[1] for p in points if p[1] is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / rng * (h - 4):.1f}" for i, v in enumerate(vals))
    cls = "up" if vals[-1] >= vals[0] else "down"
    return (f'<svg class="spark {cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>')


# ------------------------------------------------------------ gabarit commun
def page(active, title, body, generated_at, alerts=""):
    nav = "".join(
        f'<a href="{href}"{" class=on aria-current=page" if href == active else ""}>{label}</a>'
        for href, label in TABS
    )
    ts = datetime.fromisoformat(generated_at)
    stamp = f"{ts:%d/%m/%Y à %H:%M} (Paris)"
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · Market Dashboard</title>
<link rel="stylesheet" href="static/style.css?v={CSS_VERSION}">
</head><body>
<header><div class="wrap">
 <div class="brand"><strong>Market Dashboard</strong><span class="stamp">Dernière mise à jour : {stamp}</span></div>
 <nav>{nav}</nav>
</div></header>
{alerts}
<main class="wrap">{body}</main>
<footer class="wrap">Usage personnel et pédagogique. Ceci n'est pas un conseil en investissement.
Les chiffres proviennent exclusivement des sources indiquées sur chaque tuile ; « n.d. » = non disponible.</footer>
</body></html>"""


def alert_banner(latest):
    errs = latest.get("errors") or {}
    if not errs:
        return ""
    labels = {t["id"]: t["label"] for t in latest["tiles"]}
    names = ", ".join(labels.get(k, k) for k in list(errs)[:6])
    more = f" et {len(errs) - 6} autre(s)" if len(errs) > 6 else ""
    return (f'<div class="alert wrap" role="status">⚠ {len(errs)} source(s) en erreur lors de la dernière mise à jour : '
            f'{html.escape(names)}{more}. Les autres données sont à jour ; les tuiles concernées affichent la dernière valeur connue ou « n.d. ».</div>')


# ------------------------------------------------------------ tableau de bord
def tile_html(t):
    kind, monthly = t["kind"], t.get("freq") in ("monthly", "quarterly")
    note = f'<p class="note">{html.escape(t["note"])}</p>' if t.get("note") else ""
    src = f'<p class="src">Source : {html.escape(t.get("source") or "—")}</p>'
    head = f'<h3>{html.escape(t["label"])}</h3>'

    if t["status"] == "na":
        return (f'<article class="tile na">{head}<p class="val">n.d.</p>'
                f'<p class="reason">{html.escape(t.get("reason", ""))}</p>{src}</article>')

    badge = ""
    if t["status"] == "stale":
        badge = f'<p class="reason">⏱ {html.escape(t.get("reason", ""))}</p>'

    if kind == "macro":
        dec = t.get("dec") if t.get("dec") is not None else 1
        unit = " %" if t.get("unit") == "%" else " k" if t.get("unit") == "k" else ""
        prev = (f'Précédent : {num(t.get("previous"), dec)}{unit} ({fdate(t["previous_date"], True)})'
                if t.get("previous") is not None else "Précédent : n.d.")
        when = fdate(t["date"], True) if t.get("freq") == "monthly" else f'T{(int(t["date"][5:7]) - 1) // 3 + 1} {t["date"][:4]}'
        return (f'<article class="tile">{head}<p class="val">{num(t["value"], dec)}{unit}</p>'
                f'<p class="meta">Période : {when}</p><p class="meta">{prev}</p>'
                f'{sparkline(t.get("spark") or [])}{badge}{note}{src}</article>')

    # valeur principale
    if t.get("restricted"):
        val = '<p class="val small">Niveau non affiché</p>'
        note = ('<p class="note">Licence ICE : republier le niveau est interdit. Seules les variations sont montrées ; '
                'niveau consultable sur FRED.</p>')
    elif t.get("display") == "fed_range" and t.get("range_low") is not None:
        val = f'<p class="val">{num(t["range_low"], 2)} – {num(t["value"], 2)} %</p>'
    elif t.get("show_bp"):
        val = f'<p class="val">{num(t["value"] * 100, 0)} pb</p>'
    elif kind == "rate":
        val = f'<p class="val">{num(t["value"], 2)} %</p>'
    else:
        dec = t.get("dec") if t.get("dec") is not None else 2
        val = f'<p class="val">{num(t["value"], dec)}</p>'

    if monthly:
        changes = (f'<dl class="chg"><div><dt>1 mois</dt><dd>{chg(t.get("chg_1m"), kind)}</dd></div>'
                   f'<div><dt>YTD</dt><dd>{chg(t.get("chg_ytd"), kind)}</dd></div></dl>')
        when = f'Mois : {fdate(t["date"], True)}'
    else:
        changes = (f'<dl class="chg"><div><dt>1 j</dt><dd>{chg(t.get("chg_1d"), kind)}</dd></div>'
                   f'<div><dt>1 sem.</dt><dd>{chg(t.get("chg_1w"), kind)}</dd></div>'
                   f'<div><dt>YTD</dt><dd>{chg(t.get("chg_ytd"), kind)}</dd></div></dl>')
        when = f'Donnée du {fdate(t["date"])}'
        if t.get("freq") == "event":
            when = f'En vigueur depuis le {fdate(t["date"])}'
        if t.get("fetched_at"):
            when = f'Séance du {fdate(t["date"])}, relevé à {t["fetched_at"]}'
    return (f'<article class="tile">{head}{val}{changes}'
            f'{sparkline(t.get("spark") or [])}<p class="meta">{when}</p>{badge}{note}{src}</article>')


def build_dashboard(latest):
    by_group = {}
    for t in latest["tiles"]:
        by_group.setdefault(t["group"], []).append(t)
    parts = ['<p class="legend">Vert = hausse, rouge = baisse. Taux et spreads : variations en points de base (pb). '
             'Mini-graphique : 3 mois (12 mois pour les séries mensuelles).</p>']
    for g in latest["groups"]:
        tiles = by_group.get(g["id"])
        if tiles:
            parts.append(f'<section><h2>{html.escape(g["label"])}</h2><div class="grid">'
                         + "".join(tile_html(t) for t in tiles) + "</div></section>")
    return "".join(parts)


def placeholder(text):
    return f'<section class="empty"><p>{text}</p></section>'


# ------------------------------------------------------------ calendrier
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _v(x, unit="%", dec=2):
    if x is None:
        return '<span class="flat">n.d.</span>'
    if unit == "k":
        return f"{num(x, 0)} k"
    return f"{num(x, dec)} %"


def _surprise(x, unit):
    if x is None:
        return '<span class="flat">—</span>'
    cls = "up" if x > 0 else "down" if x < 0 else "flat"
    sign = "+" if x > 0 else ""
    txt = f"{sign}{num(x, 0)} k" if unit == "k" else f"{sign}{num(x, 2)} pt"
    return f'<span class="{cls}">{txt}</span>'


def event_rows(ev, now):
    """Une ou plusieurs lignes par événement (ex. CPI global + core)."""
    t = ev.get("time_paris")
    released = bool(t) and datetime.fromisoformat(t) <= now
    hour = datetime.fromisoformat(t).strftime("%H:%M") if t else "—"
    stars = f'<span class="stars" aria-label="importance {ev["stars"]} sur 3">{"★" * ev["stars"]}{"☆" * (3 - ev["stars"])}</span>'
    link = f'<a href="{html.escape(ev["url"])}" rel="noopener" target="_blank">{html.escape(ev["label"])}</a>'
    note = f'<div class="note">{html.escape(ev["note"])}</div>' if ev.get("note") else ""
    pending = '<span class="flat">en attente</span>' if released else '<span class="flat">—</span>'
    rows = []

    def row(name, prev, act, surp, first):
        lead = (f'<td class="time">{hour}</td><td>{stars}</td><td class="ev">{link}{name}{note}</td>' if first
                else '<td></td><td></td><td class="ev sub">' + name + '</td>')
        return (f'<tr class="{"done" if released else ""}">{lead}<td>{prev}</td>'
                f'<td class="flat" title="Aucune source gratuite de consensus">n.d.</td><td>{act}</td><td>{surp}</td></tr>')

    if ev["kind"] == "macro" and ev.get("values"):
        for i, (sid, v) in enumerate(ev["values"].items()):
            unit, dec = v.get("unit") or "%", 0 if v.get("unit") == "k" else 1
            name = f'<div class="sub">{html.escape(v["label"])}</div>' if len(ev["values"]) > 1 else ""
            act = _v(v.get("actual"), unit, dec) if v.get("actual") is not None else pending
            rows.append(row(name, _v(v.get("previous"), unit, dec), act, _surprise(v.get("surprise_vs_prev"), unit), i == 0))
    elif ev["kind"] == "cb":
        def rate(val, low):
            if val is None:
                return '<span class="flat">n.d.</span>'
            return f"{num(low, 2)} – {num(val, 2)} %" if low is not None else f"{num(val, 2)} %"
        act = rate(ev.get("actual"), ev.get("actual_low")) if ev.get("actual") is not None else pending
        ch = ev.get("change_bp")
        surp = ('<span class="flat">inchangé</span>' if ch == 0 else
                f'<span class="{"up" if ch > 0 else "down"}">{"+" if ch > 0 else ""}{ch} pb</span>' if ch is not None
                else '<span class="flat">—</span>')
        rows.append(row("", rate(ev.get("previous"), ev.get("previous_low")), act, surp, True))
    elif ev["kind"] == "auction":
        prev = _v(ev.get("previous"), "%", 3)
        act = _v(ev.get("actual"), "%", 3) if ev.get("actual") is not None else pending
        if ev.get("bid_to_cover"):
            act += f'<div class="sub">bid-to-cover {num(ev["bid_to_cover"], 2)}</div>'
        ch = ev.get("change_bp")
        surp = (f'<span class="{"up" if ch > 0 else "down" if ch < 0 else "flat"}">{"+" if ch > 0 else ""}{num(ch, 1)} pb</span>'
                if ch is not None else '<span class="flat">—</span>')
        rows.append(row("", prev, act, surp, True))
    else:
        rows.append(row("", '<span class="flat">n.d.</span>', pending, '<span class="flat">—</span>', True))
    return "".join(rows)


def build_calendar(cal):
    if not cal:
        return placeholder("Calendrier pas encore généré.")
    now = datetime.fromisoformat(cal["updated_at"])
    today = now.date().isoformat()
    days = {}
    for ev in cal["events"]:
        days.setdefault(ev["date"], []).append(ev)
    head = ('<thead><tr><th>Heure</th><th>Imp.</th><th>Événement</th><th>Précédent</th>'
            '<th>Consensus</th><th>Réel</th><th>Réel − préc.</th></tr></thead>')

    def block(title, keys):
        out = [f"<section><h2>{title}</h2>"]
        if not keys:
            out.append('<p class="legend">Aucun événement suivi sur la période.</p>')
        for d in keys:
            dd = date_from_iso(d)
            label = f'{JOURS[dd.weekday()].capitalize()} {fdate(d)}' + (" · aujourd'hui" if d == today else "")
            out.append(f'<h3 class="day">{label}</h3><div class="tablewrap"><table class="cal">{head}<tbody>'
                       + "".join(event_rows(e, now) for e in days[d]) + "</tbody></table></div>")
        out.append("</section>")
        return "".join(out)

    upcoming = sorted(d for d in days if d >= today)
    past = sorted((d for d in days if d < today), reverse=True)
    info = "".join(f"<li>{html.escape(m)}</li>" for m in cal.get("missing", []))
    warns = "".join(f"<li>{html.escape(w)}</li>" for w in cal.get("warnings", []))
    intro = ('<p class="legend">Heures de Paris. Importance : ★★★ forte, ★★ moyenne, ★ faible. '
             'Taux d\'une adjudication = rendement le plus haut servi (« high yield »). '
             'Valeurs réelles reprises de l\'agent Données dès que la source officielle les publie.</p>')
    notes = f'<details class="notes"><summary>Limites des sources</summary><ul>{info}{warns}</ul></details>'
    return intro + block("À venir — 14 jours", upcoming) + block("Publiés — 7 derniers jours", past) + notes


def date_from_iso(s):
    return datetime.fromisoformat(s).date()


# ------------------------------------------------------------ actualités
def _summaries():
    """Résumés du top 10 rédigés chaque matin par la tâche Newsletter (content/news_summaries/*.json)."""
    folder = os.path.join(CONTENT, "news_summaries")
    out = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder))[-3:]:
            if name.endswith(".json"):
                with open(os.path.join(folder, name)) as f:
                    out.update(json.load(f).get("items", {}))
    return out


def _news_line(it, rank=None, summary=None):
    t = datetime.fromisoformat(it["published"])
    dots = f'<span class="score s{it["score"]}" title="Note {it["score"]}/5">{it["score"]}</span>'
    chips = "".join(f'<span class="chip">{html.escape(c)}</span>' for c in it.get("themes", [])[:3])
    also = (f' <span class="also">· aussi : {html.escape(", ".join(it["also"][:3]))}</span>' if it.get("also") else "")
    extra = ""
    if summary:
        extra = (f'<p class="sum">{html.escape(summary.get("summary", ""))}</p>'
                 f'<p class="why"><strong>Pourquoi ça compte :</strong> {html.escape(summary.get("why", ""))}</p>')
    elif rank:
        extra = '<p class="sum flat">Résumé ajouté chaque matin par la newsletter.</p>'
    num_ = f'<span class="rank">{rank}</span>' if rank else ""
    return (f'<li class="news">{num_}{dots}<div class="nbody"><a href="{html.escape(it["link"])}" target="_blank" '
            f'rel="noopener">{html.escape(it["title"])}</a><div class="nmeta">{html.escape(it["source"])} · '
            f'{t:%d/%m %H:%M}{also}</div><div class="chips">{chips}</div>{extra}</div></li>')


def build_news(news):
    if not news or not news.get("items"):
        return placeholder("Pas encore d'actualités collectées.")
    items, sums = news["items"], _summaries()
    top = items[:10]
    rest = items[10:]
    intro = ('<p class="legend">Note de 1 à 5 calculée par des règles, sans IA : fiabilité de la source, thèmes '
             '(banque centrale, inflation, emploi, risque…), actifs cités, reprise par plusieurs sources. '
             f'Fenêtre : {news.get("keep_hours", 48)} h. Seuls le titre et le lien sont repris ; l\'article reste chez son éditeur.</p>')
    errs = news.get("errors") or {}
    warn = (f'<p class="reason">Flux indisponibles lors de la dernière collecte : {html.escape(", ".join(errs))}.</p>'
            if errs else "")
    body = [intro, warn, '<section><h2>Top 10</h2><ol class="newslist top">']
    body += [_news_line(it, i + 1, sums.get(it["id"])) for i, it in enumerate(top)]
    body.append('</ol></section><section><h2>Toutes les actualités</h2><ul class="newslist">')
    body += [_news_line(it) for it in rest]
    body.append("</ul></section>")
    srcs = ", ".join(html.escape(s) for s in news.get("feeds", []))
    body.append(f'<details class="notes"><summary>Sources suivies</summary><p>{srcs}</p></details>')
    return "".join(body)


def _load_json(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def main():
    with open(os.path.join(DATA, "latest.json")) as f:
        latest = json.load(f)
    gen = latest["generated_at"]
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "web", "static"), os.path.join(OUT, "static"))
    shutil.copy(os.path.join(DATA, "latest.json"), os.path.join(OUT, "latest.json"))
    alerts = alert_banner(latest)

    pages = {
        "index.html": ("Tableau de bord", build_dashboard(latest)),
        "calendrier.html": ("Calendrier", build_calendar(_load_json("calendar.json"))),
        "actualites.html": ("Actualités", build_news(_load_json("news.json"))),
        "newsletter.html": ("Newsletter", placeholder("Les newsletters apparaîtront ici à partir de l'étape 6.")),
        "wraps.html": ("Market Wraps", placeholder("Les market wraps apparaîtront ici à partir de l'étape 6.")),
        "rapports.html": ("Rapports mensuels", placeholder("Les rapports mensuels apparaîtront ici à partir de l'étape 6.")),
    }
    for href, (title, body) in pages.items():
        with open(os.path.join(OUT, href), "w") as f:
            f.write(page(href, title, body, gen, alerts if href == "index.html" else ""))
    open(os.path.join(OUT, ".nojekyll"), "w").close()
    print(f"[site] {len(pages)} pages générées dans _site/")


if __name__ == "__main__":
    main()
