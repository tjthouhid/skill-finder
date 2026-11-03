import contextlib
import copy
import datetime
import io
import json
import pathlib
import shlex
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skill-finder" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from common import load_sources
from build_index import build_index
from find import (_bigrams, _clean_use_when, close_call, damp_common, expand, main,
                  render_markdown, score_journey, score_skill, search, tokenize)

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

    def test_common_word_alone_does_not_win(self):
        # "design" names many skills; system-design matches nothing else in this query
        self.assertNotIn("system-design", top_slugs("human type web design for my portfolio"))

    def test_system_design_queries_still_find_it(self):
        self.assertEqual(top_slugs("system design for a chat app")[0], "system-design")
        self.assertIn("system-design", top_slugs("design a url shortener"))

    def test_damp_common_lowers_frequent_terms_only(self):
        records = [{"summary": "design thing %d" % i} for i in range(40)]
        records[0]["summary"] += " portfolio"
        terms = damp_common({"design": 1.0, "portfolio": 1.0, "ui": 0.5}, records)
        self.assertLess(terms["design"], 0.5)
        self.assertEqual(terms["portfolio"], 1.0)
        self.assertEqual(terms["ui"], 0.5)

    def test_damp_common_leaves_small_indexes_alone(self):
        records = [{"summary": "design"} for _ in range(5)]
        self.assertEqual(damp_common({"design": 1.0}, records), {"design": 1.0})

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

    def test_launch_page_not_ai_generated(self):
        got = set(top_slugs("launch page that doesn't look AI-generated"))
        self.assertTrue(got & {"design-taste-frontend", "top-design"}, got)

    def test_checkout_page_loses_customers(self):
        self.assertIn("cro-methodology", top_slugs("my checkout page loses customers"))

    def test_synonym_terms_weigh_half(self):
        q = "launch"
        rec = {"summary": "release"}
        user = score_skill(expand(tokenize(q), q), [], {"summary": "launch"})
        syn = score_skill(expand(tokenize(q), q), [], rec)
        self.assertAlmostEqual(syn, user * 0.5)

    def test_leave_abandon_symmetric(self):
        for q in ("users leave", "users abandon"):
            terms = expand(tokenize(q), q)
            self.assertTrue({"leave", "abandon", "drop"} <= set(terms), (q, terms))

    def test_generated_synonyms(self):
        for q in ("AI-generated copy", "looks generated"):
            self.assertIn("slop", expand(tokenize(q), q))

    def test_landing_not_stemmed(self):
        self.assertEqual(tokenize("landing pages"), ["landing", "page"])

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

    def test_render_invoke_name_only_when_namespaced(self):
        res = search(INDEX, "brainstorming")
        one = {"skills": res["skills"][:1], "journeys": [], "routes": []}
        self.assertEqual(res["skills"][0][1]["slug"], "brainstorming")
        lines = render_markdown(one, "claude", INDEX).splitlines()
        self.assertTrue(lines[1].startswith("1. brainstorming "), lines)
        self.assertEqual(lines[2], "   Invoke (claude): superpowers:brainstorming")
        self.assertNotIn("Invoke", render_markdown(one, "codex", INDEX))
        out = render_markdown(search(INDEX, "refactoring ui looks uneven cluttered"), "claude", INDEX)
        self.assertNotIn("Invoke (claude): refactoring-ui", out)

    def test_bigram_bonus_on_token_boundaries(self):
        rec = {"summary": "refactor old code safely"}
        terms = ["zzzz"]
        self.assertEqual(score_skill(terms, ["old code"], rec), 2)
        across = {"summary": "scan barcode older items"}
        self.assertEqual(score_skill(terms, ["code old"], across), 0)
        self.assertEqual(_bigrams(["code", "old"]), ["code old"])

    def test_no_journey_or_route_caps(self):
        res = search(INDEX, "design website landing page", top=50)
        q = "design website landing page"
        tokens = tokenize(q)
        eligible = [
            j for j in INDEX["journeys"]
            if score_journey(expand(tokens, q), _bigrams(tokens), j) >= 1.0
        ]
        self.assertEqual(len(res["journeys"]), len(eligible))
        self.assertEqual(len(search(INDEX, q, top=2)["journeys"]), min(2, len(eligible)))
        top3 = {r["slug"] for _, r in res["skills"][:3]}
        want = [r for r in INDEX["routes"] if top3 & {s[0] for s in r["steps"]}]
        self.assertEqual(len(res["routes"]), len(want))
        counts = [len(top3 & {s[0] for s in r["steps"]}) for r in res["routes"]]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_non_ascii_query_no_crash(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "skills.json"
            p.write_text(json.dumps(_local_index()), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["ওয়েবসাইট ডিজাইন 🎨", "--index", str(p)])
        self.assertEqual(rc, 0, err.getvalue())
        prefix = "No match. Categories: "
        self.assertTrue(out.getvalue().startswith(prefix), out.getvalue())
        listed = out.getvalue()[len(prefix):].strip().split(", ")
        self.assertTrue(listed[0] and set(listed) <= set(INDEX["categories"]), listed)

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


def _run(index_obj, *extra):
    """Write index_obj to a temp file, run main(), return (rc, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "skills.json"
        p.write_text(json.dumps(index_obj), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["checkout", "--index", str(p)] + list(extra))
    return rc, out.getvalue(), err.getvalue()


def _local_index(days_old=0):
    idx = copy.deepcopy(INDEX)
    idx["roots"] = {"claude": [str(pathlib.Path.home() / ".claude" / "skills")], "codex": []}
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_old)
    idx["generated_at"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    return idx


class IndexFreshnessTests(unittest.TestCase):
    def test_foreign_home_exit_2_with_hint(self):
        idx = _local_index()
        idx["roots"]["claude"] = ["/nowhere/else/.claude/skills"]
        rc, out, err = _run(idx)
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("another machine or is stale", err)
        self.assertIn("build_index.py", err)

    def test_codex_only_roots_are_local(self):
        idx = _local_index()
        idx["roots"] = {"claude": [], "codex": [str(pathlib.Path.home() / ".codex" / "skills")]}
        self.assertEqual(_run(idx)[0], 0)

    def test_no_recorded_roots_is_local(self):
        idx = _local_index()
        idx["roots"] = {"claude": [], "codex": []}
        self.assertEqual(_run(idx)[0], 0)

    def test_sibling_home_is_foreign(self):
        idx = _local_index()
        idx["roots"] = {"claude": [str(pathlib.Path.home()) + "2/.claude/skills"], "codex": []}
        self.assertEqual(_run(idx)[0], 2)

    def test_stale_index_exit_2(self):
        rc, _, err = _run(_local_index(days_old=31))
        self.assertEqual(rc, 2)
        self.assertIn("build_index.py", err)

    def test_fresh_local_index_ok(self):
        rc, out, err = _run(_local_index(days_old=1))
        self.assertEqual(rc, 0, err)
        self.assertIn("## Skills", out)

    def test_bad_generated_at_is_stale(self):
        idx = _local_index()
        idx["generated_at"] = "yesterday"
        self.assertEqual(_run(idx)[0], 2)

    def test_non_dict_index_exit_2(self):
        rc, _, err = _run([1, 2, 3])
        self.assertEqual(rc, 2)
        self.assertIn("build_index.py", err)

    def test_missing_skills_dict_exit_2(self):
        idx = _local_index()
        idx["skills"] = []
        self.assertEqual(_run(idx)[0], 2)

    def test_hint_path_is_shell_quoted(self):
        # the repo path contains a space; the printed command must quote it
        _, _, err = _run([])
        cmd = err.split("Run:")[1].strip()
        self.assertTrue(cmd.startswith("python3 -I "))
        self.assertEqual(shlex.split(cmd)[2], str(SCRIPTS / "build_index.py"))


class UseWhenTests(unittest.TestCase):
    def test_clean_use_when(self):
        self.assertEqual(_clean_use_when("Use when the UI works"), "the UI works")
        self.assertEqual(_clean_use_when("Use for launch pages or brand moments"),
                         "launch pages or brand moments")
        self.assertEqual(_clean_use_when("use before shipping: check"), "shipping: check")
        self.assertEqual(_clean_use_when("Use whenever X"), "X")
        self.assertEqual(_clean_use_when("Use as a gate"), "a gate")
        self.assertEqual(_clean_use_when("Use in a hurry"), "a hurry")
        self.assertEqual(_clean_use_when("Launch pages"), "Launch pages")
        self.assertEqual(_clean_use_when(None), "")

    def test_render_no_doubled_label(self):
        out = render_markdown(search(INDEX, "distinctive memorable launch page art direction"),
                              "claude", INDEX)
        self.assertNotIn("Use when: Use", out)
        self.assertIn("Use when: launch pages or brand moments", out)

    def test_journey_install_line_for_missing_tool(self):
        out = render_markdown(search(INDEX, "build a landing page from scratch"), "codex", INDEX)
        want = "   Install (codex): npx skills add wondelai/skills -s create-website -g -a codex"
        self.assertIn(want, out)
        lines = out.splitlines()
        j0 = lines.index("## Journeys")
        i = next(n for n, l in enumerate(lines) if n > j0 and l.startswith("1. create-website"))
        self.assertEqual(lines[i + 1], want)
        out_claude = render_markdown(search(INDEX, "build a landing page from scratch"), "claude", INDEX)
        self.assertNotIn("-s create-website", out_claude)


class CloseCallTests(unittest.TestCase):
    @staticmethod
    def _skills(*scores):
        return [(s, {"slug": "s%d" % n}) for n, s in enumerate(scores, 1)]

    def test_close_call_lists_leaders_within_share_of_top(self):
        self.assertEqual(close_call(self._skills(3.98, 3.97, 3.84, 1.37)), ["s1", "s2", "s3"])
        self.assertEqual(close_call(self._skills(4.0, 3.9, 3.7)), ["s1", "s2"])

    def test_close_call_empty_when_top_is_clear_or_alone(self):
        self.assertEqual(close_call(self._skills(4.0, 3.5)), [])
        self.assertEqual(close_call(self._skills(4.0)), [])
        self.assertEqual(close_call([]), [])

    def test_close_call_caps_at_three(self):
        self.assertEqual(close_call(self._skills(4, 4, 4, 4)), ["s1", "s2", "s3"])

    def test_render_shows_close_call_line_only_when_close(self):
        res = {"skills": self._skills(3.98, 3.97, 1.0), "journeys": [], "routes": []}
        out = render_markdown(res, "claude", INDEX)
        self.assertIn("Close call: s1, s2", out)
        res["skills"] = self._skills(4.0, 2.0)
        self.assertNotIn("Close call", render_markdown(res, "claude", INDEX))

    def test_json_has_close_call(self):
        rc, out, _ = _run(_local_index(), "--json")
        self.assertEqual(rc, 0)
        self.assertIsInstance(json.loads(out)["close_call"], list)


if __name__ == "__main__":
    unittest.main()
