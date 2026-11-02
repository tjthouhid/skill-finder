# Skill Finder

An agent skill that indexes every installed `SKILL.md` (Claude Code and Codex CLI) together with curated knowledge about skill libraries, then recommends which skill to use for a task, which journey fits a whole project, and the exact install command for anything you are missing. Pure Python 3.9+ standard library; no network at query time.

## Install

```sh
npx skills add tjthouhid/skill-finder -g -a claude-code
npx skills add tjthouhid/skill-finder -g -a codex
```

First run on a new machine: the shipped `data/skills.json` describes the author's machine, so `find.py` exits 2 and prints a one-line hint to rebuild (it does the same when the index is missing or older than 30 days). The skill runs the rebuild for you and retries once; to do it by hand, with `$SKILL_DIR` set to the installed skill directory (e.g. `~/.claude/skills/skill-finder`):

```sh
python3 -I "$SKILL_DIR/scripts/build_index.py"
```

## Example

> `/skill-finder human type web design for my portfolio`

The reply has five labelled parts: **Best fit**, **Also consider**, **Journey**, **Install** (only for skills you lack in the current tool), and **Try this** (a ready prompt such as `Use refactoring-ui to ... Start with the smallest first step.`).

CLI directly: `python3 -I "$SKILL_DIR/scripts/find.py" "shoppers leave at checkout" --tool claude --top 5`

## Adding a source

Say "add these skills to skill finder" with a URL, file, or pasted list. The agent extracts skills, asks you to confirm, writes `$SKILL_DIR/data/sources/<source>.json`, and rebuilds the index. The file format is in [`data/sources/_schema.md`](skill-finder/data/sources/_schema.md).

## Development (from a clone)

Repo-relative paths, run from the repository root:

```sh
python3 -I skill-finder/scripts/build_index.py
python3 -I skill-finder/scripts/find.py "shoppers leave at checkout"
```

Tests:

```sh
python3 -I -m unittest discover -s tests -t . -v
```
