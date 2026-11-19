"""Connecteurs vers les sources de données gratuites.

Chaque fonction renvoie une liste triée de (date 'AAAA-MM-JJ', valeur float).
Aucune ne « devine » une valeur : en cas de problème, elle lève une exception
et l'agent Données affichera « n.d. » avec la raison.
"""
import csv
import io
import os
import time
from datetime import date, timedelta

import requests

HEADERS = {"User-Agent": "market-dashboard (projet personnel pedagogique)"}
TIMEOUT = 20
LOOKBACK_DAYS = 420  # assez pour le YTD, la variation 1 semaine et le graphique 3 mois


def _start(days=LOOKBACK_DAYS):
    return date.today() - timedelta(days=days)


def _get(url, params=None):
    """GET avec 2 nouvelles tentatives (les API publiques ont parfois des ratés)."""
    last = None
    for attempt in range(2):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code in (400, 404):
                break
        except requests.RequestException as e:
            last = type(e).__name__
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"source injoignable ({last})")


def _clean(points):
    out = {}
    for d, v in points:
        if v is None:
            continue
        try:
            out[d] = float(v)
        except (TypeError, ValueError):
            continue
    if not out:
        raise RuntimeError("aucune observation renvoyée")
    return sorted(out.items())


# --------------------------------------------------------------------- FRED
def fred(series_id, days=LOOKBACK_DAYS):
    """FRED (Fed de St. Louis), via l'API officielle uniquement.
    La clé est lue dans l'environnement (GitHub Secrets), jamais écrite dans le code."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("clé FRED absente (secret FRED_API_KEY)")
    r = _get(
        "https://api.stlouisfed.org/fred/series/observations",
        {"series_id": series_id, "api_key": key, "file_type": "json",
         "observation_start": _start(days).isoformat()},
    )
    obs = r.json().get("observations", [])
    return _clean((o["date"], None if o["value"] == "." else o["value"]) for o in obs)


# ---------------------------------------------------------------------- BCE
def ecb(flow, key, days=LOOKBACK_DAYS):
    """ECB Data Portal (API SDMX, sans clé)."""
    r = _get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}",
             {"startPeriod": _start(days).isoformat(), "format": "csvdata"})
    rows = csv.DictReader(io.StringIO(r.text))
    pts = []
    for row in rows:
        p = row["TIME_PERIOD"]
        if len(p) == 7:  # mensuel AAAA-MM -> 1er du mois
            p += "-01"
        pts.append((p, row["OBS_VALUE"] or None))
    return _clean(pts)


def ecb_monthly(flow, key):
    """Séries mensuelles : on remonte plus loin pour avoir l'historique."""
    r = _get(f"https://data-api.ecb.europa.eu/service/data/{flow}/{key}",
             {"startPeriod": (date.today() - timedelta(days=500)).strftime("%Y-%m"),
              "format": "csvdata"})
    rows = csv.DictReader(io.StringIO(r.text))
    return _clean((row["TIME_PERIOD"] + "-01", row["OBS_VALUE"] or None) for row in rows)


# -------------------------------------------------------------- Bundesbank
def bundesbank(key):
    """Rendements des Bund (courbe des taux de la Bundesbank, sans clé)."""
    r = _get(f"https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}",
             {"startPeriod": _start().isoformat(), "format": "csv", "lang": "en"})
    pts = []
    for line in r.text.splitlines():
        parts = line.split(",")  # en anglais : séparateur virgule, décimale point
        if len(parts) >= 2 and len(parts[0]) == 10 and parts[0][4] == "-":
            v = parts[1].strip()
            pts.append((parts[0], v if v not in ("", ".") else None))
    return _clean(pts)


