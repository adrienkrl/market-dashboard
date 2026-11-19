"""DOSSIER DE BRIEF — sans IA.

Prépare, à chaque passage, un petit fichier data/brief.json (quelques Ko) qui contient
TOUT ce dont les tâches Claude ont besoin : chiffres clés déjà formatés, agenda, résultats
publiés, top 10 des actualités, performances de la semaine et du mois, et des drapeaux
(rapport mensuel à écrire ? lendemain de réunion Fed/BCE ?).

Pourquoi : Claude ne lit que ce fichier -> tâche courte, peu de quota consommé,
et surtout Claude n'a accès qu'à des chiffres produits par le code.
"""
import hashlib
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.data import asof, load_history

PARIS = ZoneInfo("Europe/Paris")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "brief.json")


def _load(name, default=None):
    p = os.path.join(DATA, name) if not os.path.isabs(name) else name
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def fr(x, dec=2, sign=False, unit=""):
    """Format français, identique à celui du site (virgule décimale)."""
    if x is None:
        return None
    s = f"{x:+,.{dec}f}" if sign else f"{x:,.{dec}f}"
    return s.replace(",", " ").replace(".", ",") + unit


def _chg_txt(v, kind):
    if v is None:
        return None
    return fr(v, 0, True, " pb") if kind == "rate" else fr(v, 2, True, " %")


def _value_txt(t):
    if t.get("restricted") or t.get("value") is None:
        return None
    if t.get("display") == "fed_range" and t.get("range_low") is not None:
        return f'{fr(t["range_low"])} – {fr(t["value"])} %'
    if t.get("show_bp"):
        return fr(t["value"] * 100, 0, unit=" pb")
    if t["kind"] == "rate":
        return fr(t["value"], 2, unit=" %")
    if t["kind"] == "macro":
        d = t.get("dec") if t.get("dec") is not None else 1
        return fr(t["value"], d, unit=" k" if t.get("unit") == "k" else " %")
    d = t.get("dec") if t.get("dec") is not None else 2
    return fr(t["value"], d)


