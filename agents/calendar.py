"""AGENT CALENDRIER — sans IA.

Deux modes, choisis par l'orchestrateur :
- refresh() : chaque matin à 8h, reconstruit la liste des événements des 14 prochains
  jours à partir des calendriers officiels (banques centrales, FRED, Eurostat, TreasuryDirect).
- update_results() : chaque heure, complète les événements passés avec la valeur publiée,
  en la lisant dans les données de l'agent Données (jamais inventée).

Consensus : aucune source gratuite et légale n'existe -> toujours « n.d. ».
La « surprise » affichée est donc réel − précédent (et non réel − consensus).
"""
import json
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.sources import HEADERS, _get

PARIS = ZoneInfo("Europe/Paris")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "calendar.json")
LATEST = os.path.join(ROOT, "data", "latest.json")
CB_FILE = os.path.join(ROOT, "config", "central_banks.json")
AHEAD_DAYS, BEHIND_DAYS = 14, 7

# Publications américaines : identifiant de « release » FRED, mot-clé de contrôle, heure (New York)
US_RELEASES = [
    dict(key="us_cpi", release_id=10, check="Consumer Price Index", label="CPI US (global et core)",
         stars=3, time="08:30", series="us_cpi", series2="us_core_cpi"),
    dict(key="nfp", release_id=50, check="Employment Situation", label="Emploi US (NFP, chômage)",
         stars=3, time="08:30", series="nfp", series2="us_unemp"),
    dict(key="pce", release_id=54, check="Personal Income", label="PCE core US (revenus et dépenses)",
         stars=3, time="08:30", series="us_core_pce"),
    dict(key="us_gdp", release_id=53, check="Gross Domestic Product", label="PIB US",
         stars=2, time="08:30", series="us_gdp"),
    dict(key="us_retail", release_id=9, check="Retail", label="Ventes au détail US",
         stars=2, time="08:30", series=None),
]

# Publications Eurostat : motif du titre iCal -> fiche (heure de diffusion standard : 11h, Luxembourg)
EUROSTAT = [
    (r"^Flash estimate inflation euro area", dict(key="ea_hicp_flash", label="HICP zone euro – estimation flash",
                                                  stars=3, series="ea_hicp", series2="ea_core")),
    (r"^Inflation \(HICP\)", dict(key="ea_hicp_final", label="HICP zone euro – chiffre définitif", stars=1,
                                  series="ea_hicp", series2="ea_core")),
    (r"^Unemployment$", dict(key="ea_unemp", label="Chômage zone euro", stars=1, series="ea_unemp")),
    (r"^GDP (main aggregates|and employment)", dict(key="ea_gdp", label="PIB zone euro", stars=2, series="ea_gdp")),
    (r"^Retail trade$", dict(key="ea_retail", label="Ventes au détail zone euro", stars=1, series=None)),
]

MISSING = [
    "Inflation France (INSEE) : le calendrier INSEE n'est pas diffusé dans un format lisible automatiquement.",
    "PMI (S&P Global / HCOB) : calendrier et chiffres propriétaires.",
    "Consensus des économistes : aucune source gratuite et légale ; la surprise affichée est réel − précédent.",
]


def _paris(day, hhmm, tz):
    """Convertit une heure locale (New York, Francfort…) en heure de Paris, été/hiver compris."""
    if not hhmm:
        return None
    h, m = map(int, hhmm.split(":"))
    local = datetime(day.year, day.month, day.day, h, m, tzinfo=ZoneInfo(tz))
    return local.astimezone(PARIS).isoformat(timespec="minutes")


def _load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


# ------------------------------------------------------------ collecte des dates
def central_banks(start, end, warnings):
    cfg = _load(CB_FILE, {})
    events = []
    for bank, b in cfg.get("banks", {}).items():
        future = [d for d in b["dates"] if d >= date.today().isoformat()]
        if len(future) < 2:
            warnings.append(f"Calendrier {bank.upper()} bientôt épuisé dans config/central_banks.json : à compléter.")
        for d in b["dates"]:
            day = date.fromisoformat(d)
            if start <= day <= end:
                events.append(dict(id=f"{bank}-{d}", kind="cb", bank=bank, label=b["label"], stars=b["stars"],
                                   date=d, time_paris=_paris(day, b.get("time"), b["tz"]), series=b.get("series"),
                                   source="Calendrier officiel", url=b["source"], note=b.get("note")))
    return events


