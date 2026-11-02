# Skill Finder

An agent skill that indexes every installed `SKILL.md` (Claude Code and Codex CLI) together with curated knowledge about skill libraries, then recommends which skill to use for a task, which journey fits a whole project, and the exact install command for anything you are missing. Pure Python 3.9+ standard library; no network at query time.

## Install

```sh
npx skills add tjthouhid/skill-finder -g -a claude-code
npx skills add tjthouhid/skill-finder -g -a codex
```

First run on a new machine: the shipped `data/skills.json` describes the author's machine. Run `python3 -I skill-finder/scripts/build_index.py` (the skill does this itself when the index is missing or older than 30 days) to regenerate it for yours.

## Example

> `/skill-finder human type web design for my portfolio`

The reply has five labelled parts: **Best fit**, **Also consider**, **Journey**, **Install** (only for skills you lack in the current tool), and **Try this** (a ready prompt such as `Use refactoring-ui to ... Start with the smallest first step.`).

CLI directly: `python3 -I skill-finder/scripts/find.py "shoppers leave at checkout" --tool claude --top 5`

## Adding a source

Say "add these skills to skill finder" with a URL, file, or pasted list. The agent extracts skills, asks you to confirm, writes `skill-finder/data/sources/<source>.json`, and rebuilds the index. The file format is in [`skill-finder/data/sources/_schema.md`](skill-finder/data/sources/_schema.md).

## Development

```sh
python3 -I -m unittest discover -s tests -t . -v
```