def fingerprint(brief):
    """Empreinte SHA-256 du contenu : toute modification du fichier la rend invalide."""
    body = {k: v for k, v in brief.items() if k != "empreinte"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def first_business_day(d):
    x = d.replace(day=1)
    while x.weekday() >= 5:
        x += timedelta(days=1)
    return x


def _controls(today, monthly_due):
    """Résumé du contrôle de cohérence des textes du mois (lu par l'Agent Général)."""
    from checks.coherence import check_all
    month = (today.replace(day=1) - timedelta(days=1)) if monthly_due else today
    res = check_all(prefix=month.strftime("%Y-%m"))
    return {"mois": month.strftime("%Y-%m"), "textes_controles": len(res),
            "textes_avec_ecarts": sum(not r["ok"] for r in res),
            "ecarts": [{"fichier": r["fichier"], "inconnus": [u["nombre"] for u in r["inconnus"]][:10],
                        "brief_valide": r.get("brief_valide")} for r in res if not r["ok"]][:20]}


def build(log=print):
    now = datetime.now(PARIS)
    today = now.date()
    latest = _load("latest.json", {})
    cal = _load("calendar.json", {"events": []})
    news = _load("news.json", {"items": []})
    cb = _load(os.path.join(ROOT, "config", "central_banks.json"), {"banks": {}})

    # ---- chiffres clés (uniquement ceux disponibles) + variation depuis le début du mois
    month_start = (today.replace(day=1) - timedelta(days=1)).isoformat()
    figures, unavailable = [], []
    for t in latest.get("tiles", []):
        if t["status"] == "na":
            unavailable.append({"label": t["label"], "raison": t.get("reason")})
            continue
        f = {"id": t["id"], "groupe": t["group"], "libelle": t["label"], "date": t.get("date"),
             "valeur": _value_txt(t)}
        if t["kind"] == "macro":
            f["precedent"] = (fr(t["previous"], t.get("dec") if t.get("dec") is not None else 1,
                                 unit=" k" if t.get("unit") == "k" else " %") if t.get("previous") is not None else None)
        else:
            f.update(var_1j=_chg_txt(t.get("chg_1d"), t["kind"]), var_1sem=_chg_txt(t.get("chg_1w"), t["kind"]),
                     var_ytd=_chg_txt(t.get("chg_ytd"), t["kind"]))
            if t.get("freq") == "monthly":
                f["var_1mois"] = _chg_txt(t.get("chg_1m"), t["kind"])
            hist = load_history(t["id"]) if not t.get("restricted") else []
            ref = asof(hist, month_start) if hist else None
            if ref and t.get("value") is not None and t.get("freq") in ("daily", "event"):
                v = t["value"]
                f["var_mois"] = _chg_txt((v - ref[1]) * 100 if t["kind"] == "rate" else (v / ref[1] - 1) * 100,
                                         t["kind"])
        if t["status"] == "stale":
            f["attention"] = t.get("reason")
        figures.append({k: v for k, v in f.items() if v is not None})

    # ---- agenda et résultats
    def ev_view(e):
        v = {"date": e["date"], "heure_paris": (e.get("time_paris") or "")[11:16] or None,
             "evenement": e["label"], "importance": e["stars"], "consensus": "n.d."}
        if e["kind"] == "macro":
            for sid, x in (e.get("values") or {}).items():
                u, d = (" k", 0) if x.get("unit") == "k" else (" %", 1)
                v.setdefault("valeurs", []).append({k: val for k, val in {
                    "serie": x["label"], "precedent": fr(x.get("previous"), d, unit=u),
                    "reel": fr(x.get("actual"), d, unit=u),
                    "reel_moins_precedent": fr(x.get("surprise_vs_prev"), d, True, u.replace("%", "pt"))}.items()
                    if val is not None})
        elif e["kind"] == "cb":
            v.update({k: val for k, val in {"taux_avant": fr(e.get("previous"), 2, unit=" %"),
                                            "taux_apres": fr(e.get("actual"), 2, unit=" %"),
                                            "variation": fr(e.get("change_bp"), 0, True, " pb")}.items() if val is not None})
        elif e["kind"] == "auction":
            v.update({k: val for k, val in {"rendement_precedent": fr(e.get("previous"), 3, unit=" %"),
                                            "rendement_servi": fr(e.get("actual"), 3, unit=" %"),
                                            "bid_to_cover": fr(e.get("bid_to_cover"), 2),
                                            "variation": fr(e.get("change_bp"), 1, True, " pb")}.items() if val is not None})
        if e.get("note"):
            v["note"] = e["note"]
        return {k: val for k, val in v.items() if val is not None}

    t0 = today.isoformat()
    events = cal.get("events", [])
    agenda = [ev_view(e) for e in events if t0 <= e["date"] <= (today + timedelta(days=2)).isoformat()]
    since_yday = [ev_view(e) for e in events if (today - timedelta(days=1)).isoformat() <= e["date"] < t0
                  or (e["date"] == t0 and e.get("time_paris") and e["time_paris"] <= now.isoformat())]
    week_events = [ev_view(e) for e in events if (today - timedelta(days=6)).isoformat() <= e["date"] <= t0]

    # ---- actualités : top 10 (titre + lien uniquement)
    top = [{"id": i["id"], "titre": i["title"], "source": i["source"], "lien": i["link"], "note": i["score"],
            "themes": i.get("themes", []), "heure": i["published"]} for i in news.get("items", [])[:10]]

    # ---- drapeaux
    yday = (today - timedelta(days=1)).isoformat()
    post_meeting = [b for b in ("fed", "ecb") if yday in cb["banks"].get(b, {}).get("dates", [])]
    monthly_due = today == first_business_day(today)
    wraps_month = sorted(p for p in os.listdir(os.path.join(ROOT, "content", "wraps"))
                         if p.startswith(((today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                                          if monthly_due else today.strftime("%Y-%m"))) and p.endswith(".md")) \
        if os.path.isdir(os.path.join(ROOT, "content", "wraps")) else []

    brief = {
        "_lisez_moi": ("Seule source de chiffres autorisée pour les textes. Recopier les valeurs telles quelles "
                       "(format français). Toute donnée absente = ne pas l'inventer, écrire « n.d. »."),
        "genere_le": now.isoformat(timespec="minutes"),
        "date": t0,
        "jour": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"][today.weekday()],
        "drapeaux": {
            "rapport_mensuel_a_ecrire": monthly_due,
            "lendemain_reunion": post_meeting,       # ["fed"], ["ecb"], ou []
            "vendredi": today.weekday() == 4,
        },
        "chiffres": figures,
        "indisponibles": unavailable,
        "agenda_3_jours": agenda,
        "publie_depuis_hier": since_yday,
        "evenements_de_la_semaine": week_events,
        "top10_actualites": top,
        "wraps_du_mois": [f"content/wraps/{p}" for p in wraps_month],
        "alertes_sources": latest.get("errors", {}),
        "controles_du_mois": _controls(today, monthly_due),
    }
    brief["empreinte"] = fingerprint(brief)
    with open(OUT, "w") as f:
        json.dump(brief, f, ensure_ascii=False, indent=0)
    log(f"[brief] {len(figures)} chiffres, {len(agenda)} événements à venir, {len(top)} actualités")
    return brief


if __name__ == "__main__":
    build()
