import sys, json, pathlib, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skill-finder" / "scripts"))
from common import validate_source, load_sources, expand_install

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "sources"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class ValidateSource(unittest.TestCase):
    def test_valid_source_passes(self):
        self.assertEqual(validate_source(load("extra.json")), [])

    def test_bad_source_errors(self):
        errors = validate_source(load("bad.json"))
        self.assertGreaterEqual(len(errors), 2)
        self.assertTrue(any("source" in e for e in errors))
        self.assertTrue(any("skills" in e for e in errors))

    def test_non_dict_rejected(self):
        self.assertEqual(len(validate_source([])), 1)

    def test_bad_slug_reports_json_path(self):
        data = load("extra.json")
        data["skills"].append({"slug": "Bad Slug", "summary": "x"})
        errors = validate_source(data)
        self.assertEqual(errors, ["skills[2].slug: must match ^[a-z0-9][a-z0-9-]*$"])

    def test_source_id_pattern(self):
        data = load("extra.json")
        data["source"] = "Bad_ID"
        self.assertEqual(len(validate_source(data)), 1)

    def test_optional_field_types_checked_individually(self):
        data = load("extra.json")
        data["homepage"] = 5
        data["categories"] = "x"
        data["skills"][0]["aliases"] = [1]
        data["skills"][0]["use_when"] = 3
        data["skills"][0]["name"] = 3
        errors = validate_source(data)
        self.assertEqual(len(errors), 5)
        for prefix in ("homepage", "categories", "skills[0].aliases", "skills[0].use_when", "skills[0].name"):
            self.assertTrue(any(e.startswith(prefix) for e in errors), prefix)

    def test_journeys_and_routes_validated(self):
        data = load("extra.json")
        data["journeys"] = [{"slug": "j", "name": "J", "skills": ["a"]}, {"name": "J2", "skills": "a"}]
        data["routes"] = [{"name": "R", "steps": [["a", "do it"]]}, {"name": "R2", "steps": [["a"]]}]
        errors = validate_source(data)
        self.assertTrue(any(e.startswith("journeys[1].slug") for e in errors))
        self.assertTrue(any(e.startswith("journeys[1].skills") for e in errors))
        self.assertTrue(any(e.startswith("routes[1].steps[0]") for e in errors))
        self.assertFalse(any(e.startswith("journeys[0]") or e.startswith("routes[0]") for e in errors))


class LoadSources(unittest.TestCase):
    def test_load_sources_skips_bad_with_warning(self):
        sources, warnings = load_sources(FIX)
        self.assertEqual([s["source"] for s in sources], ["extra"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("bad.json", warnings[0])

    def test_invalid_json_and_underscore_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p / "broken.json").write_text("{not json", encoding="utf-8")
            (p / "_ignored.json").write_text(json.dumps(load("extra.json")), encoding="utf-8")
            (p / "_schema.md").write_text("doc", encoding="utf-8")
            (p / "a.json").write_text(json.dumps(load("extra.json")), encoding="utf-8")
            sources, warnings = load_sources(p)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("broken.json: "))

    def test_real_data_dir_loads_clean(self):
        real = pathlib.Path(__file__).resolve().parents[1] / "skill-finder" / "data" / "sources"
        sources, warnings = load_sources(real)
        self.assertEqual(warnings, [])


class ExpandInstall(unittest.TestCase):
    def test_expand_install(self):
        self.assertEqual(expand_install("npx x -s {slug} -a {agent}", "a-b", "codex"), "npx x -s a-b -a codex")
        self.assertIsNone(expand_install(None, "a", "codex"))
