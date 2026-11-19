"""Tests automatiques (sans réseau) : on vérifie la logique, pas les API.

    python -m pytest -q
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents import brief as B          # noqa: E402
from agents import calendar as C       # noqa: E402
from agents import data as D           # noqa: E402
from agents import news as N           # noqa: E402
from checks import coherence as K      # noqa: E402
import orchestrator as O               # noqa: E402

PARIS = ZoneInfo("Europe/Paris")


# ------------------------------------------------------------------ orchestrateur
@pytest.mark.parametrize("day", ["2026-01-15", "2026-07-15", "2026-03-29", "2026-10-25"])
def test_cron_utc_couvre_8h_23h_paris_ete_comme_hiver(day):
    """Le cron « 17 6-22 * * * » (UTC) doit donner 16 passages, de 8h17 à 23h17 à Paris."""
    runs = []
    for h in range(6, 23):
        p = datetime.fromisoformat(f"{day}T{h:02d}:17:00+00:00").astimezone(PARIS)
        if O.in_window(p):
            runs.append(p.hour)
    assert runs == list(range(8, 24))


def test_aucune_mise_a_jour_la_nuit():
    for h in range(0, 8):
        assert not O.in_window(datetime(2026, 11, 20, h, 17, tzinfo=PARIS))


def test_plan_ordre_des_agents():
    p = O.plan(datetime(2026, 11, 20, 8, 17, tzinfo=PARIS))
    assert p[0] == "data" and p[-1] == "brief"          # Données d'abord, brief en dernier
    assert "calendar_refresh" in p and "news" in p      # 8h : calendrier complet


# ------------------------------------------------------------------ agent Données
PTS = [("2025-12-31", 100.0), ("2026-11-11", 108.0), ("2026-11-17", 109.0), ("2026-11-18", 110.0)]


def test_asof_prend_la_derniere_valeur_connue():
    assert D.asof(PTS, "2026-11-15") == ("2026-11-11", 108.0)
    assert D.asof(PTS, "2020-01-01") is None


def test_variations_prix_en_pourcentage():
    s = D.stats({"kind": "price", "freq": "daily"}, PTS)
    assert s["value"] == 110.0
    assert s["chg_1d"] == pytest.approx(0.92, abs=0.01)   # 110/109 - 1
    assert s["chg_1w"] == pytest.approx(1.85, abs=0.01)   # 110/108 - 1
    assert s["chg_ytd"] == pytest.approx(10.0)             # 110/100 - 1


def test_variations_taux_en_points_de_base():
    pts = [("2025-12-31", 4.00), ("2026-11-17", 5.12), ("2026-11-18", 5.10)]
    s = D.stats({"kind": "rate", "freq": "daily"}, pts)
    assert s["chg_1d"] == -2.0 and s["chg_ytd"] == 110.0


def test_glissement_annuel_depuis_un_indice():
    pts = [("2025-10-01", 100.0), ("2026-09-01", 103.0), ("2026-10-01", 103.7)]
    assert D.transform(pts, "yoy") == [("2026-10-01", 3.7)]


def test_spread_calcule_date_par_date():
    data = {"a": [("2026-11-18", 3.45), ("2026-11-19", 3.47)], "b": [("2026-11-18", 3.14)]}
    out = D.derive(("sub", "a", "b"), data)
    assert out[0] == ("2026-11-18", 0.31) and out[1][1] == pytest.approx(0.33)


def test_donnee_retardee_detectee():
    old = (date.today() - timedelta(days=10)).isoformat()
    assert D.is_stale({"freq": "daily"}, old)
    assert not D.is_stale({"freq": "event"}, old)


def test_merge_garde_l_historique_et_applique_les_revisions():
    assert D.merge([("d1", 1.0), ("d2", 2.0)], [("d2", 2.5), ("d3", 3.0)]) == [("d1", 1.0), ("d2", 2.5), ("d3", 3.0)]


# ------------------------------------------------------------------ agent Calendrier
def test_heure_new_york_convertie_en_paris_avec_decalage_variable():
    # 8h30 à New York = 14h30 à Paris en temps normal, 13h30 pendant les 3 semaines de décalage de mars
    assert C._paris(date(2026, 11, 25), "08:30", "America/New_York")[11:16] == "14:30"
    assert C._paris(date(2026, 3, 18), "08:30", "America/New_York")[11:16] == "13:30"


def test_valeur_reelle_jamais_devinee():
    """Publication passée mais la source n'a pas encore la nouvelle période : on attend."""
    now = datetime(2026, 11, 13, 16, 0, tzinfo=PARIS)
    tiles = {"us_cpi": {"label": "CPI", "unit": "%", "status": "ok", "freq": "monthly",
                        "date": "2026-09-01", "value": 3.7, "previous": 3.3, "previous_date": "2026-08-01"}}
    ev = {"kind": "macro", "date": "2026-11-13", "time_paris": "2026-11-13T14:30+01:00", "series": "us_cpi"}
    C._fill_macro(ev, tiles, now)
    assert ev["values"]["us_cpi"].get("actual") is None        # septembre est trop ancien pour la publication du 13/11
    tiles["us_cpi"].update(date="2026-10-01", value=3.9)       # la source publie octobre
    ev2 = {"kind": "macro", "date": "2026-11-13", "time_paris": "2026-11-13T14:30+01:00", "series": "us_cpi",
           "values": {"us_cpi": {"label": "CPI", "previous": 3.7, "previous_period": "2026-09-01"}}}
    C._fill_macro(ev2, tiles, now)
    assert ev2["values"]["us_cpi"]["actual"] == 3.9
    assert ev2["values"]["us_cpi"]["surprise_vs_prev"] == pytest.approx(0.2)


