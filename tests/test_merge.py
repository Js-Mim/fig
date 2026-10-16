import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import streamlit as st
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from utils.csv_utils import compute_percentages, merge_accords, text_to_dataframe


def formula(rows):
    return pd.DataFrame(rows, columns=["Material", "Dilution", "Amount"])


class MergeAccordsTests(unittest.TestCase):
    def test_replacing_any_row_preserves_remaining_materials_and_total(self):
        accord = formula([("New A", "100%", 60), ("New B", "100%", 40)])
        for selected_index in range(3):
            with self.subTest(selected_index=selected_index):
                parent = formula([
                    ("Base A", "100%", 40),
                    ("Base B", "100%", 40),
                ])
                parent.loc[selected_index - 0.5] = ["Accord", "100%", 20]
                parent = parent.sort_index().reset_index(drop=True)
                parent.insert(0, "", False)
                original = parent.copy(deep=True)
                remaining = parent.drop(index=selected_index)
                remaining_original = remaining.copy(deep=True)

                result = merge_accords(remaining, accord, 0.2, 1.0)

                self.assertEqual(
                    result["Material"].tolist(), ["Base A", "Base B", "New A", "New B"]
                )
                self.assertEqual(result["Amount"].tolist(), [40, 40, 12, 8])
                self.assertAlmostEqual(result["Amount"].sum(), 100)
                self.assertTrue(result.index.is_unique)
                assert_frame_equal(parent, original)
                assert_frame_equal(remaining, remaining_original)

    def test_same_material_and_dilution_add_amounts_case_insensitively(self):
        parent = formula([("Rose", "100%", 80)])
        accord = formula([("ROSE", "100%", 100)])
        result = merge_accords(parent, accord, 0.2, 1.0)
        self.assertEqual(result["Material"].tolist(), ["Rose"])
        self.assertEqual(result["Amount"].tolist(), [100])

    def test_repeated_new_material_is_merged(self):
        parent = formula([("Base", "100%", 80)])
        accord = formula([("Rose", "100%", 60), ("rose", "100%", 40)])
        original = accord.copy(deep=True)
        result = merge_accords(parent, accord, 0.2, 1.0)
        self.assertEqual(result["Material"].tolist(), ["Base", "Rose"])
        self.assertEqual(result["Amount"].tolist(), [80, 20])
        assert_frame_equal(accord, original)

    def test_different_dilutions_preserve_active_material_at_stronger_dilution(self):
        for existing_dilution, added_dilution, expected_amount in [
            ("100%", "10%", 82),
            ("10%", "100%", 28),
        ]:
            with self.subTest(existing=existing_dilution, added=added_dilution):
                parent = formula([("Rose", existing_dilution, 80)])
                accord = formula([("Rose", added_dilution, 100)])
                result = merge_accords(parent, accord, 0.2, 1.0)
                self.assertEqual(len(result), 1)
                self.assertAlmostEqual(result.iloc[0]["Amount"], expected_amount)
                self.assertEqual(float(result.iloc[0]["Dilution"].rstrip("%")), 100)
                expected_active = (
                    80 * float(existing_dilution.rstrip("%")) / 100
                    + 20 * float(added_dilution.rstrip("%")) / 100
                )
                self.assertAlmostEqual(
                    result.iloc[0]["Amount"]
                    * float(result.iloc[0]["Dilution"].rstrip("%")) / 100,
                    expected_active,
                )

    def test_parent_dilution_does_not_round_small_accord_dilutions_to_zero(self):
        parent = formula([("Base", "100%", 80)])
        accord = formula([("Trace", "0.1%", 100)])
        result = merge_accords(parent, accord, 0.2, 0.01)
        self.assertAlmostEqual(float(result.iloc[1]["Dilution"].rstrip("%")), 0.001)
        self.assertEqual(result.iloc[1]["Amount"], 20)

    def test_numeric_csv_values_and_no_selection_column(self):
        parent = formula([("Rose", 100, 80)])
        accord = formula([("Rose", 100, 100)])
        result = merge_accords(parent, accord, 0.2, 1.0)
        self.assertEqual(result["Amount"].tolist(), [100])
        self.assertEqual(float(result.iloc[0]["Dilution"].rstrip("%")), 100)
        result = merge_accords(parent, formula([("Jasmine", 100, 100)]), 0.2, 1.0)
        self.assertEqual(result["Material"].tolist(), ["Rose", "Jasmine"])
        self.assertEqual(result["Amount"].tolist(), [80, 20])

    def test_text_inputs_in_parts_per_100(self):
        parent = text_to_dataframe("Base 100% 80\nAccord 100% 20")
        accord = text_to_dataframe("Rose 100% 60\nJasmine 50% 40")
        result = merge_accords(parent.drop(index=1), accord, 0.2, 1.0)
        analysed = compute_percentages(result)
        self.assertEqual(analysed["Amount"].tolist(), [80, 12, 8])
        self.assertEqual(
            analysed["Percentage (Relative)"].tolist(), ["80.000%", "12.000%", "8.000%"]
        )

    def test_explicit_text_columns_support_commas_and_decimal_values(self):
        result = text_to_dataframe("Material 123, 0.1%, 33.333333\nBase, 100, 66.666667")
        self.assertEqual(result["Material"].tolist(), ["Material 123", "Base"])
        self.assertEqual(result["Dilution"].tolist(), ["0.1%", "100%"])
        self.assertEqual(result["Amount"].tolist(), [33.333333, 66.666667])


