#!/usr/bin/env python3
"""Rank installed/curated skills against a plain-language need.

Usage: python3 -I find.py "query text" [--tool claude|codex] [--top N] [--json]
Exit codes: 0 ok, 1 usage, 2 skills.json missing/unreadable/malformed, built for
another machine, or older than 30 days (run build_index.py, then retry).
"""
import argparse
import json
import math
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone
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
    "generated": "slop templated generic",
    "ai-generated": "slop templated generic",
    "checkout": "conversion funnel cart cro",
    "abandon": "drop-off leave",
    "leave": "drop-off abandon",
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
SYNONYM_WEIGHT = 0.5
NO_STEM = {"landing"}
MIN_SCORE = 1.0
# A term found in more skills than this share (and this count) is weak evidence: "design" alone
COMMON_SHARE = 0.05
COMMON_MIN = 5
# Leading skills scoring within this share of the top score are a close call: let Use when decide
CLOSE_SHARE = 0.05
CLOSE_MAX = 3
MAX_INDEX_AGE = timedelta(days=30)
_USE_PREFIX = re.compile(r"^use\b(?:\s+(?:when|for|before|whenever|as|in)\b)?[:\s]*", re.I)

_SPLIT = re.compile(r"[\W_]+", re.UNICODE)


def _stem(tok):
    if tok in NO_STEM:
        return tok
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
    """Return {term: weight}: query tokens weigh 1, synonym-only terms SYNONYM_WEIGHT."""
    low = raw.lower()
    terms = dict.fromkeys(tokens, 1.0)
    for key, syn in SYNONYMS.items():
        if re.search(r"(?<!\w)" + re.escape(key) + r"\w{0,3}(?!\w)", low):
            if "-" in key:  # one concept ("ai-generated"): its parts are not separate topics
                for t in tokenize(key):
                    terms[t] = SYNONYM_WEIGHT
            for t in tokenize(syn):
                terms.setdefault(t, SYNONYM_WEIGHT)
    return terms


def damp_common(terms, records):
    """Return terms with weights lowered for terms that appear in many records.

    A term in more than max(COMMON_SHARE * n, COMMON_MIN) of the n records is scaled by
    log(1 + n/df) / log(1 + n/threshold), so it still counts, but less than a rare term.
    """
    records = list(records)
    n = len(records)
    threshold = max(COMMON_SHARE * n, COMMON_MIN)
    df = dict.fromkeys(terms, 0)
    for rec in records:
        seen = set()
        for field, _ in FIELD_WEIGHTS:
            seen.update(tokenize(_field_text(rec, field)))
        for t in terms:
            if t in seen:
                df[t] += 1
    return {t: w * math.log(1 + n / df[t]) / math.log(1 + n / threshold) if df[t] > threshold else w
            for t, w in terms.items()}


def score_text(terms, text, weight):
    toks = tokenize(text)
    if not toks or not terms:
        return 0.0
    if not isinstance(terms, dict):
        terms = dict.fromkeys(terms, 1.0)
    present = set(toks)
    hits = sum(w for t, w in terms.items() if t in present)
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
    terms = damp_common(expand(tokens, query), index.get("skills", {}).values())
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


def close_call(skills):
    """Return slugs of the leading skills within CLOSE_SHARE of the top score, or [] if the top is clear."""
    if not skills:
        return []
    floor = skills[0][0] * (1 - CLOSE_SHARE)
    close = [r["slug"] for s, r in skills[:CLOSE_MAX] if s >= floor]
    return close if len(close) > 1 else []


def _mark(flag):
    return "✓" if flag else "✗"


def _clean_use_when(text):
    """Drop a leading 'Use [when|for|before|...]' so the caller can add its own label."""
    return _USE_PREFIX.sub("", (text or "").strip(), count=1)


