# Skill Finder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `skill-finder` agent skill that, from a plain-language need, names the best installed skills, the fitting journey, install lines for anything missing in the current tool, and a ready prompt.

**Architecture:** A generated index (`skills.json`) merges every installed `SKILL.md` on the machine with curated source files (`data/sources/*.json`, Wondel first). A stdlib keyword ranker (`find.py`) prints the top candidates; `SKILL.md` tells the agent how to run it and shape the answer. Shared parsing/loading lives in `common.py`.

**Tech Stack:** Python 3.9+ stdlib only, run with `python3 -I`; `unittest`; Markdown SKILL.md consumed by Claude Code and Codex CLI.

**Spec:** `docs/superpowers/specs/2026-11-02-skill-finder-design.md`

## Global Constraints

- Python 3.9+, standard library only; every script invocation in docs and SKILL.md uses `python3 -I`.
- Scripts take paths as arguments or defaults under `~`; never `chdir` into a skills folder.
- Exit codes: `1` usage error, `2` missing/invalid index; errors are one line on stderr.
- Slugs are installed directory names (e.g. `storybrand-messaging`), never guide names.
- Install template placeholders: `{slug}`, `{agent}`; agent values are exactly `claude-code` and `codex`.
- Tool names are exactly `claude` and `codex`.
- Commit after each task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; author `tjthouhid <tjthouhid@gmail.com>` (pass via `-c user.name -c user.email`).

## Review Focus

1. A query in Bengali or with emoji/punctuation only → `find.py` must not crash; prints "no match" and the category list (Task 5 test `test_non_ascii_query_no_crash`).
2. The same slug in two roots (Claude and Codex) → one record, `installed` true for both, both paths kept (Task 4 `test_same_slug_two_roots`).
3. A skills folder entry that is a symlink to a directory (how `npx skills add` installs) → followed and indexed (Task 4 `test_symlinked_skill_dir`).
4. A SKILL.md whose frontmatter is broken (no closing `---`) → skipped, counted, index still written (Task 4 `test_broken_frontmatter_skipped`).
5. `find.py` run before `build_index.py` on a fresh clone → exit 2 with a one-line hint naming the build command (Task 5 `test_missing_index_exit_2`).

---

### Task 1: Frontmatter parser

**Files:**
- Create: `skill-finder/scripts/common.py`
- Create: `tests/__init__.py` (empty), `tests/test_common.py`

**Interfaces:**
- Produces: `parse_frontmatter(text: str) -> tuple[dict, str]` — `(meta, body)`. `meta` is `{}` and `body` is the full text when there is no leading `---` block. Supports: `key: value` (value may contain `:`), single- or double-quoted scalars spanning lines (YAML `''` doubling inside single quotes), `>` and `|` block scalars, one level of nested mapping (`metadata:` followed by indented `author:`/`version:`), `#` comments at line start. Unknown constructs keep the raw string.
- Produces: `first_sentence(text: str) -> str` — up to the first `.`/`!`/`?` followed by space or end, max 200 chars.

- [ ] **Step 1: Write failing tests** in `tests/test_common.py`:

```python
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skill-finder" / "scripts"))
from common import parse_frontmatter, first_sentence

class ParseFrontmatter(unittest.TestCase):
    def test_single_quoted_multiline_with_colons_and_doubled_quotes(self):
        text = "---\nname: create-website\ndescription: 'Guided journey: blank page. Says ''build me a page''.\n  Second line.'\nlicense: MIT\nmetadata:\n  author: wondelai\n  version: \"1.0.2\"\n---\n# Body\n"
        meta, body = parse_frontmatter(text)
        self.assertEqual(meta["name"], "create-website")
        self.assertEqual(meta["description"], "Guided journey: blank page. Says 'build me a page'. Second line.")
        self.assertEqual(meta["metadata"]["author"], "wondelai")
        self.assertEqual(meta["metadata"]["version"], "1.0.2")
        self.assertEqual(body.strip(), "# Body")

    def test_double_quoted_with_gstack_suffix(self):
        meta, _ = parse_frontmatter('---\nname: ship\npreamble-tier: 4\ndescription: "Ship workflow: merge, test. (gstack)"\nallowed-tools:\n  - Bash\n---\n')
        self.assertEqual(meta["description"], "Ship workflow: merge, test. (gstack)")
        self.assertEqual(meta["preamble-tier"], "4")

    def test_folded_block_scalar(self):
        meta, _ = parse_frontmatter("---\nname: x\ndescription: >\n  First line\n  second line.\n---\n")
        self.assertEqual(meta["description"], "First line second line.")

    def test_no_frontmatter(self):
        meta, body = parse_frontmatter("# Just a doc\n")
        self.assertEqual(meta, {}); self.assertEqual(body, "# Just a doc\n")

    def test_unclosed_frontmatter_raises(self):
        with self.assertRaises(ValueError):
            parse_frontmatter("---\nname: x\nno end")

class FirstSentence(unittest.TestCase):
    def test_cuts_at_sentence_end(self):
        self.assertEqual(first_sentence("Do a thing. Then another."), "Do a thing.")
    def test_version_number_not_a_boundary(self):
        self.assertEqual(first_sentence("Uses v1.5 tokens. More."), "Uses v1.5 tokens.")
```

