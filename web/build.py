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
<link rel="stylesheet" href="static/style.css">
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
        "calendrier.html": ("Calendrier", placeholder("L'agent Calendrier arrive à l'étape 3.")),
        "actualites.html": ("Actualités", placeholder("L'agent Actualités arrive à l'étape 4.")),
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
