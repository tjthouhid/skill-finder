import contextlib
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill-finder" / "scripts"))
from common import load_sources
from build_index import build_index, detect_source, main, scan_root

FIX = ROOT / "tests" / "fixtures"
REAL_SOURCES = ROOT / "skill-finder" / "data" / "sources"
CLAUDE = FIX / "claude_skills"
PLUGINS = FIX / "plugins" / "cache" / "mkt" / "superpowers" / "7.0.0" / "skills"
CODEX = FIX / "codex_skills"


def fixture_roots():
    return {"claude": [CLAUDE, PLUGINS], "codex": [CODEX]}


def fixture_sources():
    return load_sources(REAL_SOURCES)[0] + load_sources(FIX / "sources")[0]


class BuildIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index, cls.stats = build_index(fixture_roots(), fixture_sources())
        cls.skills = cls.index["skills"]

    def test_scan_root_skips_hidden_missing_and_no_skillmd(self):
        found = scan_root(CLAUDE)
        self.assertNotIn("synced", found)
        self.assertIn("refactoring-ui", found)
        self.assertEqual(scan_root(FIX / "does-not-exist"), {})

    def test_symlinked_skill_dir(self):
        self.assertIn("linked-skill", scan_root(CLAUDE))

    def test_broken_frontmatter_skipped(self):
        self.assertNotIn("broken", self.skills)
        self.assertTrue(any("broken" in s for s in self.stats["skipped"]))

    def test_same_slug_two_roots(self):
        rec = self.skills["refactoring-ui"]
        self.assertEqual(rec["installed"], {"claude": True, "codex": True})
        self.assertIn("claude", rec["paths"])
        self.assertIn("codex", rec["paths"])

    def test_wondel_enrichment_and_install(self):
        rec = self.skills["refactoring-ui"]
        self.assertEqual(rec["category"], "Design & UX")
        self.assertEqual(rec["source"], "wondel")
        self.assertTrue(rec["use_when"].startswith("Use when the UI works"))
        self.assertEqual(rec["install"]["codex"],
                         "npx skills add wondelai/skills -s refactoring-ui -g -a codex")
        self.assertIn("extra", rec["sources_seen"])
        self.assertEqual(rec["sources_seen"][0], "wondel")
        self.assertEqual(rec["display_name"], "Refactoring UI")

    def test_earlier_source_wins(self):
        self.assertNotIn("EXTRA", self.skills["refactoring-ui"]["summary"])

    def test_curated_not_installed_is_indexed(self):
        self.assertIn("acme-pricing-wizard", self.skills)
        self.assertIn("mom-test", self.skills)
        rec = self.skills["top-design"]
        self.assertEqual(rec["installed"], {"claude": False, "codex": False})
        self.assertEqual(rec["paths"], {})
        self.assertIn("top-design", self.stats["curated_not_installed"])
        self.assertNotIn("mom-test", self.stats["curated_not_installed"])

    def test_plugin_source(self):
        rec = self.skills["brainstorming"]
        self.assertEqual(rec["source"], "superpowers")
        self.assertEqual(rec["install"]["claude"], "/plugin install superpowers@mkt")
        self.assertIsNone(rec["install"]["codex"])

    def test_gstack_source(self):
        rec = self.skills["ship"]
        self.assertEqual(rec["source"], "gstack")
        self.assertEqual(rec["install"], {"claude": None, "codex": None})

    def test_journeys_carry_installed_flag(self):
        journey = next(j for j in self.index["journeys"] if j["slug"] == "create-website")
        self.assertIs(journey["installed"]["claude"], True)

    def test_journey_records_carry_install(self):
        journey = next(j for j in self.index["journeys"] if j["slug"] == "create-website")
        self.assertEqual(journey["install"]["codex"],
                         "npx skills add wondelai/skills -s create-website -g -a codex")
        self.assertEqual(journey["install"]["claude"],
                         "npx skills add wondelai/skills -s create-website -g -a claude-code")
        for j in self.index["journeys"]:
            self.assertEqual(set(j["install"]), {"claude", "codex"})

    def test_categories_and_stats(self):
        self.assertIn("Design & UX", self.index["categories"])
        self.assertEqual(self.index["categories"], sorted(self.index["categories"]))
        self.assertEqual(self.stats["total"], len(self.skills))
        self.assertEqual(sum(self.stats["by_source"].values()), len(self.skills))
        self.assertEqual({s["source"] for s in self.index["sources"]} >= {"wondel", "extra"}, True)

    def test_record_fields_and_journey_membership(self):
        rec = self.skills["linked-skill"]
        self.assertEqual(rec["source"], "unknown")
        self.assertEqual(rec["display_name"], "Linked Skill")
        self.assertEqual(rec["summary"], "Pick a pricing tier.")
        self.assertIn("create-website", self.skills["storybrand-messaging"]["journeys"])
        self.assertEqual(self.skills["37signals-way"]["author"], "wondelai")

    def test_journey_skill_gets_source_and_install(self):
        rec = self.skills["create-website"]
        self.assertEqual(rec["source"], "wondel")
        self.assertEqual(rec["display_name"], "Create a Website")
        self.assertEqual(rec["install"]["claude"],
                         "npx skills add wondelai/skills -s create-website -g -a claude-code")
        self.assertNotIn("create-business", self.skills)  # uninstalled journey is not a skill record
        self.assertNotIn("create-business", self.stats["curated_not_installed"])

    def test_slug_match_records_source_seen(self):
        # extra.json lists acme-pricing-wizard by slug; the installed record gets it
        self.assertEqual(self.skills["acme-pricing-wizard"]["source"], "extra")
        self.assertEqual(self.skills["acme-pricing-wizard"]["sources_seen"], ["extra"])

    def test_detect_source_unknown_and_author(self):
        p = pathlib.Path("/x/skills/foo/SKILL.md")
        self.assertEqual(detect_source("foo", {}, p, {}), ("unknown", None, None))
        self.assertEqual(detect_source("foo", {"metadata": {"author": "Acme"}}, p, {}),
                         ("acme", "Acme", None))
        q = pathlib.Path("/h/.claude/plugins/cache/mk/plug/1.0/skills/foo/SKILL.md")
        self.assertEqual(detect_source("foo", {}, q, {}), ("plug", None, "plug@mk"))