# ---------------------------------------------------------- Bank of England
def boe(code):
    """Base de données IADB de la Bank of England (CSV, sans clé)."""
    start = _start().strftime("%d/%b/%Y")
    r = _get("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp",
             {"csv.x": "yes", "Datefrom": start, "Dateto": "now", "SeriesCodes": code,
              "CSVF": "TN", "UsingCodes": "Y"})
    pts = []
    for row in csv.reader(io.StringIO(r.text)):
        if len(row) >= 2:
            try:
                from datetime import datetime
                d = datetime.strptime(row[0].strip(), "%d %b %Y").date().isoformat()
            except ValueError:
                continue
            pts.append((d, row[-1].strip() or None))
    return _clean(pts)


# ------------------------------------------------------ Japon : MoF et BoJ
def mof_jgb(tenor="10Y"):
    """Rendements des JGB publiés chaque jour par le ministère des Finances japonais."""
    pts = []
    for url in ("https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
                "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"):
        try:
            r = _get(url)
        except RuntimeError:
            continue
        lines = r.content.decode("utf-8", errors="ignore").splitlines()
        header = None
        for row in csv.reader(lines):
            if row and row[0].strip().lower() == "date":
                header = [h.strip() for h in row]
                continue
            if header and row and "/" in row[0] and tenor in header:
                y, m, d = row[0].split("/")
                iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                if iso >= _start().isoformat():
                    v = row[header.index(tenor)].strip()
                    pts.append((iso, v if v not in ("", "-") else None))
    return _clean(pts)


def boj(db, code):
    """API officielle de la Banque du Japon (lancée en février 2026, sans clé)."""
    r = _get("https://www.stat-search.boj.or.jp/api/v1/getDataCode",
             {"format": "json", "lang": "en", "db": db, "code": code,
              "startDate": _start().strftime("%Y%m")})
    res = r.json().get("RESULTSET") or []
    if not res:
        raise RuntimeError("réponse BoJ vide")
    vals = res[0]["VALUES"]
    pts = []
    for d, v in zip(vals["SURVEY_DATES"], vals["VALUES"]):
        s = str(d)
        if len(s) == 8:
            pts.append((f"{s[:4]}-{s[4:6]}-{s[6:]}", v))
    return _clean(pts)


# ------------------------------------------------------------------ Eurostat
def eurostat(dataset, params, geos=("EA", "EA21", "EA20")):
    """API de diffusion d'Eurostat (JSON-stat, sans clé). On essaie plusieurs
    codes de zone euro car la composition change (Bulgarie en 2026)."""
    last_err = "aucune donnée"
    for geo in geos:
        p = dict(params, geo=geo, format="JSON", lang="EN",
                 sinceTimePeriod=(date.today() - timedelta(days=800)).strftime("%Y-%m"))
        if "Q" in params.get("_freq", ""):
            y = date.today().year - 2
            p["sinceTimePeriod"] = f"{y}-Q1"
        p.pop("_freq", None)
        try:
            j = _get(f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}", p).json()
        except RuntimeError as e:
            last_err = str(e)
            continue
        idx = j.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
        values = j.get("value", {})
        if not values:
            last_err = f"aucune valeur pour {geo}"
            continue
        pts = []
        for period, pos in idx.items():
            v = values.get(str(pos))
            if "Q" in period:
                y, q = period.split("-Q")
                period = f"{y}-{(int(q) - 1) * 3 + 1:02d}-01"
            elif len(period) == 7:
                period += "-01"
            pts.append((period, v))
        return _clean(pts)
    raise RuntimeError(last_err)


# --------------------------------------------------------------------- Yahoo
def yahoo_batch(tickers):
    """Cours de marché via yfinance (outil non officiel, usage personnel).
    Un seul appel groupé pour tous les tickers, pour rester discret."""
    import yfinance as yf
    df = yf.download(tickers, start=_start().isoformat(), interval="1d",
                     progress=False, auto_adjust=False, threads=False, group_by="column")
    out = {}
    close = df["Close"]
    for t in tickers:
        try:
            s = close[t].dropna()
            out[t] = [(i.strftime("%Y-%m-%d"), float(f"{float(v):.6g}")) for i, v in s.items()]
        except Exception:
            out[t] = []
    return out
