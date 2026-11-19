"""AGENT DONNÉES — sans IA.

1. Interroge chaque source du catalogue (une erreur n'arrête pas les autres).
2. Fusionne avec l'historique déjà stocké dans data/history/.
3. Calcule les variations 1 jour / 1 semaine / depuis le 1er janvier et le mini-graphique.
4. Écrit data/latest.json, lu ensuite par le site.
"""
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents import sources as S
from agents.catalog import BY_ID, GROUPS, SERIES

PARIS = ZoneInfo("Europe/Paris")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST_DIR = os.path.join(ROOT, "data", "history")
LATEST = os.path.join(ROOT, "data", "latest.json")

# Délai au-delà duquel une donnée est considérée « retardée » (jours calendaires)
STALE_AFTER = {"daily": 5, "monthly": 80, "quarterly": 200, "event": None}


# ------------------------------------------------------------------ outils
def _d(s):
    return date.fromisoformat(s)


def asof(points, day):
    """Dernière valeur connue à une date donnée (ou avant)."""
    best = None
    for d, v in points:
        if d <= day:
            best = (d, v)
        else:
            break
    return best


def load_history(sid):
    path = os.path.join(HIST_DIR, f"{sid}.json")
    if os.path.exists(path):
        with open(path) as f:
            return [tuple(p) for p in json.load(f).get("points", [])]
    return []


def save_history(sid, points):
    os.makedirs(HIST_DIR, exist_ok=True)
    with open(os.path.join(HIST_DIR, f"{sid}.json"), "w") as f:
        json.dump({"id": sid, "points": points}, f, separators=(",", ":"))


def merge(old, new):
    """Les nouvelles valeurs remplacent les anciennes (révisions), l'historique s'allonge."""
    m = dict(old)
    m.update(dict(new))
    return sorted(m.items())


def transform(points, how):
    if how == "yoy":  # indice mensuel -> glissement annuel en %
        idx = dict(points)
        out = []
        for d, v in points:
            prev = f"{int(d[:4]) - 1}{d[4:]}"
            if prev in idx and idx[prev]:
                out.append((d, round((v / idx[prev] - 1) * 100, 2)))
        return out
    if how == "mom_diff":  # niveau -> variation mensuelle
        return [(points[i][0], round(points[i][1] - points[i - 1][1], 1)) for i in range(1, len(points))]
    return points


def derive(spec, data):
    """Séries calculées : écarts entre deux séries, alignés date par date."""
    op = spec[0]
    if op == "sub":
        a, b = data.get(spec[1]), data.get(spec[2])
        if not a or not b:
            raise RuntimeError(f"composante manquante ({spec[1] if not a else spec[2]})")
        out = []
        for d, v in a:
            ref = asof(b, d)
            if ref and (_d(d) - _d(ref[0])).days <= 400:
                out.append((d, round(v - ref[1], 4)))
        return out
    if op == "sub_mid":  # a - milieu de fourchette (b, c)
        a, up, lo = data.get(spec[1]), data.get(spec[2]), data.get(spec[3])
        if not (a and up and lo):
            raise RuntimeError("composante manquante")
        out = []
        for d, v in a:
            u, l = asof(up, d), asof(lo, d)
            if u and l:
                out.append((d, round(v - (u[1] + l[1]) / 2, 4)))
        return out
    raise ValueError(op)


def stats(meta, points):
    """Valeur, variations et mini-graphique pour une série."""
    last_d, last_v = points[-1]
    ld = _d(last_d)
    kind = meta["kind"]
    out = {"date": last_d, "value": last_v}

    if kind == "macro":
        out["previous"] = points[-2][1] if len(points) > 1 else None
        out["previous_date"] = points[-2][0] if len(points) > 1 else None
        out["spark"] = points[-13:]
        return out

    def change(ref):
        if not ref or ref[1] is None:
            return None
        if kind == "rate":
            return round((last_v - ref[1]) * 100, 1) + 0.0  # points de base (+0.0 évite « −0 »)
        return round((last_v / ref[1] - 1) * 100, 2) + 0.0 if ref[1] else None

    prev = points[-2] if len(points) > 1 else None
    if meta["freq"] == "event":
        # taux qui ne change qu'aux décisions : on compare à la valeur en vigueur hier / il y a 7 jours
        ld = date.today()
        prev = asof(points, (ld - timedelta(days=1)).isoformat())
    out["chg_1d"] = change(prev) if meta["freq"] in ("daily", "event") else None
    out["chg_1w"] = change(asof(points, (ld - timedelta(days=7)).isoformat())) if meta["freq"] in ("daily", "event") else None
    out["chg_ytd"] = change(asof(points, f"{ld.year - 1}-12-31"))
    if meta["freq"] == "monthly":
        out["chg_1m"] = change(prev)

    if meta["freq"] == "event":
        # série « à chaque décision » : on reconstruit une courbe en escalier sur 3 mois
        start = date.today() - timedelta(days=92)
        spark, d = [], start
        while d <= date.today():
            p = asof(points, d.isoformat())
            if p:
                spark.append((d.isoformat(), p[1]))
            d += timedelta(days=7)
        out["spark"] = spark
    elif meta["freq"] == "monthly":
        out["spark"] = points[-13:]
    else:
        cutoff = (ld - timedelta(days=92)).isoformat()
        out["spark"] = [p for p in points if p[0] >= cutoff]
    return out


