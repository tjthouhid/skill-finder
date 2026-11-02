# Skill Finder

Skill Finder tells you which of your installed AI agent skills to use for a
task, and how to install the ones you don't have yet.

This README is for developers who use Claude Code or Codex CLI and have more
skills installed than they can keep track of. After reading it, you can
install Skill Finder, ask it for a skill in plain words, and add your own
curated skill lists to it. It doesn't cover writing new skills or how any
individual skill works; for that, see the skill's own `SKILL.md`.

## How Skill Finder works

Skill Finder has three parts:

- **An index.** `build_index.py` reads the frontmatter of every `SKILL.md` in
  your skill folders, merges in curated knowledge about skill libraries, and
  writes the result to `data/skills.json`.
- **A ranker.** `find.py` scores every skill in the index against your
  request by keyword overlap and prints the best matches, with an install
  command for each one you're missing.
- **A skill.** `SKILL.md` tells your agent when to run `find.py` and how to
  turn its output into a short recommendation.

The index covers the following folders:

| Agent | Folders scanned |
|---|---|
| Claude Code | `~/.claude/skills` and every plugin's `skills` folder under `~/.claude/plugins/cache` |
| Codex CLI | `~/.codex/skills` and `~/.agents/skills` |

Curated sources live in `data/sources/*.json`. They add what a `SKILL.md`
alone doesn't say: a category, a "use when" line, install commands, and
journeys. A *journey* is a skill that walks you through a whole project
phase by phase using other skills, such as `create-website`. The first
source is the [Wondel.ai skills catalogue](https://skills.wondel.ai/skills):
51 skills, 14 journeys, and 8 example routes. A *route* is a suggested order
of skills for a common situation, such as an online shop that loses
customers at checkout.

Queries run offline. Neither script uses the network.

## Before you begin

- Python 3.9 or later, available as `python3`. The scripts use only the
  standard library.
- Claude Code, Codex CLI, or both.
- Optional: Node.js with `npx`, if you install through the `skills` CLI.

## Install

Choose one of the following methods.

### Install from GitHub

To install for Claude Code, Codex CLI, or both, run the matching command:

```sh
npx skills add tjthouhid/skill-finder -g -a claude-code
npx skills add tjthouhid/skill-finder -g -a codex
```

The `-g` flag installs the skill for your user account instead of a single
project. The Claude Code command installs to `~/.claude/skills/skill-finder`,
and the Codex CLI command installs to `~/.agents/skills/skill-finder`.

### Install from a local copy

To install from a folder on your machine, run:

```sh
npx skills add REPO_PATH -g -a claude-code
npx skills add REPO_PATH -g -a codex
```

Replace `REPO_PATH` with the path to this repository.

## Build the index for your machine

The `data/skills.json` file in this repository describes the author's
machine. When `find.py` finds an index that was built on another machine,
or one older than 30 days, it exits with code `2` and prints the command
that rebuilds it. Your agent runs that command and retries once, so this
step is optional.

To build the index yourself, run:

```sh
SKILL_DIR=~/.claude/skills/skill-finder
python3 -I "$SKILL_DIR/scripts/build_index.py"
```

For Codex CLI, set `SKILL_DIR` to `~/.agents/skills/skill-finder`, or to
`~/.codex/skills/skill-finder` if you linked the skill there by hand.

The script prints the path it wrote, the total number of skills, and a
count per source:

```text
Wrote /Users/you/.claude/skills/skill-finder/data/skills.json
total: 190
  gstack: 54
  wondel: 65
  ...
curated but not installed (0):
skipped (0):
```

## Confirm that it works

To confirm that Skill Finder can find itself, run:

```sh
python3 -I "$SKILL_DIR/scripts/find.py" "which skill finds skills" --top 1
```

The first result is `skill-finder`, marked as installed:

```text
## Skills
1. skill-finder  [installed: claude ✓ codex ✓]  score 8.91  (tjthouhid)
   Recommend which installed agent skill to use for a task.
```

## Find a skill

In Claude Code, run the skill with your need in plain words:

```text
/skill-finder human type web design for my portfolio
```

In Claude Code or Codex CLI, you can also ask in your own words, for
example "Which skill should I use to fix my slow checkout page?"

The reply has the following parts:

**Best fit**
: The skill that fits best, why, and whether it's installed.

**Also consider**
: Up to two more skills.

**Journey**
: A guided project skill, when your request is a whole project.

**Install**
: Install commands, only for skills missing in the tool you're using.

**Try this**
: A ready-to-paste prompt, such as `Use cro-methodology to find where
  shoppers leave checkout. Start with the smallest first step.`

### Run the finder from a terminal

To see the raw results without an agent, run `find.py` with your need. The
following command asks Codex CLI for help with a new landing page:

```sh
python3 -I "$SKILL_DIR/scripts/find.py" "build a landing page from scratch" \
  --tool codex --top 2
```

The output lists skills, then journeys, then routes. An `Install` line
appears under each item that's missing in the tool you named (output
shortened):

