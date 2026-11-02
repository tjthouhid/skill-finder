import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skill-finder" / "scripts"))
from unittest import mock
from common import default_roots, first_sentence, parse_frontmatter

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

    def test_plain_multiline_scalar_is_folded(self):
        meta, _ = parse_frontmatter("---\ndescription: Does a thing\n  and continues here: yes\nname: x\n---\n")
        self.assertEqual(meta["description"], "Does a thing and continues here: yes")
        self.assertEqual(meta["name"], "x")

    def test_literal_block_keeps_newlines(self):
        meta, _ = parse_frontmatter("---\nl: |\n  one\n  two\nn: y\n---\n")
        self.assertEqual(meta["l"], "one\ntwo")
        self.assertEqual(meta["n"], "y")

    def test_comment_lines_ignored(self):
        meta, _ = parse_frontmatter("---\n# top\nname: x\n  # indented\nother: y\n---\n")
        self.assertEqual(meta, {"name": "x", "other": "y"})

    def test_list_at_key_indent(self):
        meta, _ = parse_frontmatter("---\ntools:\n- a\n- 'b c'\nname: x\n---\n")
        self.assertEqual(meta["tools"], ["a", "b c"])
        self.assertEqual(meta["name"], "x")

    def test_unclosed_quote_kept_raw(self):
        meta, _ = parse_frontmatter("---\na: 'unclosed\nb: 1\n---\nx")
        self.assertEqual(meta["a"], "'unclosed")
        self.assertEqual(meta["b"], "1")

    def test_third_nesting_level_kept_raw(self):
        meta, _ = parse_frontmatter("---\nm:\n  k:\n    deep: 1\n  j: 2\n---\n")
        self.assertEqual(meta["m"], {"k": "deep: 1", "j": "2"})

    def test_crlf_input(self):
        meta, body = parse_frontmatter("---\r\nname: x\r\ndescription: 'a\r\n  b'\r\n---\r\n# Body\r\n")
        self.assertEqual(meta, {"name": "x", "description": "a b"})
        self.assertEqual(body.strip(), "# Body")

class FirstSentence(unittest.TestCase):
    def test_cuts_at_sentence_end(self):
        self.assertEqual(first_sentence("Do a thing. Then another."), "Do a thing.")
    def test_version_number_not_a_boundary(self):
        self.assertEqual(first_sentence("Uses v1.5 tokens. More."), "Uses v1.5 tokens.")

class DefaultRoots(unittest.TestCase):
    def test_codex_scans_codex_and_agents_skill_folders(self):
        home = pathlib.Path("/home/someone")
        with mock.patch.object(pathlib.Path, "home", return_value=home):
            roots = default_roots()
        self.assertEqual(roots["codex"], [home / ".codex" / "skills", home / ".agents" / "skills"])