def render_markdown(results, tool, index):
    skills, journeys = results["skills"], results["journeys"]
    if not skills and not journeys:
        return (
            "No match. Categories: " + ", ".join(index.get("categories", [])) + "\n"
            "Rephrase with words a skill description would use, or name a category above. "
            "If you installed skills since the last build, rebuild the index with build_index.py."
        )
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
            invoke = (rec.get("invoke") or {}).get(tool)
            if invoke and invoke != rec["slug"]:
                lines.append("   Invoke (%s): %s" % (tool, invoke))
            if rec.get("summary"):
                lines.append("   " + rec["summary"])
            uw = _clean_use_when(rec.get("use_when"))
            if uw:
                lines.append("   Use when: " + uw)
            cmd = (rec.get("install") or {}).get(tool)
            if not inst.get(tool) and cmd:
                lines.append("   Install (%s): %s" % (tool, cmd))
        close = close_call(skills)
        if close:
            lines.append("Close call: %s (scores within %d%%; choose by Use when)"
                         % (", ".join(close), round(CLOSE_SHARE * 100)))
    if journeys:
        lines.append("## Journeys")
        for n, (score, j) in enumerate(journeys, 1):
            ok = (j.get("installed") or {}).get(tool)
            lines.append(
                "%d. %s — %s (%s phases) [installed %s]"
                % (n, j["slug"], j.get("tagline", ""), j.get("phases", "?"), _mark(ok))
            )
            cmd = (j.get("install") or {}).get(tool)
            if not ok and cmd:
                lines.append("   Install (%s): %s" % (tool, cmd))
    if results["routes"]:
        lines.append("## Routes that mention these")
        for r in results["routes"]:
            chain = " → ".join(step[0] for step in r.get("steps", []))
            lines.append("- %s → %s" % (r["name"], chain))
    return "\n".join(lines)


def load_index(path):
    with open(path, encoding="utf-8") as fh:
        index = json.load(fh)
    if not isinstance(index, dict) or not isinstance(index.get("skills"), dict):
        raise ValueError("not a skills index")
    return index


def index_problem(index, now=None):
    """Return a reason string when the index is foreign to this machine or stale, else None."""
    home = Path.home().parts
    roots = index.get("roots")
    recorded = [r for v in (roots.values() if isinstance(roots, dict) else ())
                if isinstance(v, list) for r in v if isinstance(r, str)]
    # No recorded roots: nothing to compare, treat as local. Otherwise at least one must sit under HOME.
    if recorded and not any(Path(r).parts[:len(home)] == home for r in recorded):
        return "built for another machine"
    try:
        built = datetime.strptime(index["generated_at"], "%Y-%m-%dT%H:%M:%SZ")
        built = built.replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return "has no valid generated_at"
    if (now or datetime.now(timezone.utc)) - built > MAX_INDEX_AGE:
        return "is more than 30 days old"
    return None


def _results_json(query, tool, results):
    return {
        "query": query,
        "tool": tool,
        "skills": [
            dict({"score": round(s, 2), "slug": r["slug"]}, **{k: v for k, v in r.items() if k != "slug"})
            for s, r in results["skills"]
        ],
        "close_call": close_call(results["skills"]),
        "journeys": [dict({"score": round(s, 2)}, **j) for s, j in results["journeys"]],
        "routes": results["routes"],
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("find.py: error: %s\nRun find.py --help for options.\n" % message)
        raise SystemExit(1)


def main(argv=None):
    p = _Parser(
        prog="find.py",
        description="Find the right skill for a need.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            '  find.py "my checkout page loses customers"\n'
            '  find.py "build a landing page from scratch" --tool codex --top 2\n'
            "\n"
            "exit codes:\n"
            "  0  results or 'No match.' printed\n"
            "  1  empty query or invalid option\n"
            "  2  index missing, unreadable, from another machine, or older\n"
            "     than 30 days; the message names the rebuild command"
        ),
    )
    p.add_argument("query", nargs="*", help="what you want to do, in your own words")
    p.add_argument("--tool", choices=("claude", "codex"), default="claude",
                   help="tool whose installed state and install commands to show (default: claude)")
    p.add_argument("--top", type=int, default=8, metavar="N",
                   help="number of skills and journeys to list, 1 or more (default: 8)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="print full records as JSON instead of Markdown")
    p.add_argument("--index", type=Path, default=None, metavar="PATH",
                   help="index file to read (default: data/skills.json next to the scripts)")
    try:
        args = p.parse_args(argv)
        query = " ".join(args.query).strip()
        if not query:
            p.error('give a need to search for, for example: find.py "my checkout page loses customers"')
        if args.top < 1:
            p.error("--top must be 1 or more, got %d" % args.top)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    scripts = Path(__file__).resolve().parent
    path = args.index or scripts.parent / "data" / "skills.json"
    build = "python3 -I " + shlex.quote(str(scripts / "build_index.py"))
    try:
        index = load_index(path)
    except FileNotFoundError:
        sys.stderr.write("skills.json not found at %s. Run: %s\n" % (path, build))
        return 2
    except (OSError, ValueError) as e:
        sys.stderr.write("cannot read %s (%s). Run: %s\n" % (path, e, build))
        return 2
    if index_problem(index):
        sys.stderr.write("skills.json was built for another machine or is stale. Run: %s\n" % build)
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