def test_calendrier_banques_centrales_a_jour():
    with open(os.path.join(ROOT, "config", "central_banks.json")) as f:
        cfg = json.load(f)
    for bank, b in cfg["banks"].items():
        assert b["dates"] == sorted(b["dates"]), bank
        assert all(date.fromisoformat(d) for d in b["dates"])


# ------------------------------------------------------------------ agent Actualités
def _item(title, source="X", rel=2, link=None, when="2026-11-19T10:00+01:00"):
    return dict(id=title[:8], title=title, link=link or f"https://ex.com/{abs(hash(title))}", source=source,
                reliability=rel, published=when, summary_hint="")


def test_doublons_fusionnes_en_gardant_la_source_la_plus_fiable():
    items = [_item("Fed holds rates steady as inflation cools", "Média", 2),
             _item("Fed holds rates steady as inflation cools down", "Fed – communiqués", 3)]
    out = N.dedupe(items)
    assert len(out) == 1 and out[0]["source"] == "Fed – communiqués" and out[0]["also"] == ["Média"]


def test_note_officielle_banque_centrale_superieure_au_bruit():
    fomc = _item("Minutes of the Federal Open Market Committee", "Fed – communiqués", 3)
    pod = _item("Can Labour end the youth unemployment crisis? – podcast", "Guardian", 2)
    assert N.score(fomc) >= 4
    assert N.score(pod) <= 2
    assert 1 <= N.score(_item("Recette de la tarte aux pommes", "X", 1)) <= 5


# ------------------------------------------------------------------ contrôle de cohérence
BRIEF = {"date": "2026-11-19", "chiffres": [{"id": "us10y", "valeur": "5,10 %", "var_1j": "-2 pb"},
                                            {"id": "spx", "valeur": "7 327,35", "var_1sem": "-3,49 %"}]}
BRIEF["empreinte"] = B.fingerprint(BRIEF)


def _check(tmp_path, md, brief=BRIEF):
    (tmp_path / "newsletter").mkdir(exist_ok=True)
    p = tmp_path / "newsletter" / "t.md"
    p.write_text(md)
    b = tmp_path / "b.json"
    b.write_text(json.dumps(brief, ensure_ascii=False))
    return K.check(str(p), str(b))


def test_chiffres_corrects_acceptes(tmp_path):
    r = _check(tmp_path, "Le US 10 ans à 5,10 % (-2 pb), le S&P 500 à 7 327,35 (-3,49 % sur la semaine).")
    assert r["ok"] and r["verifies"] == 4


def test_chiffre_invente_detecte(tmp_path):
    r = _check(tmp_path, "Le CAC 40 recule de 7,77 % et le US 10 ans est à 5,10 %.")
    assert not r["ok"] and [u["nombre"] for u in r["inconnus"]] == ["7,77"]


def test_arrondi_non_autorise(tmp_path):
    assert not _check(tmp_path, "Le US 10 ans est à 5,1 % environ, 5 % bientôt.")["ok"]


def test_exemptions_dates_indices_maturites_question_entretien(tmp_path):
    md = ("# Brief du 19 novembre 2026\nLe S&P 500, le CAC 40, le 2s10s et le Bund 10 ans. 3 points à surveiller.\n"
          "## Question d'entretien\nUne obligation à 97,25 avec un coupon de 4,5 % : rendement ?\n")
    assert _check(tmp_path, md)["ok"]


def test_brief_falsifie_detecte(tmp_path):
    fake = json.loads(json.dumps(BRIEF))
    fake["chiffres"][0]["valeur"] = "9,99 %"   # empreinte non recalculée
    r = _check(tmp_path, "Le US 10 ans à 9,99 %.", fake)
    assert not r["brief_valide"] and not r["ok"]


# ------------------------------------------------------------------ site
def test_format_francais():
    from web import build as W
    assert W.num(7327.35) == "7 327,35"
    assert W.num(-2.0, 0) == "−2"
    assert "pb" in W.chg(-2.0, "rate") and "down" in W.chg(-2.0, "rate")
    assert B.fr(5.1, 2, unit=" %") == "5,10 %"


def test_site_se_construit(tmp_path, monkeypatch):
    """Construit le site complet à partir des données du dépôt, dans un dossier temporaire."""
    from web import build as W
    monkeypatch.setattr(W, "OUT", str(tmp_path / "_site"))
    W.main()
    for page in ("index.html", "calendrier.html", "actualites.html", "newsletter.html", "wraps.html", "rapports.html"):
        html = (tmp_path / "_site" / page).read_text()
        assert "Dernière mise à jour" in html and "pas un conseil en investissement" in html