def _src(name, skills, install=None):
    data = {"source": name, "label": name, "skills": skills}
    if install:
        data["install"] = install
    return data


def _skill(slug, summary="s", **extra):
    return dict(slug=slug, summary=summary, **extra)


class AliasPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)

    def install_dirs(self, *names):
        for name in names:
            d = self.root / name
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Dir {name}.\n---\n")

    def build(self, sources):
        index, stats = build_index({"claude": [self.root], "codex": []}, sources)
        return index["skills"], stats

    def test_alias_named_dir_uses_curated_slug_in_install(self):
        self.install_dirs("foo-old")
        skills, _ = self.build([_src("a", [_skill("foo", aliases=["foo-old"])],
                                     install="inst {slug} {agent}")])
        rec = skills["foo-old"]
        self.assertEqual(rec["install"], {"claude": "inst foo claude-code",
                                          "codex": "inst foo codex"})
        self.assertEqual(rec["source"], "a")
        self.assertEqual(rec["sources_seen"], ["a"])
        self.assertTrue(rec["installed"]["claude"])

    def test_alias_match_suppresses_duplicate_uninstalled_record(self):
        self.install_dirs("foo-old")
        skills, stats = self.build([_src("a", [_skill("foo", aliases=["foo-old"])])])
        self.assertNotIn("foo", skills)
        self.assertEqual(stats["curated_not_installed"], [])

    def test_slug_match_beats_alias_match(self):
        self.install_dirs("bar")
        skills, stats = self.build([
            _src("a", [_skill("bar", "BAR")], install="inst {slug}"),
            _src("b", [_skill("baz", "BAZ", aliases=["bar"])], install="other {slug}"),
        ])
        rec = skills["bar"]
        self.assertEqual(rec["summary"], "BAR")
        self.assertEqual(rec["sources_seen"], ["a"])
        self.assertEqual(rec["install"]["claude"], "inst bar")
        # baz was not claimed by the alias, so it is still reported as not installed
        self.assertEqual(stats["curated_not_installed"], ["baz"])
        self.assertEqual(skills["baz"]["installed"], {"claude": False, "codex": False})

    def test_alias_union_across_sources_and_earlier_summary_wins(self):
        self.install_dirs("foo")
        skills, _ = self.build([
            _src("a", [_skill("foo", "FIRST", aliases=["x"])]),
            _src("b", [_skill("foo", "SECOND", aliases=["y", "x"])]),
        ])
        rec = skills["foo"]
        self.assertEqual(rec["aliases"], ["x", "y"])
        self.assertEqual(rec["summary"], "FIRST")
        self.assertEqual(rec["sources_seen"], ["a", "b"])


class CliTests(unittest.TestCase):
    def test_cli_writes_file_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "sources").mkdir()
            for src in list(REAL_SOURCES.glob("*.json")) + list((FIX / "sources").glob("*.json")):
                shutil.copy(src, tmp / "sources" / src.name)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["--data", str(tmp), "--claude-root", str(CLAUDE),
                           "--claude-root", str(PLUGINS), "--codex-root", str(CODEX), "--quiet"])
            self.assertEqual(rc, 0)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("bad.json", err.getvalue())
            data = json.loads((tmp / "skills.json").read_text(encoding="utf-8"))
            self.assertIn("refactoring-ui", data["skills"])
            self.assertEqual(data["roots"]["codex"], [str(CODEX)])

    def test_cli_prints_summary_unless_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["--data", tmp, "--claude-root", str(CLAUDE), "--codex-root", str(CODEX)])
            self.assertEqual(rc, 0)
            self.assertIn("total", out.getvalue())


if __name__ == "__main__":
    unittest.main()
