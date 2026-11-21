import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_stats as gs


GRAPHQL_FIXTURE = {
    "data": {
        "user": {
            "createdAt": "2022-11-17T15:50:54Z",
            "contributionsCollection": {
                "contributionCalendar": {
                    "totalContributions": 12,
                    "weeks": [
                        {
                            "contributionDays": [
                                {"date": "2026-01-04", "contributionCount": 0},
                                {"date": "2026-01-05", "contributionCount": 2},
                                {"date": "2026-01-06", "contributionCount": 0},
                                {"date": "2026-01-07", "contributionCount": 0},
                                {"date": "2026-01-08", "contributionCount": 0},
                                {"date": "2026-01-09", "contributionCount": 0},
                                {"date": "2026-01-10", "contributionCount": 0},
                            ]
                        },
                        {
                            "contributionDays": [
                                {"date": "2026-01-11", "contributionCount": 0},
                                {"date": "2026-01-12", "contributionCount": 0},
                                {"date": "2026-01-13", "contributionCount": 5},
                                {"date": "2026-01-14", "contributionCount": 0},
                                {"date": "2026-01-15", "contributionCount": 0},
                                {"date": "2026-01-16", "contributionCount": 0},
                                {"date": "2026-01-17", "contributionCount": 0},
                            ]
                        },
                        {
                            "contributionDays": [
                                {"date": "2026-01-18", "contributionCount": 0},
                                {"date": "2026-01-19", "contributionCount": 0},
                                {"date": "2026-01-20", "contributionCount": 0},
                                {"date": "2026-01-21", "contributionCount": 0},
                                {"date": "2026-01-22", "contributionCount": 0},
                                {"date": "2026-01-23", "contributionCount": 0},
                                {"date": "2026-01-24", "contributionCount": 0},
                            ]
                        },
                    ],
                }
            },
            "allRepos": {"totalCount": 28},
            "ownRepos": {
                "totalCount": 22,
                "nodes": [
                    {
                        "name": "a",
                        "primaryLanguage": {"name": "Python"},
                        "languages": {"edges": [
                            {"size": 100, "node": {"name": "Python"}},
                            {"size": 40, "node": {"name": "Go"}},
                        ]},
                    },
                    {
                        "name": "b",
                        "primaryLanguage": {"name": "Python"},
                        "languages": {"edges": [{"size": 50, "node": {"name": "Python"}}]},
                    },
                    {
                        "name": "c",
                        "primaryLanguage": {"name": "Go"},
                        "languages": {"edges": [{"size": 300, "node": {"name": "Go"}}]},
                    },
                    {
                        "name": "d",
                        "primaryLanguage": {"name": "Vue"},
                        "languages": {"edges": [{"size": 25, "node": {"name": "Vue"}}]},
                    },
                    {"name": "e", "primaryLanguage": None, "languages": {"edges": []}},
                ],
            },
        }
    }
}


def fixture_data():
    return gs.normalize(GRAPHQL_FIXTURE)


class NormalizeTests(unittest.TestCase):
    def test_calendar_metrics(self):
        data = fixture_data()
        self.assertEqual(data["total_contributions"], 12)
        self.assertEqual(data["active_days"], 2)
        self.assertEqual(data["peak_day"], 5)
        self.assertEqual(data["public_repos"], 28)
        self.assertEqual(data["original_repos"], 22)

    def test_language_bytes(self):
        data = fixture_data()
        sizes = dict(data["languages"])
        self.assertEqual(sizes["Python"], 150)
        self.assertEqual(sizes["Go"], 340)
        self.assertEqual(sizes["Vue"], 25)

    def test_weeks_keep_seven_days(self):
        data = fixture_data()
        self.assertEqual(len(data["weeks"]), 3)
        self.assertEqual([len(w["days"]) for w in data["weeks"]], [7, 7, 7])
        self.assertEqual(data["weeks"][0]["start"], "2026-01-04")


class ActivityTests(unittest.TestCase):
    def test_every_day_is_a_cell(self):
        svg = gs.build_activity_svg(fixture_data())
        self.assertEqual(svg.count('class="cell"'), 21)

    def test_metrics_are_rendered(self):
        svg = gs.build_activity_svg(fixture_data())
        for value in [">12<", ">2<", ">5<", ">28<"]:
            self.assertIn(value, svg)

    def test_month_labels_and_title(self):
        svg = gs.build_activity_svg(fixture_data())
        self.assertIn("SYSTEM LOAD // ACTIVITY", svg)
        self.assertIn(">JAN<", svg)


class StackTests(unittest.TestCase):
    def test_segments_fill_the_bar(self):
        svg = gs.build_stack_svg(fixture_data())
        widths = [float(x) for x in gs._segment_widths(svg)]
        self.assertAlmostEqual(sum(widths) + 2 * (len(widths) - 1), 964, delta=2)

    def test_language_labels_and_totals(self):
        svg = gs.build_stack_svg(fixture_data())
        for label in ["GO", "PYTHON", "VUE"]:
            self.assertIn(label, svg)
        self.assertIn("LANGUAGE VOLUME", svg)
        self.assertIn("%", svg)
        self.assertIn("TOTAL", svg)


class TelemetryTests(unittest.TestCase):
    def test_nodes_token_is_replaced(self):
        template = '<text>NODES</text><text>{{NODES}}</text>'
        svg = gs.render_telemetry(template, fixture_data())
        self.assertIn(">28<", svg)
        self.assertNotIn("{{NODES}}", svg)


if __name__ == "__main__":
    unittest.main()
