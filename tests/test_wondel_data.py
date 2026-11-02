import sys, json, pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skill-finder" / "scripts"))
from common import validate_source

DATA = json.loads((ROOT / "skill-finder" / "data" / "sources" / "wondel.json").read_text(encoding="utf-8"))
SLUGS = {s["slug"] for s in DATA["skills"]}


class WondelData(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_source(DATA), [])

    def test_counts(self):
        self.assertEqual(len(DATA["skills"]), 51)
        self.assertEqual(len(DATA["journeys"]), 14)
        self.assertEqual(len(DATA["routes"]), 8)
        self.assertEqual(len(DATA["categories"]), 8)

    def test_slugs_unique_and_mapped(self):
        slugs = [s["slug"] for s in DATA["skills"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertIn("storybrand-messaging", slugs)
        self.assertNotIn("storybrand", slugs)
        self.assertIn("storybrand", [s["guide_slug"] for s in DATA["skills"]])

    def test_every_skill_has_category_in_list(self):
        for s in DATA["skills"]:
            self.assertIn(s["category"], DATA["categories"], s["slug"])

    def test_journey_skills_resolve(self):
        for j in DATA["journeys"]:
            self.assertGreaterEqual(len(j["skills"]), 3, j["slug"])
            for slug in j["skills"]:
                self.assertIn(slug, SLUGS, j["slug"])

    def test_route_steps_resolve(self):
        journeys = {j["slug"] for j in DATA["journeys"]}
        for r in DATA["routes"]:
            for slug, _text in r["steps"]:
                self.assertIn(slug, SLUGS, r["name"])
            if "shortcut" in r:
                self.assertIn(r["shortcut"], journeys, r["name"])

    def test_create_website_members(self):
        j = next(j for j in DATA["journeys"] if j["slug"] == "create-website")
        for slug in ("one-page-marketing", "storybrand-messaging", "refactoring-ui", "cro-methodology"):
            self.assertIn(slug, j["skills"])


if __name__ == "__main__":
    unittest.main()
