import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill-finder" / "scripts"))
from common import load_sources
from build_index import build_index
from find import expand, main, render_markdown, search, tokenize

FIX = ROOT / "tests" / "fixtures"
REAL_SOURCES = ROOT / "skill-finder" / "data" / "sources"
INDEX = None


def setUpModule():
    global INDEX
    roots = {
        "claude": [
            FIX / "claude_skills",
            FIX / "plugins" / "cache" / "mkt" / "superpowers" / "7.0.0" / "skills",
        ],
        "codex": [FIX / "codex_skills"],
    }
    sources = load_sources(REAL_SOURCES)[0] + load_sources(FIX / "sources")[0]
    INDEX, _ = build_index(roots, sources)


def top_slugs(q, n=3):
    return [r["slug"] for _, r in search(INDEX, q)["skills"][:n]]


class FindTests(unittest.TestCase):
    def test_tokenize_stems_and_drops_stopwords(self):
        self.assertEqual(
            tokenize("Shoppers are leaving at the checkout pages"),
            ["shopper", "leav", "checkout", "page"],
        )

    def test_expand_multiword_synonym(self):
        q = "human type web design"
        self.assertIn("frontend", expand(tokenize(q), q))

    def test_human_web_design(self):
        got = set(top_slugs("human type web design, not generic"))
        self.assertTrue(got & {"refactoring-ui", "design-taste-frontend"}, got)

    def test_checkout(self):
        self.assertIn("cro-methodology", top_slugs("shoppers leave at checkout"))

    def test_legacy(self):
        self.assertIn(
            "working-with-legacy-code", top_slugs("old untested code I'm scared to change")
        )

    def test_release_it(self):
        self.assertIn(
            "release-it", top_slugs("app depends on third party APIs, before launch")
        )

    def test_positioning(self):
        got = set(top_slugs("customers don't understand what we do"))
        self.assertTrue(got & {"obviously-awesome", "storybrand-messaging"}, got)

    def test_journey_landing_page(self):
        res = search(INDEX, "build a landing page from scratch")
        self.assertEqual(res["journeys"][0][1]["slug"], "create-website")

    def test_uninstalled_curated_skill_findable(self):
        self.assertIn(
            "top-design", top_slugs("distinctive memorable launch page art direction", 5)
        )

    def test_render_install_line_only_when_missing(self):
        out = render_markdown(search(INDEX, "shoppers leave at checkout"), "codex", INDEX)
        self.assertIn("-a codex", out)
        self.assertIn("codex ✗", out)
        res = search(INDEX, "refactoring ui looks uneven cluttered")
        self.assertEqual(res["skills"][0][1]["slug"], "refactoring-ui")
        out = render_markdown(
            {"skills": res["skills"][:1], "journeys": [], "routes": []}, "claude", INDEX
        )
        self.assertIn("claude ✓", out)
        self.assertNotIn("Install (claude)", out)

    def test_non_ascii_query_no_crash(self):
        res = search(INDEX, "ওয়েবসাইট ডিজাইন 🎨")
        self.assertIsInstance(res, dict)
        out = render_markdown(res, "claude", INDEX)
        self.assertTrue("No match" in out or "## Skills" in out)

    def test_missing_index_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(["x", "--index", str(pathlib.Path(d) / "nope.json")])
        self.assertEqual(rc, 2)
        self.assertIn("build_index.py", err.getvalue())

    def test_empty_query_exit_1(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["   "]), 1)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "skills.json"
            p.write_text(json.dumps(INDEX), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["checkout", "--json", "--index", str(p)])
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertIn(data["skills"][0]["slug"], INDEX["skills"])
        self.assertEqual(data["tool"], "claude")


if __name__ == "__main__":
    unittest.main()