- [ ] **Step 2: Run** `python3 -I -m unittest tests.test_common -v` — Expected: FAIL, `ModuleNotFoundError: common`.
- [ ] **Step 3: Implement** `parse_frontmatter` and `first_sentence` in `common.py`. Line-based state machine; `ValueError("unclosed frontmatter")` when the closing `---` is missing.
- [ ] **Step 4: Run** the same command — Expected: all PASS.
- [ ] **Step 5: Commit** `feat: frontmatter parser`.

---

### Task 2: Source files — schema, loader, validation

**Files:**
- Modify: `skill-finder/scripts/common.py`
- Create: `skill-finder/data/sources/_schema.md`
- Create: `tests/fixtures/sources/extra.json`, `tests/fixtures/sources/bad.json`, `tests/test_sources.py`

**Interfaces:**
- Produces: `validate_source(data: dict) -> list[str]` — error strings; empty = valid. Required: `source` (str, `^[a-z0-9-]+$`), `label` (str), `skills` (list, each with `slug` matching `^[a-z0-9][a-z0-9-]*$` and `summary` str). Optional per spec: `homepage`, `install`, `install_all`, `categories`, `journeys[]` (`slug`,`name`,`skills[]` required), `routes[]` (`name`,`steps[[slug,text],…]` required), per skill `name`,`guide_slug`,`category`,`use_when`,`aliases[]`.
- Produces: `load_sources(sources_dir: Path) -> tuple[list[dict], list[str]]` — valid sources in filename order, skipping `_*.md`; warnings `"<file>: <error>"` for invalid JSON or schema errors.
- Produces: `expand_install(template: str | None, slug: str, agent: str) -> str | None`.