```text
## Skills
1. create-website  [installed: claude ✓ codex ✗]  score 9.51  (wondel)
   Guided journey from a blank page to a live, high-converting website, ...
   Install (codex): npx skills add wondelai/skills -s create-website -g -a codex
2. one-page-marketing  [installed: claude ✓ codex ✗]  score 5.10  (...)
   ...
## Journeys
1. create-website — Blank page → clear, designed, ... (10 phases) [installed ✗]
   Install (codex): npx skills add wondelai/skills -s create-website -g -a codex
## Routes that mention these
- Build a small local service website → one-page-marketing → ...
```

When nothing matches, `find.py` prints `No match.` and the list of
categories.

## Add a curated skill list

Use this when you find a skill catalogue, guide, or list that you want Skill
Finder to know about. Skills that you install are picked up automatically
the next time the index is built, without this step.

1. In Claude Code, ask: "Add these skills to skill finder", followed by a
   URL, a file path, or a pasted list.
2. Check the table of skills that your agent shows you, and confirm it or
   correct it.

   Your agent writes `data/sources/SOURCE.json` and rebuilds the index.
   `SOURCE` is the source name you confirmed.
3. Confirm that the new source appears in the per-source counts that
   `build_index.py` prints.

To write a source file by hand instead, follow the format in
[the source file schema](skill-finder/data/sources/_schema.md), then build
the index.

## Refresh the index

Rebuild the index after you install or remove skills. `find.py` also asks
for a rebuild when the index is more than 30 days old. To refresh it, run:

```sh
python3 -I "$SKILL_DIR/scripts/build_index.py"
```

In Claude Code or Codex CLI, you can also say "refresh the skill index".

## Command reference

### `find.py`

```text
python3 -I find.py QUERY... [--tool {claude|codex}] [--top N] [--json]
                            [--index PATH]
```

The following options control `find.py`:

| Option | Description | Default |
|---|---|---|
| `QUERY` | The need, in your own words. | Required |
| `--tool` | The tool whose installed state and install commands to show. | `claude` |
| `--top` | The number of skills and journeys to list. Must be 1 or more. | `8` |
| `--json` | Prints full records as JSON instead of Markdown. | Off |
| `--index` | The index file to read. | `data/skills.json` next to the scripts |

`find.py` returns the following exit codes:

| Code | Meaning |
|---|---|
| `0` | Results or `No match.` printed. |
| `1` | Empty query or invalid option. |
| `2` | The index is missing, unreadable, built on another machine, or more than 30 days old. The error message names the rebuild command. |

### `build_index.py`

```text
python3 -I build_index.py [--data DIR] [--claude-root PATH]...
                          [--codex-root PATH]... [--quiet]
```

The following options control `build_index.py`:

| Option | Description | Default |
|---|---|---|
| `--data` | The data folder. The script reads `DIR/sources/*.json` and writes `DIR/skills.json`. | `data` next to the scripts |
| `--claude-root` | A Claude Code skills folder to scan. Repeat it for more folders. Any value replaces all default Claude Code folders. | The Claude Code folders listed in [How Skill Finder works](#how-skill-finder-works) |
| `--codex-root` | A Codex CLI skills folder to scan. Repeat it for more folders. Any value replaces the defaults. | `~/.codex/skills` and `~/.agents/skills` |
| `--quiet` | Skips the summary. Warnings about invalid source files still print. | Off |

### Index record fields

Each skill in `data/skills.json`, and in `find.py --json`, has the
following fields, among others:

`installed`
: For each tool (`claude`, `codex`), true if the skill is installed there.

`install`
: For each tool, the command that installs the skill, or `null` when no
  install source is known.

`invoke`
: For each tool, the name you call the skill by. Claude Code plugin skills
  use `PLUGIN:SKILL`, such as `superpowers:brainstorming`. Other skills use
  their folder name. The value is `null` for a tool where the skill is
  neither installed nor installable.

`paths`
: For each tool, every `SKILL.md` found for the skill. The first path is the
  one whose frontmatter was read.

`source`
: Where the skill's details came from: a curated source such as `wondel`, a
  plugin name, the author in the frontmatter, or `unknown`.

`category`, `use_when`, `journeys`
: Curated details. For skills that no curated source describes, `category`
  and `use_when` are `null` and `journeys` is an empty list.

## Project layout

The repository has the following structure:

| Path | Contents |
|---|---|
| `skill-finder/SKILL.md` | The skill your agent reads. |
| `skill-finder/scripts/find.py` | The ranker. |
| `skill-finder/scripts/build_index.py` | The index builder. |
| `skill-finder/scripts/common.py` | The frontmatter parser and the source file loader. |
| `skill-finder/data/sources/` | Curated source files and their schema. |
| `skill-finder/data/skills.json` | The generated index. |
| `tests/` | Unit tests and test fixtures. |
| `docs/superpowers/` | The design spec and implementation plans. |

## Develop Skill Finder

To work on a clone, link it into your skill folders so that both agents use
your working copy:

```sh
ln -s "$PWD/skill-finder" ~/.claude/skills/skill-finder
ln -s "$PWD/skill-finder" ~/.codex/skills/skill-finder
```

Run these commands from the repository root.

To run the tests, run:

```sh
python3 -I -m unittest discover -s tests -t . -v
```

## Limitations

- Ranking matches keywords and a small synonym list, not meaning. If a
  request returns nothing useful, rephrase it with the words a skill
  description would use.
- Add mode needs an agent to read and extract the list. No script does it.

## License

MIT. See [LICENSE](LICENSE).
