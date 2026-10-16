import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from utils.ifra_utils import (
    BOTANICAL_NAME,
    CONSTITUENT,
    LIMIT,
    NCS_CONCENTRATION,
    NCS_NAME,
    STANDARD_NAME,
    load_ifra_tables,
    normalize_name,
    scan_ifra,
)


def formula(*rows):
    return pd.DataFrame(rows, columns=["Material", "Dilution", "Amount"])


def standards(*rows):
    return pd.DataFrame(
        rows, columns=[STANDARD_NAME, "Synonyms", LIMIT, "IFRA Standard type"]
    )


def naturals(*rows):
    return pd.DataFrame(rows, columns=[NCS_NAME, BOTANICAL_NAME, CONSTITUENT, NCS_CONCENTRATION])


class IfraScanTests(unittest.TestCase):
    def setUp(self):
        self.standards = standards(
            ("Coumarin", "Tonka constituent\nAlias (commercial name)", 1.5, "RESTRICTION"),
            ("Eugenol", "Eugenol alias (mixture of isomers)", 2.5, "RESTRICTION"),
        )
        self.naturals = naturals(
            ("Test oil", "Testus plantus", "Coumarin", 10),
            ("Test oil", "Testus plantus", "Eugenol alias", 5),
            ("Other oil", "Otherus plantus", "Coumarin", 20),
        )

    def test_explanations_removed_but_chemical_parentheses_preserved(self):
        self.assertEqual(normalize_name(" Alias (Commercial name) "), "alias")
        self.assertEqual(normalize_name("Alias (mixture of isomers)"), "alias")
        for name in ["(E)-Compound", "2-(1-methylethyl)-phenol", "Compound (R)", "(+)-Compound"]:
            self.assertEqual(normalize_name(name), name.casefold())
        table = standards(("Chemical", "2-(1-methylethyl)-phenol", 1, "RESTRICTION"))
        result, _, issues = scan_ifra(
            formula(("2--phenol", "100%", 100)), table, self.naturals
        )
        self.assertTrue(result.empty)
        self.assertEqual(len(issues), 1)
        result, _, issues = scan_ifra(
            formula(("2-(1-methylethyl)-phenol", "100%", 100)), table, self.naturals
        )
        self.assertEqual(result.iloc[0][STANDARD_NAME], "Chemical")
        self.assertTrue(issues.empty)

    def test_direct_aliases_case_whitespace_and_dilution(self):
        data = formula(("  ALIAS  ", "10%", 20), ("unknown", "100%", 80))
        before = data.copy(deep=True)
        summary, contributions, issues = scan_ifra(data, self.standards, self.naturals)
        self.assertEqual(summary.iloc[0][STANDARD_NAME], "Coumarin")
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 2)
        self.assertEqual(summary.iloc[0]["Headroom (percentage points)"], -0.5)
        self.assertAlmostEqual(summary.iloc[0]["Limit used (%)"], 2 / 1.5 * 100)
        self.assertEqual(summary.iloc[0]["Status"], "Above limit")
        self.assertEqual(contributions.iloc[0]["Match"], "Direct")
        self.assertEqual(issues["Material"].tolist(), ["unknown"])
        assert_frame_equal(data, before)

    def test_shared_constituents_sum_across_direct_and_natural_sources(self):
        data = formula(
            ("Coumarin", "100%", 1),
            ("Test oil", "50%", 10),
            ("Otherus plantus", "100%", 5),
            ("unmatched", "100%", 84),
        )
        summary, contributions, issues = scan_ifra(data, self.standards, self.naturals)
        by_name = summary.set_index(STANDARD_NAME)
        self.assertAlmostEqual(by_name.at["Coumarin", "Total Absolute Percentage (%)"], 2.5)
        self.assertAlmostEqual(by_name.at["Eugenol", "Total Absolute Percentage (%)"], 0.25)
        self.assertEqual(by_name.at["Coumarin", "Status"], "Above limit")
        self.assertEqual(by_name.at["Eugenol", "Status"], "Below limit")
        self.assertEqual(len(contributions), 4)
        self.assertEqual(len(issues), 1)

    def test_direct_standard_takes_precedence_over_natural_lookup(self):
        ncs = naturals(("Coumarin", "Test botanical", "Eugenol", 50))
        summary, contributions, issues = scan_ifra(
            formula(("Coumarin", "100%", 100)), self.standards, ncs
        )
        self.assertEqual(summary[STANDARD_NAME].tolist(), ["Coumarin"])
        self.assertEqual(contributions["Match"].tolist(), ["Direct"])
        self.assertTrue(issues.empty)

    def test_repeated_direct_aliases_sum_to_one_standard(self):
        summary, contributions, issues = scan_ifra(
            formula(("Coumarin", "1%", 50), ("Tonka constituent", "2%", 50)),
            self.standards, self.naturals,
        )
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 1.5)
        self.assertEqual(summary.iloc[0]["Status"], "At limit")
        self.assertEqual(len(contributions), 2)
        self.assertTrue(issues.empty)

    def test_botanical_match_collects_all_rows_of_the_identified_natural(self):
        ncs = naturals(
            ("Oil", "Botanical", "Coumarin", 10),
            ("Oil", "Botanical alternative", "Eugenol", 20),
        )
        summary, _, issues = scan_ifra(
            formula(("Botanical", "100%", 100)), self.standards, ncs
        )
        self.assertEqual(set(summary[STANDARD_NAME]), {"Coumarin", "Eugenol"})
        self.assertTrue(issues.empty)

    def test_botanical_ambiguity_requires_exact_natural_name(self):
        ncs = naturals(
            ("Oil", "Same botanical", "Coumarin", 10),
            ("Absolute", "Same botanical", "Coumarin", 20),
        )
        summary, _, issues = scan_ifra(
            formula(("Same botanical", "100%", 100)), self.standards, ncs
        )
        self.assertTrue(summary.empty)
        self.assertIn("multiple natural materials", issues.iloc[0]["Issue"])
        summary, _, issues = scan_ifra(
            formula(("Oil", "100%", 100)), self.standards, ncs
        )
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 10)
        self.assertTrue(issues.empty)

    def test_duplicate_natural_records_not_double_counted(self):
        ncs = pd.concat([self.naturals, self.naturals], ignore_index=True)
        summary, contributions, issues = scan_ifra(
            formula(("Test oil", "100%", 100)), self.standards, ncs
        )
        self.assertEqual(len(contributions), 2)
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 10)
        self.assertTrue(issues.empty)

    def test_invalid_conflicting_and_missing_constituents_are_reported(self):
        for rows, message in [
            ([("Oil", "Botanical", "Coumarin", "0..3")], "Not a plain numeric"),
            ([
                ("Oil", "Botanical", "Coumarin", 10),
                ("Oil", "Botanical", "Coumarin", 20),
            ], "conflicting"),
            ([("Oil", "Botanical", "Not a standard", 10)], "not found"),
            ([("Oil", "Botanical", None, 10)], "no constituent"),
            ([("Oil", "Botanical", "Coumarin", 101)], "between 0 and 100"),
        ]:
            with self.subTest(message=message):
                summary, _, issues = scan_ifra(
                    formula(("Oil", "100%", 100)), self.standards, naturals(*rows)
                )
                self.assertTrue(summary.empty)
                self.assertIn(message, issues.iloc[0]["Issue"])

    def test_limits_comma_prohibition_and_nonnumeric_entries(self):
        cases = [
            ("0,40", "RESTRICTION", "Above limit", 0.4),
            ("1%", "RESTRICTION", "At limit", 1.0),
            (2, "RESTRICTION", "Below limit", 2.0),
            (None, "PROHIBITION", "Prohibited", 0.0),
            (None, "SPECIFICATION", "Manual review required", None),
            ("See Notebox", "PROHIBITION_RESTRICTION", "Manual review required", None),
            ("0.0015 (5-MOP)", "RESTRICTION", "Manual review required", None),
            ("No Restriction", "RESTRICTION", "No Category 4 restriction listed", None),
        ]
        for value, kind, status, expected_limit in cases:
            with self.subTest(value=value, kind=kind):
                table = standards(("Test", "", value, kind))
                summary, _, _ = scan_ifra(
                    formula(("Test", "1%", 100)), table, self.naturals
                )
                self.assertEqual(summary.iloc[0]["Status"], status)
                if expected_limit is None:
                    self.assertTrue(pd.isna(summary.iloc[0][LIMIT]))
                else:
                    self.assertEqual(summary.iloc[0][LIMIT], expected_limit)

    def test_numeric_dilution_conventions(self):
        for dilution in [10, "10", 0.1, "0.1", "10%"]:
            with self.subTest(dilution=dilution):
                summary, _, _ = scan_ifra(
                    formula(("Coumarin", dilution, 100)), self.standards, self.naturals
                )
                self.assertAlmostEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 10)

    def test_near_limit_does_not_round_away_a_real_exceedance(self):
        summary, _, _ = scan_ifra(
            formula(("Coumarin", "100%", 1.5000001), ("Unknown", "100%", 98.4999999)),
            self.standards, self.naturals,
        )
        self.assertEqual(summary.iloc[0]["Status"], "Above limit")
        self.assertLess(summary.iloc[0]["Headroom (percentage points)"], 0)

    def test_invalid_formula_and_missing_headers_raise(self):
        for data in [
            formula(("Coumarin", "100%", 0)),
            formula(("Coumarin", "100%", -1)),
            formula(("Coumarin", "bad", 100)),
            formula(("Coumarin", "101%", 100)),
            formula(("Coumarin", "100%", float("nan"))),
            formula(("Coumarin", "100%", float("inf"))),
            formula(("", "100%", 100)),
        ]:
            with self.subTest(data=data.to_dict()):
                with self.assertRaises(ValueError):
                    scan_ifra(data, self.standards, self.naturals)
        with self.assertRaisesRegex(ValueError, "missing columns"):
            scan_ifra(formula(("Coumarin", "100%", 100)), pd.DataFrame(), self.naturals)

    def test_small_scientific_and_leading_decimal_percentages_remain_numeric(self):
        summary, _, _ = scan_ifra(
            formula(("Coumarin", ".5%", 100)),
            standards(("Coumarin", "", 1e-5, "RESTRICTION")), self.naturals,
        )
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 0.5)
        self.assertEqual(summary.iloc[0][LIMIT], 1e-5)
        self.assertEqual(summary.iloc[0]["Status"], "Above limit")

    def test_multiple_standard_matches_are_not_silently_selected(self):
        table = standards(
            ("First", "Shared", 1, "RESTRICTION"),
            ("Second", "Shared", 2, "RESTRICTION"),
        )
        summary, _, issues = scan_ifra(
            formula(("Shared", "100%", 100)), table, self.naturals
        )
        self.assertEqual(len(summary), 2)
        self.assertIn("Multiple standards", issues.iloc[0]["Issue"])


class IfraWorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.standards, cls.naturals = load_ifra_tables()

    def test_real_workbook_headers_synonyms_and_natural_contributions(self):
        data = formula(
            ("Trimofix O", "100%", 1),
            ("Coumarin", "100%", 1),
            ("Lavender oil", "100%", 10),
            ("Unknown base", "100%", 88),
        )
        summary, contributions, issues = scan_ifra(data, self.standards, self.naturals)
        direct = contributions[contributions["Material"] == "Trimofix O"]
        self.assertEqual(len(direct), 1)
        self.assertEqual(direct.iloc[0]["Contribution (%)"], 1)
        natural = contributions[contributions["Material"] == "Lavender oil"]
        self.assertEqual(len(natural), 3)
        self.assertTrue(natural["Match"].eq("Natural").all())
        octenyl = natural[natural["Constituent"] == "1-Octen-3-yl acetate"].iloc[0]
        self.assertAlmostEqual(octenyl["Constituent in natural (%)"], 1.04)
        self.assertAlmostEqual(octenyl["Contribution (%)"], 0.104)
        coumarin = summary[summary[STANDARD_NAME] == "Coumarin"].iloc[0]
        self.assertEqual(coumarin["Total Absolute Percentage (%)"], 1)
        self.assertEqual(coumarin[LIMIT], 1.5)
        self.assertEqual(coumarin["Headroom (percentage points)"], 0.5)
        self.assertTrue(issues["Material"].eq("Unknown base").any())
        self.assertFalse(summary.empty)

    def test_real_bad_concentration_is_explicitly_reported(self):
        _, _, issues = scan_ifra(
            formula(("Cassia bark oil", "100%", 100)), self.standards, self.naturals
        )
        self.assertTrue(issues["Issue"].str.contains("0..3", regex=False).any())


