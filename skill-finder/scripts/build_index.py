"""Build data/skills.json: scan installed SKILL.md files and merge curated sources."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (default_roots, expand_install, first_sentence, load_sources,  # noqa: E402
                    parse_frontmatter)

AGENTS = ("claude", "codex")
INSTALL_AGENT = {"claude": "claude-code", "codex": "codex"}


def scan_root(root):
    """Return {slug: SKILL.md path} for each visible child dir (symlinks followed) holding SKILL.md."""
    found = {}
    try:
        children = sorted(Path(root).iterdir())
    except OSError:
        return found
    for child in children:
        if child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if skill_md.is_file():
            found[child.name] = skill_md
    return found


def _plugin_ref(path):
    """'<plugin>@<marketplace>' when path sits under .../plugins/cache/<marketplace>/<plugin>/."""
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "cache" and i > 0 and parts[i - 1] == "plugins" and i + 2 < len(parts) - 1:
            return f"{parts[i + 2]}@{parts[i + 1]}"
    return None


def detect_source(slug, meta, path, source_index):
    """Return (source, author, plugin_ref) for an installed skill.

    source_index maps a slug (or alias) to {"sources_seen": [...], ...}; its first source wins.
    """
    author = _author(meta)
    plugin_ref = _plugin_ref(Path(path))
    seen = (source_index.get(slug) or {}).get("sources_seen")
    if seen:
        return seen[0], author, plugin_ref
    if plugin_ref:
        return plugin_ref.split("@", 1)[0], author, plugin_ref
    if author:
        return author.lower(), author, None
    if str(meta.get("description", "")).rstrip().endswith("(gstack)"):
        return "gstack", author, None
    return "unknown", author, None


def _title(slug):
    return " ".join(w[:1].upper() + w[1:] for w in slug.split("-") if w)


def _index_sources(sources):
    """Map slug -> curated entries and alias -> curated entries (slug keys take precedence).

    A journey's slug is also an installable skill, so a source's journeys count as mentions
    (name only) even though they are not listed in its skills[].
    """
    by_slug, by_alias = {}, {}
    for src in sources:
        for skill in src["skills"]:
            by_slug.setdefault(skill["slug"], []).append((src, skill))
            for alias in skill.get("aliases", []):
                by_alias.setdefault(alias, []).append((src, skill))
        listed = {sk["slug"] for sk in src["skills"]}
        for journey in src.get("journeys", []):
            if journey["slug"] not in listed:
                by_slug.setdefault(journey["slug"], []).append(
                    (src, {"slug": journey["slug"], "name": journey["name"]}))
    merged = {}
    for key, entries in list(by_alias.items()) + list(by_slug.items()):
        merged[key] = entries
    return {
        key: {"entries": entries, "sources_seen": _distinct(s["source"] for s, _ in entries)}
        for key, entries in merged.items()
    }


def _distinct(items):
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


def _first(entries, field):
    for _, skill in entries:
        if skill.get(field):
            return skill[field]
    return None


def _install(entries, plugin_ref):
    # expand with the curated entry's slug: an alias-matched dir name may not exist in the source
    for src, skill in entries:
        if src.get("install"):
            return {a: expand_install(src["install"], skill["slug"], INSTALL_AGENT[a])
                    for a in AGENTS}
    if plugin_ref:
        return {"claude": f"/plugin install {plugin_ref}", "codex": None}
    return {"claude": None, "codex": None}


def _author(meta):
    metadata = meta.get("metadata")
    author = metadata.get("author") if isinstance(metadata, dict) else None
    return author.strip() if isinstance(author, str) and author.strip() else None


def _claim_entries(slug, meta, entries):
    """Curated entries an installed dir may take: its own slug's, else alias entries it proves.

    An alias claims the dir when the dir's frontmatter name is the curated slug, its author
    matches the source (author "wondelai" for source "wondel"), or it has no author and the alias
    names one curated skill across all sources. Otherwise an unrelated dir that happens to share
    an alias's name (e.g. "refactoring") keeps its own identity.
    """
    primary = [e for e in entries if e[1]["slug"] == slug]
    if primary:
        return primary
    author = _author(meta)
    unique = len({sk["slug"] for _, sk in entries}) == 1
    return [(src, sk) for src, sk in entries
            if meta.get("name") == sk["slug"]
            or (author.lower().startswith(src["source"]) if author else unique)]


def _read_installed(roots, skipped):
    """Return {slug: {"paths": {agent: [Path, ...]}, "meta": dict}}.

    Every root holding the slug is kept, in root order; only an agent's first path is parsed.
    """
    paths = {}
    for agent in AGENTS:
        for root in roots.get(agent, []):
            for slug, path in scan_root(Path(root)).items():
                paths.setdefault(slug, {}).setdefault(agent, []).append(path)
    installed = {}
    for slug in sorted(paths):
        good, meta = {}, None
        for agent in AGENTS:
            found = paths[slug].get(agent)
            if not found:
                continue
            try:
                parsed, _ = parse_frontmatter(found[0].read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                skipped.append(f"{slug}: {found[0]}: {exc}")
                continue
            good[agent] = found
            if meta is None:
                meta = parsed
        if good:
            installed[slug] = {"paths": good, "meta": meta}
    return installed


def build_index(roots, sources):
    """Return (index, stats) from installed skills under roots merged with curated sources."""
    source_index = _index_sources(sources)
    skipped = []
    installed = _read_installed(roots, skipped)

    curated_slugs = _distinct(sk["slug"] for src in sources for sk in src["skills"])
    claims = {slug: _claim_entries(slug, info["meta"], source_index.get(slug, {}).get("entries", []))
              for slug, info in installed.items()}
    claimed = {skill["slug"] for entries in claims.values() for _, skill in entries}

    journey_members = {}
    journeys, seen_journeys = [], set()
    for src in sources:
        for journey in src.get("journeys", []):
            if journey["slug"] in seen_journeys:
                continue
            seen_journeys.add(journey["slug"])
            journeys.append((src, journey))
            for member in journey["skills"]:
                journey_members.setdefault(member, []).append(journey["slug"])

    def record(slug, entries, seen, meta, paths, plugin_ref, source, author):
        description = meta.get("description", "") if meta else ""
        description = description if isinstance(description, str) else ""
        curated_name = _first(entries, "name")
        aliases = _distinct(a for _, sk in entries for a in sk.get("aliases", []))
        install = _install(entries, plugin_ref)
        # Claude Code names plugin skills <plugin>:<skill>; codex has none unless installed/installable
        invoke = {"claude": f"{plugin_ref.split('@', 1)[0]}:{slug}" if plugin_ref else slug,
                  "codex": slug if "codex" in paths or install["codex"] else None}
        return {
            "slug": slug,
            "name": (meta or {}).get("name") or slug,
            "display_name": curated_name or _title(slug),
            "description": description,
            "summary": _first(entries, "summary") or first_sentence(description),
            "use_when": _first(entries, "use_when"),
            "category": _first(entries, "category"),
            "guide_slug": _first(entries, "guide_slug"),
            "source": source,
            "sources_seen": seen,
            "author": author,
            "install": install,
            "invoke": invoke,
            "installed": {a: a in paths for a in AGENTS},
            "paths": {a: [str(p) for p in ps] for a, ps in paths.items()},
            "journeys": journey_members.get(slug, []),
            "aliases": aliases,
        }

    skills = {}
    for slug, info in installed.items():
        entries = claims[slug]
        seen = _distinct(s["source"] for s, _ in entries)
        meta = info["meta"]
        first_path = (info["paths"].get("claude") or info["paths"]["codex"])[0]
        source, author, plugin_ref = detect_source(slug, meta, first_path,
                                                   {slug: {"sources_seen": seen}} if seen else {})
        skills[slug] = record(slug, entries, seen, meta, info["paths"], plugin_ref, source, author)

    not_installed = []
    for slug in curated_slugs:
        if slug in skills or slug in claimed:
            continue
        entries = source_index[slug]["entries"]
        entries = [e for e in entries if e[1]["slug"] == slug]
        seen = _distinct(s["source"] for s, _ in entries)
        skills[slug] = record(slug, entries, seen, None, {}, None, seen[0], None)
        not_installed.append(slug)

    journey_out = []
    for src, journey in journeys:
        item = dict(journey)
        item["source"] = src["source"]
        item["install"] = {a: expand_install(src.get("install"), journey["slug"], INSTALL_AGENT[a])
                           for a in AGENTS}
        rec = skills.get(journey["slug"])
        item["installed"] = dict(rec["installed"]) if rec else {a: False for a in AGENTS}
        journey_out.append(item)
    routes = []
    for src in sources:
        for route in src.get("routes", []):
            item = dict(route)
            item["source"] = src["source"]
            routes.append(item)

    by_source = {}
    for rec in skills.values():
        by_source[rec["source"]] = by_source.get(rec["source"], 0) + 1
    index = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "roots": {a: [str(r) for r in roots.get(a, [])] for a in AGENTS},
        "categories": sorted({c for src in sources for c in src.get("categories", [])}),
        "sources": [{"source": s["source"], "label": s["label"], "homepage": s.get("homepage")}
                    for s in sources],
        "skills": skills,
        "journeys": journey_out,
        "routes": routes,
    }
    stats = {"total": len(skills), "by_source": by_source, "skipped": skipped,
             "curated_not_installed": sorted(not_installed)}
    return index, stats


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _UsageError(message)


def main(argv=None):
    parser = _Parser(
        prog="build_index.py",
        description="Build data/skills.json from installed skills and curated sources.",
        epilog="Run it after you install or remove skills.",
    )
    parser.add_argument("--data", metavar="DIR",
                        help="data folder: reads DIR/sources/*.json, writes DIR/skills.json "
                             "(default: data next to the scripts)")
    parser.add_argument("--claude-root", action="append", default=[], metavar="PATH",
                        help="Claude Code skills folder to scan; repeat for more. "
                             "Any value replaces the defaults")
    parser.add_argument("--codex-root", action="append", default=[], metavar="PATH",
                        help="Codex CLI skills folder to scan; repeat for more. "
                             "Any value replaces the defaults")
    parser.add_argument("--quiet", action="store_true",
                        help="skip the summary; source-file warnings still print")
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        print(f"build_index.py: {exc}\nRun build_index.py --help for options.", file=sys.stderr)
        return 1

    data_dir = Path(args.data) if args.data else Path(__file__).resolve().parent.parent / "data"
    roots = default_roots()
    if args.claude_root:
        roots["claude"] = [Path(p) for p in args.claude_root]
    if args.codex_root:
        roots["codex"] = [Path(p) for p in args.codex_root]

    sources, warnings = load_sources(data_dir / "sources")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    index, stats = build_index(roots, sources)

    out = data_dir / "skills.json"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                       encoding="utf-8")
    except OSError as exc:
        print(f"build_index.py: cannot write {out}: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"Wrote {out}")
        print(f"total: {stats['total']}")
        for name, n in sorted(stats["by_source"].items()):
            print(f"  {name}: {n}")
        print(f"curated but not installed ({len(stats['curated_not_installed'])}): "
              + ", ".join(stats["curated_not_installed"]))
        print(f"skipped ({len(stats['skipped'])}): " + "; ".join(stats["skipped"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
