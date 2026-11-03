# Changelog

This file lists the changes that affect people who use Skill Finder. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added

- When the top skills score within 5% of each other, `find.py` flags them
  as a close call, and the agent's reply says when to pick each one.
  `--json` lists them in `close_call`.
- `find.py --help` and `build_index.py --help` describe every option and
  its default. `find.py --help` also lists examples and exit codes.

### Changed

- Usage errors name the problem and point to `--help`. An empty query shows
  an example request, and a bad `--top` value is printed back.
- `No match.` now suggests rephrasing the request, naming a category, or
  rebuilding the index.

### Fixed

- When the index needs a rebuild, the error gives the real reason: built
  for another machine, more than 30 days old, or no valid `generated_at`.
  Before, every case printed the same message.

## 0.1.0 - 2026-11-02

First release.

- `build_index.py` indexes every installed `SKILL.md` for Claude Code
  (`~/.claude/skills` and plugin skills) and Codex CLI (`~/.codex/skills`
  and `~/.agents/skills`), and merges in curated sources.
- `find.py` ranks skills, journeys, and routes against a request in plain
  words, and prints install commands for skills that are missing. Words that
  appear in many skills count for less than rare words.
- `find.py` exits with code `2` when the index is missing, unreadable,
  built on another machine, or more than 30 days old, and names the rebuild
  command.
- The Wondel.ai catalogue is the first curated source: 51 skills, 14
  journeys, and 8 routes.
- Add mode: ask your agent to add skills from a URL, file, or pasted list
  as a new curated source.
- The "Try this" prompt adds "Start with the smallest first step." only
  when you fix or improve something that exists.