def us_releases(start, end, warnings):
    key = os.environ.get("FRED_API_KEY")
    if not key:
        warnings.append("Dates US indisponibles : clé FRED absente.")
        return []
    events = []
    for r in US_RELEASES:
        try:
            j = _get("https://api.stlouisfed.org/fred/release/dates",
                     {"release_id": r["release_id"], "api_key": key, "file_type": "json",
                      "realtime_start": start.isoformat(), "realtime_end": "9999-12-31",
                      "include_release_dates_with_no_data": "true", "sort_order": "asc", "limit": 100}).json()
            name = _get("https://api.stlouisfed.org/fred/release",
                        {"release_id": r["release_id"], "api_key": key, "file_type": "json"}).json()
            rel_name = (name.get("releases") or [{}])[0].get("name", "")
            if r["check"].lower() not in rel_name.lower():
                warnings.append(f"FRED release {r['release_id']} = « {rel_name} » (attendu : {r['check']}) : ignorée.")
                continue
        except Exception as e:  # noqa: BLE001
            warnings.append(f"Dates FRED « {r['label']} » indisponibles ({e}).")
            continue
        for d in {x["date"] for x in j.get("release_dates", [])}:
            day = date.fromisoformat(d)
            if start <= day <= end:
                events.append(dict(id=f"{r['key']}-{d}", kind="macro", label=r["label"], stars=r["stars"], date=d,
                                   time_paris=_paris(day, r["time"], "America/New_York"), series=r["series"],
                                   series2=r.get("series2"), source="FRED – calendrier des publications",
                                   url=f"https://fred.stlouisfed.org/release?rid={r['release_id']}"))
    return events


def eurostat_releases(start, end, warnings):
    try:
        ics = _get("https://ec.europa.eu/eurostat/o/calendars/eventsIcal", {"theme": "", "category": ""}).text
    except Exception as e:  # noqa: BLE001
        warnings.append(f"Calendrier Eurostat indisponible ({e}).")
        return []
    events, seen = [], set()
    for block in ics.split("BEGIN:VEVENT")[1:]:
        s = re.search(r"\nSUMMARY[^:]*:(.*)", block)
        d = re.search(r"\nDTSTART[^:]*:(\d{8})", block)
        if not (s and d):
            continue
        title = s.group(1).strip()
        day = datetime.strptime(d.group(1), "%Y%m%d").date()
        if not (start <= day <= end):
            continue
        for pattern, meta in EUROSTAT:
            if re.search(pattern, title) and (meta["key"], day) not in seen:
                seen.add((meta["key"], day))
                events.append(dict(id=f"{meta['key']}-{day}", kind="macro", label=meta["label"], stars=meta["stars"],
                                   date=day.isoformat(), time_paris=_paris(day, "11:00", "Europe/Luxembourg"),
                                   series=meta.get("series"), series2=meta.get("series2"),
                                   source="Eurostat – calendrier de diffusion",
                                   url="https://ec.europa.eu/eurostat/news/release-calendar"))
    return events


def _adate(sec):
    """Date d'adjudication (le champ change selon le point d'accès de TreasuryDirect)."""
    return (sec.get("auctionDate") or sec.get("competitiveAuctionCloseDate") or "")[:10]


def _is_major(sec):
    """« Grandes adjudications » : obligations et notes de 2 ans et plus, TIPS inclus (pas les T-bills)."""
    # les FRN sont exclues : leur « rendement » est une marge, pas comparable
    return (sec.get("securityType") in ("Note", "Bond") or sec.get("type") == "TIPS") and sec.get("type") != "FRN"


def _stars_auction(sec):
    term = sec.get("originalSecurityTerm") or sec.get("securityTerm") or ""
    return 2 if term.startswith(("10-Year", "30-Year", "20-Year")) else 1


