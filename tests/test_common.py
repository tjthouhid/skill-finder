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