class IfraAppTests(unittest.TestCase):
    def test_button_scans_current_edited_table_not_batch_or_source(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.sidebar.text_area[0].input("Coumarin 100% 1\nBase 100% 99").run()
        edited = formula(("Coumarin", "100%", 2), ("Base", "100%", 98))
        edited.insert(0, "", False)
        with patch("streamlit.data_editor", return_value=edited):
            next(button for button in app.button if button.label == "IFRA Scan").click().run()
        self.assertEqual(list(app.exception), [])
        summary = next(
            frame.value for frame in app.dataframe
            if "Total Absolute Percentage (%)" in frame.value.columns
        )
        self.assertEqual(summary.iloc[0]["Total Absolute Percentage (%)"], 2)
        self.assertEqual(summary.iloc[0]["Status"], "Above limit")
        self.assertTrue(any("exceed" in error.value for error in app.error))
        self.assertTrue(any("incomplete" in warning.value for warning in app.warning))

    def test_workbook_load_failure_is_visible(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        app.sidebar.text_area[0].input("Coumarin 100% 100").run()
        with patch("utils.ifra_utils.load_ifra_tables", side_effect=OSError("Missing workbook")):
            next(button for button in app.button if button.label == "IFRA Scan").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Missing workbook" in error.value for error in app.error))


if __name__ == "__main__":
    unittest.main()