def treasury_auctions(start, end, warnings):
    events = []
    try:
        upcoming = _get("https://www.treasurydirect.gov/TA_WS/securities/upcoming", {"format": "json"}).json()
    except Exception as e:  # noqa: BLE001
        warnings.append(f"Adjudications du Trésor US indisponibles ({e}).")
        return []
    for sec in upcoming:
        if not _is_major(sec):
            continue
        d = _adate(sec)
        if not d:
            continue
        day = date.fromisoformat(d)
        if start <= day <= end:
            t = sec.get("competitiveAuctionCloseTime") or "01:00 PM"
            hhmm = datetime.strptime(t, "%I:%M %p").strftime("%H:%M")
            desc = sec.get("securityDescription") or f"{sec.get('securityTerm')} {sec.get('securityType')}"
            amount = sec.get("offeringAmount")
            events.append(dict(id=f"ust-{sec.get('cusip')}-{d}", kind="auction", cusip=sec.get("cusip"),
                               sec_type=sec.get("type"),
                               term=sec.get("originalSecurityTerm") or sec.get("securityTerm"),
                               label=f"Adjudication Trésor US – {desc}", stars=_stars_auction(sec), date=d,
                               time_paris=_paris(day, hhmm, "America/New_York"),
                               note=f"Montant offert : {int(float(amount)) / 1e9:.0f} Md$" if amount else None,
                               source="TreasuryDirect", url="https://www.treasurydirect.gov/auctions/upcoming/"))
    return events


# ------------------------------------------------------------ valeurs publiées
def _tiles():
    latest = _load(LATEST, {})
    return {t["id"]: t for t in latest.get("tiles", [])}


# Délai maximal entre la fin de la période mesurée et la publication (garde-fou :
# on n'attribue jamais à un événement un chiffre trop ancien pour être le sien)
MAX_LAG = {"monthly": 65, "quarterly": 180}


def _fill_macro(ev, tiles, now):
    """Avant la publication on fige la « précédente » ; après, on attend que la source affiche
    une nouvelle période. Si elle ne l'a pas encore fait : « en attente », jamais de valeur devinée."""
    released = bool(ev.get("time_paris")) and datetime.fromisoformat(ev["time_paris"]) <= now
    for k in ("series", "series2"):
        sid = ev.get(k)
        if not sid or sid not in tiles or tiles[sid].get("status") == "na" or not tiles[sid].get("date"):
            continue
        t = tiles[sid]
        slot = ev.setdefault("values", {}).setdefault(sid, {"label": t["label"], "unit": t.get("unit")})
        if "previous" not in slot:
            lag = MAX_LAG.get(t.get("freq"), 65)
            fresh_enough = (date.fromisoformat(ev["date"]) - date.fromisoformat(t["date"])).days <= lag
            if released and fresh_enough:
                # événement déjà passé au premier passage et chiffre récent : c'est celui publié
                slot.update(previous=t.get("previous"), previous_period=t.get("previous_date"),
                            actual=t.get("value"), period=t["date"])
            elif released:
                slot.update(previous=t.get("value"), previous_period=t["date"])
            else:
                slot.update(previous=t.get("value"), previous_period=t["date"])
        elif released and slot.get("actual") is None and t["date"] > (slot.get("previous_period") or ""):
            slot.update(actual=t.get("value"), period=t["date"])
        if slot.get("actual") is not None and slot.get("previous") is not None:
            slot["surprise_vs_prev"] = round(slot["actual"] - slot["previous"], 2)


def _fill_cb(ev, tiles, now):
    sid = ev.get("series")
    if not sid or sid not in tiles or tiles[sid].get("status") == "na":
        return
    t = tiles[sid]
    decision = date.fromisoformat(ev["date"])
    released = bool(ev.get("time_paris")) and datetime.fromisoformat(ev["time_paris"]) <= now
    if "previous" not in ev:
        if released and t.get("date", "") >= ev["date"]:
            return  # passé avant notre premier relevé : on ne reconstitue pas l'avant-décision
        ev["previous"], ev["previous_low"] = t.get("value"), t.get("range_low")
    if not released or ev.get("actual") is not None:
        return
    if t.get("freq") == "event":
        # BCE : la série n'enregistre que les changements, à leur date d'effet (souvent la semaine suivante)
        if t.get("date", "") >= ev["date"] or now.date() >= decision + timedelta(days=8):
            ev["actual"] = t.get("value")
    elif t.get("date", "") >= ev["date"]:
        ev["actual"], ev["actual_low"] = t.get("value"), t.get("range_low")
    if ev.get("actual") is not None and ev.get("previous") is not None:
        ev["change_bp"] = round((ev["actual"] - ev["previous"]) * 100)


