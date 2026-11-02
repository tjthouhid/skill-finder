---
name: skill-finder
description: 'Recommend which installed agent skill to use for a task. Indexes every installed SKILL.md (Claude Code and Codex CLI) plus curated knowledge about skill libraries, then returns the best-fit skills, related journeys, and install commands for anything missing. Use when the user says "which skill should I use", "what skill for", "is there a skill for", "find me a skill", "recommend a skill", or "/skill-finder". Add mode: when the user says "add these skills to skill finder" or "index a new skills guide", extract skills from a URL, file, or pasted list into a curated source and rebuild the index. Also use for "refresh the skill index".'
license: MIT
metadata:
  author: tjthouhid
  version: "0.1.0"
---

# Skill Finder

Recommends skills from a local index (`data/skills.json`). Two modes: **Find** (default) and **Add**.

## Where the scripts are

`SKILL_DIR` is the directory containing this SKILL.md. Scripts live in `$SKILL_DIR/scripts`, data in `$SKILL_DIR/data`.
Always run them as `python3 -I "$SKILL_DIR/scripts/<name>.py"` (stdlib only, no installs needed).

- `find.py "<need>" [--tool claude|codex] [--top N] [--json]` — default tool `claude`. Exit 1 = usage error, exit 2 = `skills.json` missing, unreadable, built for another machine, or older than 30 days (the message names `build_index.py`).
- `build_index.py [--data DIR] [--claude-root P ...] [--codex-root P ...] [--quiet]` — rebuilds `data/skills.json`, prints counts.

## Find mode

1. Pick the tool: `codex` if you are running under Codex CLI, else `claude`.
2. Run `python3 -I "$SKILL_DIR/scripts/find.py" "<the user's need, in their words>" --tool <tool>`. Append the project's language/stack if the user gave it. If it exits 2, run `python3 -I "$SKILL_DIR/scripts/build_index.py"` and re-run `find.py` once.
3. Read the top results. Pick 2–4 skills that actually fit; drop near-duplicates (prefer the installed one; prefer the Wondel one when a gstack/other skill overlaps and the ask is advice-shaped). If the ask is a whole project ("build me a…", "my site is failing"), lead with the matching journey and list its skills under it.
4. Reply in this format (short, no preamble):
   - **Best fit** — slug, one line why, installed/not.
   - **Also consider** — up to 2 more.
   - **Journey** — if applicable.
   - **Install** — only lines for skills missing in the current tool, copied from the `Install (<tool>):` lines in the output; for unknown-source skills say "already installed" (or "no known install source" if missing).
   - **Try this** — one ready prompt: `Use <slug> [and <slug>] to <user's goal in their words>. Start with the smallest first step.`
5. If the output says `No match.` or nothing fits, say so and suggest the closest category it lists, or run `build_index.py` if the index looks stale.
6. Never invent install commands or skills not in the index.

## Add mode

Triggered by "add these skills to skill finder", "/skill-finder add <url|file|pasted list>", or "index a new skills guide".

1. Read the input (URL via fetch, local file, or pasted text). Extract per skill: name, slug, summary, use_when, category; per journey: name, slug, member skills; plus the install command for the whole set if the input states one.
2. Show the user a short table of what was extracted and the proposed source name; ask them to confirm or correct before writing.
3. Write `$SKILL_DIR/data/sources/<source>.json` following `$SKILL_DIR/data/sources/_schema.md` (slug = installed directory name). If a file for that source exists, merge: append new skills, update existing fields, delete nothing silently.
4. Run `build_index.py`; report the counts and any slugs that match nothing installed.
5. Suggest a commit; do not commit unasked.

## Refresh

`python3 -I "$SKILL_DIR/scripts/build_index.py"` — run when the index is older than 30 days, after installing skills, or when the user says "refresh". Installed skills are picked up automatically; no Add mode needed for those.

## Rules

- Never invent install commands or skills that are not in the index.
- When scores tie, prefer an installed skill over an uninstalled one.
- Drop near-duplicates; keep the answer to 2–4 skills.
- Show an install line only for skills missing in the current tool; none for installed skills.
- Do not install anything yourself; give the command and let the user run it.
