"""ORCHESTRATEUR — décide quels agents tournent, tient les logs, isole les erreurs.

GitHub Actions le lance toutes les heures (cron en UTC). C'est ici, et pas dans
le cron, qu'on vérifie l'heure de Paris : ça gère tout seul l'heure d'été/d'hiver.

    python orchestrator.py           # respecte la fenêtre 8h-23h Paris
    python orchestrator.py --force   # lance quand même (test manuel)
"""
import json
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "data", "logs", "runs.jsonl")
OPEN_HOUR, CLOSE_HOUR = 8, 23  # inclus : dernière mise à jour à 23h


def in_window(now):
    return OPEN_HOUR <= now.hour <= CLOSE_HOUR


def _calendar_refreshed_today(now):
    path = os.path.join(ROOT, "data", "calendar.json")
    if not os.path.exists(path):
        return False
    with open(path) as f:
        last = json.load(f).get("refreshed_at") or ""
    return last[:10] == now.date().isoformat()


def plan(now, force=False):
    """Quels agents tournent à cette heure-ci ?
    - Données : à chaque passage (en premier : les autres agents lisent ses résultats).
    - Calendrier : liste complète à 8h (ou au premier passage du jour si celui de 8h a sauté),
      puis seulement la mise à jour des valeurs publiées les autres heures.
    - Actualités : à chaque passage."""
    agents = ["data"]
    if force or now.hour == OPEN_HOUR or not _calendar_refreshed_today(now):
        agents.append("calendar_refresh")
    else:
        agents.append("calendar_results")
    agents.append("news")   # Actualités : à chaque passage
    agents.append("brief")  # Dossier de brief pour les tâches Claude : en dernier (il lit tout le reste)
    return agents


def write_log(entry):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    lines = []
    if os.path.exists(LOG):
        with open(LOG) as f:
            lines = f.readlines()[-499:]  # on garde les 500 dernières exécutions
    lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(LOG, "w") as f:
        f.writelines(lines)


def main():
    now = datetime.now(PARIS)
    force = "--force" in sys.argv
    if not force and not in_window(now):
        print(f"{now:%H:%M} à Paris : hors de la fenêtre 8h-23h, rien à faire.")
        # Fichier lu par le workflow pour sauter la suite (commit, publication)
        open(os.path.join(ROOT, ".skip"), "w").close()
        return 0

    entry = {"start": now.isoformat(timespec="seconds"), "agents": {}}
    for name in plan(now, force):
        try:
            if name == "data":
                from agents import data
                res = data.run()
                entry["agents"][name] = {"ok": True, "errors": len(res["errors"])}
            elif name == "calendar_refresh":
                from agents import calendar
                res = calendar.refresh()
                entry["agents"][name] = {"ok": True, "events": len(res["events"]), "warnings": len(res["warnings"])}
            elif name == "news":
                from agents import news
                res = news.run()
                entry["agents"][name] = {"ok": True, "items": len(res["items"]), "feed_errors": len(res["errors"])}
            elif name == "brief":
                from agents import brief
                res = brief.build()
                entry["agents"][name] = {"ok": True, "figures": len(res["chiffres"])}
            elif name == "calendar_results":
                from agents import calendar
                res = calendar.update_results()
                entry["agents"][name] = {"ok": True, "events": len(res["events"])}
        except Exception as e:  # un agent qui plante n'empêche pas les autres
            traceback.print_exc()
            entry["agents"][name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}

    # Le site est reconstruit à chaque passage, même si un agent a échoué :
    # les tuiles concernées affichent « n.d. » et un bandeau d'alerte.
    try:
        from web import build
        build.main()
        entry["site"] = "ok"
    except Exception as e:
        traceback.print_exc()
        entry["site"] = f"{type(e).__name__}: {e}"[:200]
    entry["end"] = datetime.now(PARIS).isoformat(timespec="seconds")
    write_log(entry)
    print(json.dumps(entry, ensure_ascii=False))
    return 0 if entry["site"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