def _fill_auctions(events, warnings):
    pending = [e for e in events if e["kind"] == "auction"]
    if not pending:
        return
    try:
        done = _get("https://www.treasurydirect.gov/TA_WS/securities/auctioned",
                    {"format": "json", "days": 120}).json()
    except Exception as e:  # noqa: BLE001
        warnings.append(f"Résultats d'adjudication indisponibles ({e}).")
        return
    by_term = {}
    for s in sorted(done, key=_adate):
        if s.get("highYield") and _is_major(s):
            by_term.setdefault((s.get("originalSecurityTerm") or s.get("securityTerm"), s.get("type")), []).append(s)
    for ev in pending:
        for (term, typ), lst in by_term.items():
            if term != ev.get("term") or typ != ev.get("sec_type"):
                continue
            mine = [s for s in lst if s.get("cusip") == ev.get("cusip") and _adate(s) == ev["date"]]
            before = [s for s in lst if _adate(s) < ev["date"]]
            if before and "previous" not in ev:
                ev["previous"] = float(before[-1]["highYield"])
                ev["previous_date"] = _adate(before[-1])
            if mine:
                ev["actual"] = float(mine[0]["highYield"])
                if mine[0].get("bidToCoverRatio"):
                    ev["bid_to_cover"] = float(mine[0]["bidToCoverRatio"])
                if ev.get("previous") is not None:
                    ev["change_bp"] = round((ev["actual"] - ev["previous"]) * 100, 1)


# ------------------------------------------------------------ points d'entrée
def refresh(log=print):
    """Reconstruit la liste des événements (8h), en conservant les valeurs déjà relevées."""
    today = date.today()
    start, end = today - timedelta(days=BEHIND_DAYS), today + timedelta(days=AHEAD_DAYS)
    warnings = []
    fresh = (central_banks(start, end, warnings) + us_releases(start, end, warnings)
             + eurostat_releases(start, end, warnings) + treasury_auctions(start, end, warnings))
    old = {e["id"]: e for e in _load(OUT, {}).get("events", [])}
    merged = {}
    for e in fresh:
        prev = old.get(e["id"], {})
        for k in ("values", "previous", "previous_low", "previous_date", "actual", "actual_low", "change_bp",
                  "bid_to_cover"):
            if k in prev:
                e[k] = prev[k]
        merged[e["id"]] = e
    # les événements passés d'avant (adjudications déjà retirées des listes « à venir », etc.) restent 7 jours
    for eid, e in old.items():
        if eid not in merged and start.isoformat() <= e["date"] <= end.isoformat():
            merged[eid] = e
    return _save(list(merged.values()), warnings, log, refreshed=True)


def update_results(log=print):
    cal = _load(OUT, None)
    if cal is None:
        return refresh(log)
    return _save(cal["events"], [], log, refreshed=False, keep=cal)


def _save(events, warnings, log, refreshed, keep=None):
    now = datetime.now(PARIS)
    tiles = _tiles()
    for ev in events:
        if ev["kind"] == "macro":
            _fill_macro(ev, tiles, now)
        elif ev["kind"] == "cb":
            _fill_cb(ev, tiles, now)
    _fill_auctions(events, warnings)
    events.sort(key=lambda e: (e["date"], e.get("time_paris") or "", -e["stars"]))
    out = {
        "refreshed_at": now.isoformat(timespec="minutes") if refreshed else (keep or {}).get("refreshed_at"),
        "updated_at": now.isoformat(timespec="minutes"),
        "events": events,
        "warnings": warnings if refreshed else (keep or {}).get("warnings", []),
        "missing": MISSING,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"[calendrier] {len(events)} événements, {len(out['warnings'])} avertissement(s)")
    return out


if __name__ == "__main__":
    refresh()