def is_stale(meta, last_date):
    lim = STALE_AFTER.get(meta["freq"])
    if not lim:
        return False
    return (date.today() - _d(last_date)).days > lim


# ------------------------------------------------------------------ agent
def run(log=print):
    now = datetime.now(PARIS)
    raw, errors = {}, {}

    # 1) Yahoo : un seul appel groupé
    yahoo_ids = [s for s in SERIES if s.get("yahoo")]
    try:
        res = S.yahoo_batch([s["yahoo"] for s in yahoo_ids])
        for s in yahoo_ids:
            if res.get(s["yahoo"]):
                raw[s["id"]] = res[s["yahoo"]]
            else:
                errors[s["id"]] = "Yahoo n'a renvoyé aucune donnée"
    except Exception as e:  # noqa: BLE001
        for s in yahoo_ids:
            errors[s["id"]] = f"Yahoo indisponible ({type(e).__name__})"

    # 2) Les autres sources, une par une
    for s in SERIES:
        if "fetch" not in s:
            continue
        fn, *args = s["fetch"]
        try:
            raw[s["id"]] = fn(*args)
        except Exception as e:  # noqa: BLE001
            errors[s["id"]] = str(e)[:160]

    # 3) Fusion avec l'historique (sauf données sous licence restrictive)
    data = {}
    for s in SERIES:
        sid = s["id"]
        if s.get("restricted"):
            data[sid] = raw.get(sid, [])
            continue
        hist = load_history(sid)
        merged = merge(hist, raw.get(sid, []))
        if merged:
            data[sid] = merged
            if sid in raw:
                save_history(sid, merged)

    # 4) Séries calculées
    for s in SERIES:
        if "derive" in s:
            try:
                data[s["id"]] = derive(s["derive"], data)
                save_history(s["id"], data[s["id"]])
            except Exception as e:  # noqa: BLE001
                errors[s["id"]] = str(e)

    # 5) Statistiques et statut de chaque tuile
    tiles = []
    for s in SERIES:
        if s.get("hidden"):
            continue
        sid = s["id"]
        tile = {k: s.get(k) for k in ("id", "group", "label", "kind", "freq", "source", "note", "unit", "dec",
                                       "show_bp", "restricted", "display")}
        if s.get("na"):
            tile.update(status="na", reason=s["na"])
            tiles.append(tile)
            continue
        pts = transform(data.get(sid, []), s.get("transform"))
        if not pts:
            tile.update(status="na", reason=errors.get(sid, "aucune donnée"))
            tiles.append(tile)
            continue
        tile.update(stats(s, pts))
        if s.get("display") == "fed_range" and data.get("fed_lower"):
            tile["range_low"] = data["fed_lower"][-1][1]
        if sid in errors:
            tile.update(status="stale", reason=f"Source en erreur, dernière valeur connue : {errors[sid]}")
        elif is_stale(s, tile["date"]):
            tile.update(status="stale", reason="Donnée non mise à jour par la source depuis plusieurs jours")
        else:
            tile["status"] = "ok"
        if s.get("restricted"):  # licence ICE : pas de niveau, pas de graphique
            tile.pop("value", None)
            tile.pop("spark", None)
        if s.get("yahoo"):
            tile["fetched_at"] = f"{now:%H:%M}"
        tiles.append(tile)

    latest = {
        "generated_at": now.isoformat(timespec="minutes"),
        "groups": [{"id": g, "label": l} for g, l in GROUPS],
        "tiles": tiles,
        "errors": {k: v for k, v in errors.items() if not BY_ID[k].get("hidden")},
    }
    with open(LATEST, "w") as f:
        json.dump(latest, f, ensure_ascii=False, indent=1)
    ok = sum(t["status"] == "ok" for t in tiles)
    log(f"[données] {ok}/{len(tiles)} tuiles à jour, {len(errors)} erreur(s) de source")
    return latest


if __name__ == "__main__":
    run()