class MergeAppTests(unittest.TestCase):
    def setUp(self):
        self.selected_indices = []
        data_editor = st.data_editor

        def select_in_editor(*args, **kwargs):
            result = data_editor(*args, **kwargs).copy()
            result.loc[self.selected_indices, ""] = True
            return result

        # AppTest cannot edit data_editor cells, so simulate only its returned selection.
        editor_patch = patch("streamlit.data_editor", side_effect=select_in_editor)
        editor_patch.start()
        self.addCleanup(editor_patch.stop)

    def start_app(self, text):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
        app.run()
        app.sidebar.text_area[0].input(text).run()
        self.assertEqual(list(app.exception), [])
        return app

    def select_rows(self, app, indices):
        self.selected_indices = indices
        app.run()
        self.assertEqual(list(app.exception), [])

    def test_analysis_chart_uses_numeric_absolute_percentages(self):
        app = self.start_app("Rose 10% 20\nBase 100% 80\nTrace 0.1% 0")
        with patch("streamlit.bar_chart", wraps=st.bar_chart) as chart:
            app.tabs[0].button[0].click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        chart.assert_called_once()
        chart_data = chart.call_args.args[0]
        self.assertEqual(chart.call_args.kwargs["y"], "Percentage (Absolute)")
        self.assertTrue(pd.api.types.is_numeric_dtype(chart_data["Percentage (Absolute)"]))
        self.assertEqual(chart_data["Percentage (Absolute)"].tolist(), [2, 80, 0])
        self.assertEqual(chart.call_args.kwargs["x"], "Material")
        self.assertTrue(chart.call_args.kwargs["horizontal"])
        self.assertEqual(
            app.tabs[0].dataframe[0].value["Percentage (Absolute)"].tolist(),
            ["2.000000%", "80.000000%", "0.000000%"],
        )

    def test_no_selection_and_multiple_selection_do_not_offer_accord_input(self):
        app = self.start_app("Base 100% 80\nAccord 100% 20")
        self.assertEqual(len(app.text_area), 1)
        self.select_rows(app, [0, 1])
        self.assertEqual(len(app.text_area), 1)
        self.assertTrue(any("only one material" in info.value for info in app.info))

    def test_selected_row_waits_for_accord_then_merges(self):
        app = self.start_app("Base A 100% 40\nAccord 100% 20\nBase B 100% 40")
        self.select_rows(app, [1])
        self.assertEqual(len(app.text_area), 2)
        self.assertEqual(list(app.error), [])
        self.assertEqual(len(app.dataframe), 2)
        self.assertFalse(any(button.label == "Place to FIGbench" for button in app.button))
        app.tabs[2].text_area[0].input("New A 100% 60\nNew B 100% 40").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        result = app.dataframe[-1].value
        self.assertEqual(
            result["Material"].tolist(), ["Base A", "Base B", "New A", "New B"]
        )
        self.assertEqual(result["Amount"].tolist(), [40, 40, 12, 8])
        self.assertAlmostEqual(result["Amount"].sum(), 100)
        self.assertFalse(result[""].any())
        self.assertTrue(any(button.label == "Place to FIGbench" for button in app.button))

    def test_place_to_figbench_persists_and_drives_all_operations(self):
        app = self.start_app("Base A 100% 40\nAccord 100% 20\nBase B 100% 40")
        self.select_rows(app, [1])
        app.tabs[2].text_area[0].input("New A 100% 60\nNew B 100% 40").run()
        merged = app.dataframe[-1].value[["Material", "Dilution", "Amount"]].copy()
        self.selected_indices = []
        app.tabs[2].button[0].click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        main = app.dataframe[0].value
        assert_frame_equal(main[["Material", "Dilution", "Amount"]], merged)
        self.assertEqual(main.columns.tolist(), ["", "Material", "Dilution", "Amount"])
        self.assertFalse(main[""].any())
        self.assertEqual(len(app.text_area), 1)
        self.assertFalse(any(button.label == "Place to FIGbench" for button in app.button))
        self.assertEqual(app.metric[0].value, "4")
        self.assertEqual(app.metric[1].value, "100.00")

        app.slider[0].set_value(5.0).run()
        assert_frame_equal(app.dataframe[0].value[merged.columns], merged)
        batch = app.tabs[1].dataframe[0].value
        self.assertEqual(batch["Material"].tolist(), merged["Material"].tolist())
        self.assertEqual(batch["Amount"].tolist(), [2, 2, 0.6, 0.4])
        app.tabs[0].button[0].click().run()
        analysed = app.tabs[0].dataframe[0].value
        self.assertEqual(analysed["Material"].tolist(), merged["Material"].tolist())
        self.assertEqual(analysed["Amount"].tolist(), [40, 40, 12, 8])

        self.select_rows(app, [2])
        self.assertEqual(app.tabs[2].text_area[0].value, "")
        app.tabs[2].text_area[0].input("Rose 100% 100").run()
        self.selected_indices = []
        app.tabs[2].button[0].click().run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.dataframe[0].value["Material"].tolist(), ["Base A", "Base B", "New B", "Rose"]
        )

        app.sidebar.text_area[0].input("Fresh 100% 100").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.dataframe[0].value["Material"].tolist(), ["Fresh"])
        self.assertEqual(app.dataframe[0].value["Amount"].tolist(), [100])

    def test_merge_uses_unrounded_selected_amount_and_parent_dilution(self):
        app = self.start_app("Base 100% 66.666667\nAccord 10% 33.333333")
        self.select_rows(app, [1])
        app.tabs[2].text_area[0].input("Rose 50% 100").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        result = app.dataframe[-1].value
        self.assertAlmostEqual(result.iloc[1]["Amount"], 33.333333, places=8)
        self.assertAlmostEqual(float(result.iloc[1]["Dilution"].rstrip("%")), 5)
        self.assertAlmostEqual(result["Amount"].sum(), 100)

    def test_invalid_accord_is_reported_and_can_be_corrected(self):
        app = self.start_app("Base 100% 80\nAccord 100% 20")
        self.select_rows(app, [1])
        app.tabs[2].text_area[0].input("not a formula").run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Failed to read accord" in error.value for error in app.error))
        self.assertFalse(any(button.label == "Place to FIGbench" for button in app.button))
        app.tabs[2].text_area[0].input("Rose 100% 100").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(list(app.error), [])
        self.assertEqual(app.dataframe[-1].value["Amount"].tolist(), [80, 20])


if __name__ == "__main__":
    unittest.main()
