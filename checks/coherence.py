"""CONTRÔLE DE COHÉRENCE — sans IA.

Vérifie qu'un texte rédigé par Claude ne cite QUE des chiffres présents dans le dossier
de brief qu'il a utilisé (fourni par le code). Chaque texte est publié avec une copie de
son brief (content/sources/<nom>.json) ; l'empreinte de cette copie est recalculée pour
s'assurer qu'elle n'a pas été modifiée.

    python checks/coherence.py content/newsletter/2026-11-20.md

Exemptions (documentées sur le site) :
- la section « Question d'entretien » (exemple pédagogique, chiffres d'illustration) ;
- les nombres qui font partie d'un nom (S&P 500, CAC 40, Nasdaq 100…), d'une maturité
  (2 ans, 10 ans, 2s10s, 3M), d'une date ou d'une numérotation (entiers ≤ 31 sans unité).
"""
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from agents.brief import fingerprint  # noqa: E402

NUM = re.compile(r"(?<![\w.,])[+\-−]?\d{1,3}(?:[   ]\d{3})+(?:[,.]\d+)?(?![\w])"
                 r"|(?<![\w.,])[+\-−]?\d+(?:[,.]\d+)?")
UNIT_AFTER = re.compile(r"^\s?(%|pb|bp|pt|points?|k\b|\$|€|md|mds|milliards?|millions?|x\b)", re.I)
MONTHS = ("janv", "févr", "fevr", "mars", "avr", "mai", "juin", "juil", "août", "aout", "sept", "oct", "nov", "déc",
          "dec", "january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december", "t1", "t2", "t3", "t4", "q1", "q2", "q3", "q4")
NAME_NUMBERS = re.compile(r"(S&P|Nasdaq|CAC|Stoxx|STOXX|FTSE|Nikkei|DAX|Euro Stoxx|MSCI|Dow)\s?$")
MATURITY_AFTER = re.compile(r"^\s?(ans?|years?|y\b|-year|m\b|mois|s10s|s30s|s5s|jours?|j\b|semaines?|h\b|heures?)", re.I)


def norm(s):
    s = s.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return abs(Decimal(s)).normalize()
    except InvalidOperation:
        return None


def allowed_numbers(brief):
    """Tous les nombres présents dans le brief (valeurs formatées et champs numériques)."""
    out = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k not in ("lien", "id", "empreinte", "genere_le", "heure"):
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            out.add(norm(str(x)))
        elif isinstance(x, str):
            for m in NUM.finditer(x):
                n = norm(m.group())
                if n is not None:
                    out.add(n)
    walk(brief)
    return out


def strip_exempt_sections(md):
    """Retire la section « Question d'entretien » (jusqu'au titre suivant de même niveau ou plus haut)."""
    lines, out, skip, level = md.splitlines(), [], False, 0
    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            lvl = len(m.group(1))
            if skip and lvl <= level:
                skip = False
            if re.search(r"entretien", m.group(2), re.I):
                skip, level = True, lvl
                continue
        if not skip:
            out.append(ln)
    return "\n".join(out)


def cited_numbers(md):
    text = strip_exempt_sections(md)
    text = re.sub(r"\]\([^)]*\)", "]", text)          # liens markdown : on ignore l'URL
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text)  # dates ISO
    found = []
    for m in NUM.finditer(text):
        raw = m.group()
        after, before = text[m.end():m.end() + 12], text[max(0, m.start() - 14):m.start()]
        n = norm(raw)
        if n is None:
            continue
        unit = UNIT_AFTER.match(after)
        is_int = "," not in raw and "." not in raw
        signed = raw[0] in "+-−"
        # « 3 points à surveiller » n'est pas une mesure ; « +0,2 point » ou « +3 points » en est une
        has_unit = bool(unit) and not (unit.group(1).lower().startswith("point") and is_int and not signed)
        if is_int and not has_unit:
            if 1990 <= n <= 2100:
                continue  # année
            if n <= 31:
                continue  # numérotation, jour, compte (« 3 points à surveiller »)
            if after.lstrip().lower().startswith(MONTHS):
                continue  # date
            if NAME_NUMBERS.search(before):
                continue  # « S&P 500 », « CAC 40 »
        if MATURITY_AFTER.match(after) and not has_unit:
            continue      # « 10 ans », « 3M », « 2s10s »
        if NAME_NUMBERS.search(before) and is_int:
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        ctx = text[line_start: line_end if line_end > 0 else None].strip()
        found.append({"nombre": raw, "valeur": n, "contexte": ctx[:160]})
    return found


def summaries_as_md(json_path):
    """Les résumés du top 10 (JSON) sont contrôlés comme un texte."""
    with open(json_path) as f:
        items = json.load(f).get("items", {})
    return "\n".join(f"- {v.get('summary', '')} {v.get('why', '')}" for v in items.values())


def check(md_path, brief_path=None):
    name = os.path.splitext(os.path.basename(md_path))[0]
    folder = os.path.basename(os.path.dirname(md_path))
    if md_path.endswith(".json"):
        md = summaries_as_md(md_path)
        if brief_path is None:  # les résumés utilisent le brief de la newsletter du même jour
            brief_path = os.path.join(ROOT, "content", "sources", f"newsletter-{name}.json")
    else:
        with open(md_path) as f:
            md = f.read()
    brief_path = brief_path or os.path.join(ROOT, "content", "sources", f"{folder}-{name}.json")
    result = {"fichier": os.path.relpath(md_path, ROOT), "brief": os.path.relpath(brief_path, ROOT)}
    if not os.path.exists(brief_path):
        result.update(ok=False, brief_valide=False, erreur="copie du brief absente", inconnus=[], verifies=0)
        return result
    with open(brief_path) as f:
        brief = json.load(f)
    result["brief_valide"] = brief.get("empreinte") == fingerprint(brief)
    allowed = allowed_numbers(brief)
    cited = cited_numbers(md)
    unknown = [{"nombre": c["nombre"], "contexte": c["contexte"]} for c in cited if c["valeur"] not in allowed]
    result.update(ok=result["brief_valide"] and not unknown, verifies=len(cited), inconnus=unknown,
                  brief_genere_le=brief.get("genere_le"))
    return result


if __name__ == "__main__":
    status = 0
    for path in sys.argv[1:]:
        r = check(path)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        status |= 0 if r["ok"] else 1
    sys.exit(status)


def check_all(prefix=""):
    """Contrôle tous les textes publiés (optionnellement ceux dont le nom commence par `prefix`)."""
    out = []
    for folder in ("newsletter", "wraps", "rapports", "news_summaries"):
        d = os.path.join(ROOT, "content", folder)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith(prefix) and name.endswith((".md", ".json")):
                out.append(check(os.path.join(d, name)))
    return out