- [ ] **Step 1: Write `_schema.md`** documenting the fields above with one full example (copy the spec's JSON example) and the merge rule: *earlier filename wins per field; both source names recorded*.
- [ ] **Step 2: Write fixtures.** `extra.json`: `source: "extra"`, `label: "Extra test source"`, `install: "npx skills add acme/skills -s {slug} -g -a {agent}"`, skills: `refactoring-ui` (summary "EXTRA summary should lose to wondel", use_when "EXTRA") and `acme-pricing-wizard` (summary "Pick a price tier", use_when "Use when choosing between pricing tiers", aliases `["pricing tiers"]`). `bad.json`: `{"label": "no source key", "skills": "not a list"}`.
- [ ] **Step 3: Write failing tests** in `tests/test_sources.py`: `test_valid_source_passes` (extra.json → `[]`), `test_bad_source_errors` (≥2 errors mentioning `source` and `skills`), `test_load_sources_skips_bad_with_warning` (returns 1 source, 1 warning containing `bad.json`), `test_expand_install` (`expand_install("npx x -s {slug} -a {agent}", "a-b", "codex") == "npx x -s a-b -a codex"`; `expand_install(None, "a", "codex") is None`).
- [ ] **Step 4: Run** `python3 -I -m unittest tests.test_sources -v` — Expected: FAIL (ImportError).
- [ ] **Step 5: Implement** the three functions in `common.py`.
- [ ] **Step 6: Run** — Expected: PASS. Run `tests.test_common` too — still PASS.
- [ ] **Step 7: Commit** `feat: source schema and loader`.

---

### Task 3: Curate `wondel.json` from the field guide

**Files:**
- Create: `skill-finder/data/sources/wondel.json`
- Create: `tests/test_wondel_data.py`

**Interfaces:**
- Consumes: `validate_source` (Task 2).
- Produces: the first source file; its `skills[].slug` values are the installed directory names used by every later test.

Input: `/Users/tjthouhid/Documents/Codex/2026-11-02/https-skills-wondel-ai-skills-architecture/outputs/wondel-skills-field-guide.html`. The one `<script>` holds `const categories=[...]` (8 categories × `[name, guide_slug, summary, use_when]`), `const journeys=[...]` (`[slug, name, tagline, "N phases"]`), `const journeySteps=...`, and the eight example routes are in the page body under "Example project routes". Extract with a throwaway Python snippet run with `-I` (do not commit it).

Guide slug → installed slug (everything else is identical):

| guide_slug | slug |
|---|---|
| storybrand | storybrand-messaging |
| the-mom-test | mom-test |
| refactoring | refactoring-patterns |
| software-design | software-design-philosophy |
| legacy-code | working-with-legacy-code |
| design-of-everyday-things | design-everyday-things |
| 100m-offers | hundred-million-offers |
| 1-page-marketing-plan | one-page-marketing |
| inspired | inspired-product |

Top-level values: `source: "wondel"`, `label: "Wondel.ai skills"`, `homepage: "https://skills.wondel.ai/skills"`, `install: "npx skills add wondelai/skills -s {slug} -g -a {agent}"`, `install_all: "npx skills add wondelai/skills --all --global"`. Each skill: `name`, `guide_slug`, `slug`, `category`, `summary`, `use_when`, `aliases` (guide_slug when it differs, plus the display name lower-cased). Journey `skills`: parse the installed journey's description at `~/.claude/skills/<journey>/SKILL.md` — the comma list after "Orchestrates N skills phase by phase -" — mapped through the table; fall back to the guide's `journeySteps` if a journey's description lacks the list. Journey `fits`: the matching project-card sentence from the guide (e.g. create-website → "new marketing site or landing page from scratch"). Routes: the eight from the guide, `steps` as `[slug, text]`, `shortcut` journey slug, `note` the trailing sentence.

- [ ] **Step 1: Write failing tests** in `tests/test_wondel_data.py`: loads the file; `test_valid` (`validate_source == []`), `test_counts` (50 skills, 14 journeys, 8 routes, 8 categories), `test_slugs_unique_and_mapped` (slugs unique; `"storybrand-messaging"` present, `"storybrand"` absent as slug but present as a `guide_slug`), `test_every_skill_has_category_in_list`, `test_journey_skills_resolve` (every journey has ≥3 skills, all in the 50), `test_route_steps_resolve` (every route step slug is in the 50; every `shortcut` is a journey slug), `test_create_website_members` (contains `one-page-marketing`, `storybrand-messaging`, `refactoring-ui`, `cro-methodology`).
- [ ] **Step 2: Run** — Expected: FAIL (file missing).
- [ ] **Step 3: Extract and write `wondel.json`** per the rules above; pretty-printed, 2-space indent, `ensure_ascii=False`.
- [ ] **Step 4: Run** — Expected: PASS. Fix data (not tests) on failure.
- [ ] **Step 5: Commit** `data: Wondel field guide source (50 skills, 14 journeys, 8 routes)`.

---

### Task 4: `build_index.py`

**Files:**
- Create: `skill-finder/scripts/build_index.py`
- Modify: `skill-finder/scripts/common.py` (add `default_roots`)
- Create: `tests/fixtures/claude_skills/<slug>/SKILL.md` for: `refactoring-ui`, `design-taste-frontend`, `cro-methodology`, `working-with-legacy-code`, `release-it`, `obviously-awesome`, `storybrand-messaging`, `create-website`, `ux-heuristics`, `mom-test`, `37signals-way`, `ship` — each file = the real installed file's `---` frontmatter block only (copy `name`, `description`, and `metadata` if present) + one body line. Plus `broken/SKILL.md` (frontmatter without closing `---`), `synced/` (empty dir), and `linked-skill` as a **symlink** to `../codex_skills/acme-pricing-wizard` (create with `ln -s`).
- Create: `tests/fixtures/codex_skills/refactoring-ui/SKILL.md` (copy), `tests/fixtures/codex_skills/acme-pricing-wizard/SKILL.md` (name `acme-pricing-wizard`, description "Pick a pricing tier. Use when choosing between tiers.").
- Create: `tests/fixtures/plugin_cache/mkt/superpowers/7.0.0/skills/brainstorming/SKILL.md` (copy of the real one's frontmatter).
- Create: `tests/test_build_index.py`

**Interfaces:**
- Consumes: `parse_frontmatter`, `first_sentence`, `load_sources`, `expand_install`.
- Produces in `common.py`: `default_roots() -> dict[str, list[Path]]` = `{"claude": [~/.claude/skills] + sorted(glob ~/.claude/plugins/cache/*/*/*/skills), "codex": [~/.codex/skills]}` (existing or not).
- Produces in `build_index.py`:
  - `scan_root(root: Path) -> dict[str, Path]` — `{slug: SKILL.md path}` for each immediate child dir (symlinks followed) containing `SKILL.md`; hidden dirs skipped; missing root → `{}`.
  - `detect_source(slug: str, meta: dict, path: Path, source_index: dict[str, dict]) -> tuple[str, str | None, str | None]` → `(source, author, plugin_ref)`; `plugin_ref` is `"<plugin>@<marketplace>"` when `path` has `/plugins/cache/<marketplace>/<plugin>/` in it. Order: curated source match → plugin → `metadata.author` lower-cased → `"gstack"` if description ends with `(gstack)` → `"unknown"`.
  - `build_index(roots: dict[str, list[Path]], sources: list[dict]) -> tuple[dict, dict]` → `(index, stats)`; `stats = {"total": n, "by_source": {...}, "skipped": [str], "curated_not_installed": [slug]}`. Index shape exactly per spec §`skills.json`; per-skill `install` is a dict `{"claude": str|None, "codex": str|None}` (template expanded with `claude-code`/`codex`; plugin → `{"claude": "/plugin install <ref>", "codex": None}`). `journeys` copied from sources with `installed` added; `routes` copied; `sources` = list of `{source, label, homepage}`.
  - CLI `main(argv) -> int`: `--data DIR` (default: `<script>/../data`), `--claude-root PATH` (repeatable; any given replaces defaults), `--codex-root PATH` (same), `--quiet`. Writes `<data>/skills.json` (2-space indent, sorted keys, `ensure_ascii=False`), prints stats summary unless quiet, prints each source warning to stderr. Returns 0.

- [ ] **Step 1: Create fixtures** as listed (copy frontmatter with a short shell loop; verify `ls -la tests/fixtures/claude_skills` shows the symlink).
- [ ] **Step 2: Write failing tests** in `tests/test_build_index.py` using `roots = {"claude": [FIX/claude_skills, FIX/plugin_cache/mkt/superpowers/7.0.0/skills], "codex": [FIX/codex_skills]}` and `sources = load_sources(REAL data/sources)[0] + load_sources(FIX/sources)[0]`:
  - `test_scan_root_skips_hidden_missing_and_no_skillmd` — `synced` absent; nonexistent root → `{}`.
  - `test_symlinked_skill_dir` — `"linked-skill"` in `scan_root(claude_skills)`.
  - `test_broken_frontmatter_skipped` — `"broken"` not in index; appears in `stats["skipped"]`.
  - `test_same_slug_two_roots` — `refactoring-ui`: `installed == {"claude": True, "codex": True}`, both `paths` keys present.
  - `test_wondel_enrichment_and_install` — `refactoring-ui`: `category == "Design & UX"`, `source == "wondel"`, `use_when` starts with "Use when the UI works", `install["codex"] == "npx skills add wondelai/skills -s refactoring-ui -g -a codex"`, `"extra"` in `sources_seen`.
  - `test_earlier_source_wins` — `refactoring-ui` summary does not contain "EXTRA".
  - `test_curated_not_installed_is_indexed` — `acme-pricing-wizard` present (from codex root) and `mom-test` present; `top-design` present with `installed == {"claude": False, "codex": False}` and in `stats["curated_not_installed"]`.
  - `test_plugin_source` — `brainstorming`: `source == "superpowers"`, `install["claude"] == "/plugin install superpowers@mkt"`, `install["codex"] is None`.
  - `test_gstack_source` — `ship`: `source == "gstack"`, `install == {"claude": None, "codex": None}`.
  - `test_journeys_carry_installed_flag` — journey `create-website` has `installed["claude"] is True`.
  - `test_cli_writes_file_and_warns` — run `main(["--data", tmpdir, "--claude-root", …, "--codex-root", …, "--quiet"])` after copying `sources/` (real + fixtures) into `tmpdir/sources`; returns 0; `tmpdir/skills.json` exists; stderr contains `bad.json`.
- [ ] **Step 3: Run** `python3 -I -m unittest tests.test_build_index -v` — Expected: FAIL (ImportError).
- [ ] **Step 4: Implement** `default_roots` and `build_index.py` per Interfaces.
- [ ] **Step 5: Run** — Expected: PASS; full suite `python3 -I -m unittest discover -s tests -v` PASS.
- [ ] **Step 6: Generate the real index:** `python3 -I skill-finder/scripts/build_index.py` — Expected: stats print, total ≈ 160, `by_source.wondel == 50`, `curated_not_installed == []`.
- [ ] **Step 7: Commit** `feat: build_index scans installed skills and merges sources` (include `data/skills.json`).

---

### Task 5: `find.py`

**Files:**
- Create: `skill-finder/scripts/find.py`
- Create: `tests/test_find.py`

**Interfaces:**
- Consumes: index dict from Task 4.
- Produces:
  - `STOPWORDS: set[str]`, `SYNONYMS: dict[str, list[str]]` — at minimum: `web design`→`ui frontend landing visual interface`; `human`→`taste handcrafted anti-slop distinctive intentional`; `generic`→`templated slop`; `checkout`→`conversion funnel cart`; `abandon`→`drop-off leave`; `slow`→`performance speed latency`; `legacy`→`untested old seams`; `scared`→`risky safe`; `customers`→`prospects buyers users`; `understand`→`clarity positioning message`; `launch`→`release production`; `api`→`external service network`; `landing page`→`website homepage`; `retention`→`return habit churn`; `price`→`pricing willingness pay`.
  - `tokenize(text: str) -> list[str]` — lowercase, split on non-alphanumerics (Unicode-aware, keep non-Latin words), drop stopwords and 1-char tokens, light stem (strip trailing `ing`, `ed`, `es`, `s` when the stem is ≥4 chars).
  - `expand(tokens: list[str], raw: str) -> list[str]` — tokens plus synonym tokens for any key found in `raw.lower()` (multi-word keys matched as substrings).
  - `score_text(terms: list[str], text: str, weight: float) -> float` = `weight * hits / (1 + log(1 + len(tokens)))` where `hits` = number of distinct terms present in `tokenize(text)`.
  - `score_skill(terms, bigrams, rec) -> float` — weights: `name` 4, `display_name` 4, `aliases` 4, `use_when` 3, `category` 2, `summary` 2, `description` 1; `+2` per query bigram (adjacent original tokens) found verbatim in any field.
  - `score_journey(terms, bigrams, j) -> float` — over `name` 4, `tagline` 3, `fits` 3, member skill slugs 1.
  - `search(index: dict, query: str, top: int = 8) -> dict` → `{"skills": [(score, rec)…], "journeys": [(score, j)…], "routes": [route…]}`; routes = those containing any of the top-3 skill slugs; results with score < 1.0 dropped.
  - `render_markdown(results: dict, tool: str, index: dict) -> str` — exactly the spec's layout; the install line shown only when `rec["installed"][tool]` is False and `rec["install"][tool]` is not None; when no skills and no journeys: `No match. Categories: …` listing `index` categories.
  - `load_index(path: Path) -> dict` — `FileNotFoundError` → caller exits 2 with `skills.json not found at <path>. Run: python3 -I <scripts>/build_index.py`.
  - CLI `main(argv) -> int`: positional `query` (joined), `--tool {claude,codex}` default `claude`, `--top N` default 8, `--json`, `--index PATH` default `<script>/../data/skills.json`. Empty/whitespace query → usage, exit 1.

- [ ] **Step 1: Write failing tests** in `tests/test_find.py`. Build `INDEX` once in `setUpModule` via `build_index(fixture roots, real + fixture sources)` from Task 4. Helper `top_slugs(q, n=3)`.
  - `test_tokenize_stems_and_drops_stopwords` — `tokenize("Shoppers are leaving at the checkout pages") == ["shopper", "leav", "checkout", "page"]`.
  - `test_expand_multiword_synonym` — `"frontend" in expand(tokenize("human type web design"), "human type web design")`.
  - `test_human_web_design` — `top_slugs("human type web design, not generic")` intersects `{"refactoring-ui", "design-taste-frontend"}`.
  - `test_checkout` — `"cro-methodology" in top_slugs("shoppers leave at checkout")`.
  - `test_legacy` — `"working-with-legacy-code" in top_slugs("old untested code I'm scared to change")`.
  - `test_release_it` — `"release-it" in top_slugs("app depends on third party APIs, before launch")`.
  - `test_positioning` — `top_slugs("customers don't understand what we do")` intersects `{"obviously-awesome", "storybrand-messaging"}`.
  - `test_journey_landing_page` — first journey for `"build a landing page from scratch"` is `create-website`.
  - `test_uninstalled_curated_skill_findable` — `"top-design" in top_slugs("distinctive memorable launch page art direction", 5)`.
  - `test_render_install_line_only_when_missing` — for `tool="codex"`, output for the checkout query contains `-a codex` and `codex ✗`; for `tool="claude"` with `refactoring-ui` query it contains `claude ✓` and no `Install (claude)` line for that skill.
  - `test_non_ascii_query_no_crash` — `search(INDEX, "ওয়েবসাইট ডিজাইন 🎨")` returns a dict; `render_markdown` of it contains `No match` or a skill list (no exception).
  - `test_missing_index_exit_2` — `main(["x", "--index", tmp/"nope.json"])` returns 2; stderr mentions `build_index.py`.
  - `test_empty_query_exit_1` — `main(["   "])` returns 1.
  - `test_json_output` — `main(["checkout", "--json", "--index", written fixture index])` prints JSON whose `skills[0]["slug"]` exists.
- [ ] **Step 2: Run** `python3 -I -m unittest tests.test_find -v` — Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `find.py` per Interfaces.
- [ ] **Step 4: Run** — Expected: PASS. If a ranking test fails, adjust `SYNONYMS`/weights, not the test, unless the expectation is unreasonable (then say so in the commit).
- [ ] **Step 5: Live check against the real index:** run the six spec queries with `python3 -I skill-finder/scripts/find.py "<q>"`; paste the top-3 slugs for each into the commit message body.
- [ ] **Step 6: Commit** `feat: find.py keyword ranker with markdown/json output`.

---

### Task 6: `SKILL.md`, README, local install, live run

**Files:**
- Create: `skill-finder/SKILL.md`
- Create: `README.md`, `.gitignore` (`__pycache__/`, `.DS_Store`)
- Create symlinks: `~/.claude/skills/skill-finder` and `~/.codex/skills/skill-finder` → `<repo>/skill-finder`

**Interfaces:**
- Consumes: both CLIs exactly as defined in Tasks 4–5.

- [ ] **Step 1: Write `SKILL.md`.** Frontmatter: `name: skill-finder`; `description` (single-quoted, one paragraph): what it does + triggers `"which skill should I use"`, `"what skill for"`, `"is there a skill for"`, `"find me a skill"`, `"recommend a skill"`, `"/skill-finder"`, `"add these skills to skill finder"`, `"index a new skills guide"`; `license: MIT`; `metadata: {author: tjthouhid, version: "0.1.0"}`. Body sections, in this order, each ≤ 12 lines: **Where the scripts are** (`$SKILL_DIR/scripts`, resolve relative to this file), **Find mode** (spec steps 1–6 verbatim, including the 30-day staleness rule read from `generated_at`, the `--tool codex` rule, and the reply template with the five bold labels and the `Use <slug> [and <slug>] to <goal>. Start with the smallest first step.` prompt), **Add mode** (spec's five numbered steps; point at `data/sources/_schema.md`), **Refresh** (`python3 -I scripts/build_index.py`), **Rules** (never invent install commands or skills not in the index; prefer installed over uninstalled when scores tie; drop near-duplicates).
- [ ] **Step 2: Write `README.md`**: one-paragraph purpose; install block `npx skills add tjthouhid/skill-finder -g -a claude-code` and `… -a codex`; first-run note (`build_index.py` regenerates for the machine); example request/response; "Adding a source" pointing at `_schema.md`; dev: `python3 -I -m unittest discover -s tests`.
- [ ] **Step 3: Install locally:** `ln -s "$PWD/skill-finder" ~/.claude/skills/skill-finder` and `mkdir -p ~/.codex/skills && ln -s "$PWD/skill-finder" ~/.codex/skills/skill-finder`. Then rebuild the index (`skill-finder` itself now appears; `installed` true for both).
- [ ] **Step 4: Verify** `ls -la ~/.claude/skills/skill-finder ~/.codex/skills/skill-finder` shows both links; `python3 -I skill-finder/scripts/find.py "which skill finds skills"` lists `skill-finder` with `claude ✓ codex ✓`.
- [ ] **Step 5: Live run in this Claude Code session:** invoke `/skill-finder human type web design for my portfolio` and confirm the reply follows the five-label template and shows no install line for installed skills. Record the outcome in the commit body.
- [ ] **Step 6: Full suite** `python3 -I -m unittest discover -s tests -v` — Expected: PASS.
- [ ] **Step 7: Commit** `feat: skill-finder SKILL.md, README, local install`.
