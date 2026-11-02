#!/usr/bin/env python3
"""Rank installed/curated skills against a plain-language need.

Usage: python3 -I find.py "query text" [--tool claude|codex] [--top N] [--json]
Exit codes: 0 ok, 1 usage, 2 skills.json missing/unreadable.
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

STOPWORDS = {
    "i", "me", "my", "we", "our", "you", "your", "the", "a", "an", "at", "to",
    "for", "of", "in", "on", "and", "or", "is", "are", "was", "were", "be",
    "am", "it", "its", "this", "that", "these", "those", "with", "before",
    "after", "not", "no", "do", "does", "don't", "dont", "what", "which",
    "how", "want", "need", "should", "use", "can", "from", "by", "as", "but",
    "if", "so", "about", "into", "have", "has", "had", "will", "would", "than",
    "then", "them", "they", "there", "when", "who", "why",
}

SYNONYMS = {
    "web design": "ui frontend landing visual interface",
    "human": "taste handcrafted anti-slop distinctive intentional",
    "generic": "templated slop",
    "checkout": "conversion funnel cart",
    "abandon": "drop-off leave",
    "slow": "performance speed latency",
    "legacy": "untested old seams",
    "scared": "risky safe",
    "customers": "prospects buyers users",
    "customer": "prospects buyers users",
    "understand": "clarity positioning message",
    "launch": "release production",
    "api": "external service network",
    "landing page": "website homepage",
    "retention": "return habit churn",
    "price": "pricing willingness pay",
    "pricing": "price willingness pay",
}

FIELD_WEIGHTS = (
    ("name", 4), ("display_name", 4), ("aliases", 4), ("use_when", 3),
    ("category", 2), ("summary", 2), ("description", 1),
)
JOURNEY_WEIGHTS = (("name", 4), ("tagline", 3), ("fits", 3))
MIN_SCORE = 1.0

_SPLIT = re.compile(r"[\W_]+", re.UNICODE)


def _stem(tok):
    for suf in ("ing", "ed", "es", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def tokenize(text):
    out = []
    # Whitespace pieces first so "don't" can hit the stopword list as one word.
    for piece in text.lower().replace("\u2019", "'").split():
        if piece.strip("\"'.,;:!?()[]{}") in STOPWORDS:
            continue
        for raw in _SPLIT.split(piece):
            if len(raw) < 2 or raw in STOPWORDS:
                continue
            out.append(_stem(raw))
    return out


def expand(tokens, raw):
    low = raw.lower()
    terms = list(tokens)
    for key, syn in SYNONYMS.items():
        if re.search(r"(?<!\w)" + re.escape(key) + r"\w{0,3}(?!\w)", low):
            terms.extend(tokenize(syn))
    seen, out = set(), []
    for t in terms:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def score_text(terms, text, weight):
    toks = tokenize(text)
    if not toks or not terms:
        return 0.0
    present = set(toks)
    hits = sum(1 for t in set(terms) if t in present)
    return weight * hits / (1 + math.log(1 + len(toks)))


def _bigrams(tokens):
    return [" ".join(p) for p in zip(tokens, tokens[1:])]


def _field_text(rec, field):
    val = rec.get(field) or ""
    if isinstance(val, (list, tuple)):
        val = " ".join(str(v) for v in val)
    return str(val)


def _score(terms, bigrams, texts_weights):
    total = 0.0
    joined = []
    for text, weight in texts_weights:
        total += score_text(terms, text, weight)
        joined.append(" ".join(tokenize(text)))
    for bg in bigrams:
        if any((" " + bg + " ") in (" " + j + " ") for j in joined):
            total += 2
    return total


def score_skill(terms, bigrams, rec):
    return _score(terms, bigrams, [(_field_text(rec, f), w) for f, w in FIELD_WEIGHTS])


def score_journey(terms, bigrams, j):
    tw = [(_field_text(j, f), w) for f, w in JOURNEY_WEIGHTS]
    tw.append((" ".join(j.get("skills") or []), 1))
    return _score(terms, bigrams, tw)


def search(index, query, top=8):
    tokens = tokenize(query)
    terms = expand(tokens, query)
    bigrams = _bigrams(tokens)
    skills = []
    for slug, rec in index.get("skills", {}).items():
        s = score_skill(terms, bigrams, rec)
        if s >= MIN_SCORE:
            skills.append((s, rec))
    skills.sort(key=lambda p: (-p[0], p[1].get("slug", "")))
    skills = skills[:top]
    journeys = []
    for j in index.get("journeys", []):
        s = score_journey(terms, bigrams, j)
        if s >= MIN_SCORE:
            journeys.append((s, j))
    journeys.sort(key=lambda p: (-p[0], p[1].get("slug", "")))
    journeys = journeys[:top]
    top3 = {r["slug"] for _, r in skills[:3]}
    ranked = []
    for pos, r in enumerate(index.get("routes", [])):
        n = len(top3 & {step[0] for step in r.get("steps", [])})
        if n:
            ranked.append((-n, pos, r))
    ranked.sort(key=lambda t: (t[0], t[1]))
    routes = [r for _, _, r in ranked]
    return {"skills": skills, "journeys": journeys, "routes": routes}


def _mark(flag):
    return "✓" if flag else "✗"


def render_markdown(results, tool, index):
    skills, journeys = results["skills"], results["journeys"]
    if not skills and not journeys:
        return "No match. Categories: " + ", ".join(index.get("categories", []))
    lines = []
    if skills:
        lines.append("## Skills")
        for n, (score, rec) in enumerate(skills, 1):
            inst = rec.get("installed", {})
            tail = ", ".join(x for x in (rec.get("category"), rec.get("source")) if x)
            lines.append(
                "%d. %s  [installed: claude %s codex %s]  score %.2f  (%s)"
                % (n, rec["slug"], _mark(inst.get("claude")), _mark(inst.get("codex")), score, tail)
            )
            if rec.get("summary"):
                lines.append("   " + rec["summary"])
            uw = re.sub(r"^use when[:\s]*", "", rec.get("use_when") or "", flags=re.I)
            if uw:
                lines.append("   Use when: " + uw)
            cmd = (rec.get("install") or {}).get(tool)
            if not inst.get(tool) and cmd:
                lines.append("   Install (%s): %s" % (tool, cmd))
    if journeys:
        lines.append("## Journeys")
        for n, (score, j) in enumerate(journeys, 1):
            ok = (j.get("installed") or {}).get(tool)
            lines.append(
                "%d. %s — %s (%s phases) [installed %s]"
                % (n, j["slug"], j.get("tagline", ""), j.get("phases", "?"), _mark(ok))
            )
    if results["routes"]:
        lines.append("## Routes that mention these")
        for r in results["routes"]:
            chain = " → ".join(step[0] for step in r.get("steps", []))
            lines.append("- %s → %s" % (r["name"], chain))
    return "\n".join(lines)


def load_index(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _results_json(query, tool, results):
    return {
        "query": query,
        "tool": tool,
        "skills": [
            dict({"score": round(s, 2), "slug": r["slug"]}, **{k: v for k, v in r.items() if k != "slug"})
            for s, r in results["skills"]
        ],
        "journeys": [dict({"score": round(s, 2)}, **j) for s, j in results["journeys"]],
        "routes": results["routes"],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("find.py: error: %s\n" % message)
        raise SystemExit(1)


def main(argv=None):
    p = _Parser(prog="find.py", description="Find the right skill for a need.")
    p.add_argument("query", nargs="*", help="what you want to do")
    p.add_argument("--tool", choices=("claude", "codex"), default="claude")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--index", type=Path, default=None)
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    query = " ".join(args.query).strip()
    if not query or args.top < 1:
        p.print_usage(sys.stderr)
        sys.stderr.write("find.py: a non-empty query and --top >= 1 are required\n")
        return 1
    scripts = Path(__file__).resolve().parent
    path = args.index or scripts.parent / "data" / "skills.json"
    try:
        index = load_index(path)
    except FileNotFoundError:
        sys.stderr.write(
            "skills.json not found at %s. Run: python3 -I %s\n"
            % (path, scripts / "build_index.py")
        )
        return 2
    except (OSError, ValueError) as e:
        sys.stderr.write(
            "cannot read %s (%s). Run: python3 -I %s\n" % (path, e, scripts / "build_index.py")
        )
        return 2
    results = search(index, query, args.top)
    if args.as_json:
        print(json.dumps(_results_json(query, args.tool, results), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(results, args.tool, index))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
