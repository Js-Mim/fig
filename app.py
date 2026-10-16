# imports
import io
import requests
import streamlit as st
from utils.csv_utils import *
from utils.formula_utis import calculate_batch_amount
from utils.pdf_utils import grab_formula
from utils.ifra_utils import load_ifra_tables, scan_ifra

# helpers
def reset_editor():
    for key in ("csv_editor", "accord_text", "accord_csv"):
        st.session_state.pop(key, None)


def place_to_figbench(merged_df):
    st.session_state["figbench_table"] = merged_df[
        ["Material", "Dilution", "Amount"]
    ].reset_index(drop=True).copy()
    reset_editor()

# Headline & Title
st.set_page_config(page_title="FIG-Workbench", layout="wide")
st.title("FIGbench")
st.caption("Upload your CSV including the materials and select an operation to proceed.")

# Upload Sidebar
with st.sidebar:
    st.title("Grabing Options")
    st.header("Text Input")
    formula_text = st.text_area(
        "Formula must include the following information: Material, Dilution, Amount in this exact order comma or space separated. " \
        "Each material must be provided on a new line.",
        height=120,
    )
    st.header("PDF Input")
    uploaded_pdf_file = st.file_uploader("Upload PDF", type=["pdf"])
    pdf_url = st.text_input('The URL link to the PDF file')
    st.header("CSV Input")
    uploaded_csv_file = st.file_uploader("Upload CSV", type=["csv"])
    separator = "," #st.text_input("Separator", value=",", max_chars=1)
    encoding = "utf-8" #st.text_input("Encoding", value="utf-8")


if not uploaded_csv_file and not formula_text.strip() and not uploaded_pdf_file and not pdf_url:
    for key in ("figbench_source", "figbench_table"):
        st.session_state.pop(key, None)
    reset_editor()
    st.info("Upload a CSV or PDF file or type your formula inside the Text Input to start.")
    st.stop()


if uploaded_csv_file:
    try:
        csv_value = uploaded_csv_file.getvalue()
        dataframe = load_csv(csv_value, separator=separator, encoding=encoding)
    except Exception as exc:  # pragma: no cover - runtime UI path
        st.error(f"Failed to read CSV: {exc}")
        st.stop()
if uploaded_pdf_file:
    try:
        pdf_values = uploaded_pdf_file.getvalue()
        pdf_values = io.BytesIO(pdf_values)  # Convert bytes to BytesIO for pdfplumber
        formula_list = grab_formula(pdf_values)  # Getting a list here
        if not formula_list:
            st.warning("No valid materials found in the PDF.")
            st.stop()
        # Convert list to DataFrame
        dataframe = list_to_dataframe(formula_list)
    except Exception as exc:  # pragma: no cover - runtime UI path
        st.error(f"Failed to read PDF: {exc}")
        st.stop()
if pdf_url:
    response = requests.get(pdf_url)
    if response.status_code == 200:
        formula_list = grab_formula(io.BytesIO(response.content))
        if not formula_list:
            st.warning("No valid materials found in the PDF.")
            st.stop()
        # Convert list to DataFrame
        dataframe = list_to_dataframe(formula_list)
if formula_text.strip():
    dataframe = text_to_dataframe(formula_text)

if (
    "figbench_source" not in st.session_state
    or not dataframe.equals(st.session_state["figbench_source"])
):
    st.session_state["figbench_source"] = dataframe.copy()
    st.session_state["figbench_table"] = dataframe.copy()
    reset_editor()

# CSV Preview & Edit
st.subheader("Preview & Edit")
st.caption("Edit CSV data")
dataframe = st.session_state["figbench_table"].reset_index(drop=True).copy()
dataframe.insert(0, "", False)  
edited_df = st.data_editor(
    dataframe,
    use_container_width=True,
    num_rows="dynamic",
    key="csv_editor",
    hide_index=True,
)
st.metric("Materials found", value=len(edited_df))  # Point out number of materials
st.metric("Total Amount",
          value=f"{edited_df['Amount'].sum():.2f}")  # Point out total amount



# Features & Operations
st.subheader("Operations")
if st.button("IFRA Scan"):
    st.subheader("IFRA 51st Amendment - Category 4 screening")
    st.caption(
        "The FIGbench formula is treated as the finished product. Direct additions and "
        "matched natural contributions are summed per standard. This is a name-based "
        "screening and not an IFRA compliance certificate! "
        "Specifications, notebox conditions, and unmatched materials require review."
    )
    try:
        standards, naturals = load_ifra_tables()
        summary, contributions, issues = scan_ifra(edited_df, standards, naturals)
    except (OSError, ImportError, ValueError, TypeError, KeyError) as exc:
        st.error(f"Failed to scan IFRA data: {exc}")
    else:
        if not summary.empty:
            if summary["Status"].isin(["Above limit", "Prohibited"]).any():
                st.error("One or more assessed constituents exceed a Category 4 limit or are prohibited.")
            if summary["Status"].eq("Manual review required").any():
                st.warning("Some Category 4 entries cannot be evaluated numerically; review the standards.")
            st.dataframe(summary, hide_index=True, use_container_width=True)
        else:
            st.warning("No standard totals could be assessed.")
        if not issues.empty:
            st.warning("The scan is incomplete. Unmatched, ambiguous, or invalid records are listed below.")
            st.dataframe(issues, hide_index=True, use_container_width=True)
        if not contributions.empty:
            with st.expander("Source contributions"):
                st.dataframe(contributions, hide_index=True, use_container_width=True)

ops_percentages, ops_batches, fig_merge  = st.tabs(
    ["Grab Percentages", "Prepare Batches", "FIG Merge"]
)
with ops_percentages:
    working_df = edited_df.copy()
    amount_column = "Amount"  # Defaults to "Amount" column
    if st.button("Analyse"):
        try:
            working_df = compute_percentages(working_df, column=amount_column)
            st.success("Dataframe updated with Percentage column.")
            st.subheader("Updated Data")
            st.dataframe(working_df, use_container_width=True,
                         width='stretch', hide_index=True, 
                         column_order=(working_df.columns.tolist()[1:]))
            st.metric("Materials found", value=len(edited_df))  # Point out number of materials
            concentration_val, diluents = compute_concentration(working_df)
            st.metric(f"Total concentration of enlisted materials, minus detected diluent(s): {diluents}", value=f"{concentration_val:.2f}%")
            chart_df = working_df[["Material", "Percentage (Absolute)"]].copy()
            chart_df["Percentage (Absolute)"] = chart_df["Percentage (Absolute)"].str.rstrip("%").astype(float)
            st.bar_chart(
                chart_df, x="Material", y="Percentage (Absolute)",
                x_label="Absolute %", horizontal=True, use_container_width=True,
            )
        except ValueError as exc:
            st.error(str(exc))

with ops_batches:
    working_df = edited_df.copy()
    batch_amount = st.slider("Select the desired amount (grams)", min_value=0.5,
                             max_value=20.0, step=0.5, value=10.0)
    dilution_q = st.checkbox("Dilution Adjustment", value=False)
    if batch_amount:
        analysed_df = compute_percentages(working_df, column=amount_column)
        if dilution_q:
            st.info("Dilution adjustment is enabled. Amounts below the threshold will be adjusted.")
            new_amount_series, new_dilution_series = calculate_batch_amount(analysed_df, batch_amount)
        else:
            new_amount_series = analysed_df["Percentage (Relative)"].copy().apply(lambda x: (float(x.rstrip("%")) / 100.0) * batch_amount)
            new_dilution_series = analysed_df["Dilution"].copy()
        
        working_df["Amount"] = new_amount_series
        working_df["Dilution"] = new_dilution_series
        st.dataframe(working_df, use_container_width=True,
                     width='stretch', hide_index=True, column_order=(working_df.columns.tolist()[1:]))
        new_total = float(working_df["Amount"].sum())
        assert abs(new_total - batch_amount) < 1e-2, "Total amount does not match the desired batch amount."
with fig_merge:
    merge_info = st.info("Please select the row you wish to replace with a given accord. Then provide the accord using the uploaders below.")
    working_df = edited_df.copy()
    accord_df = None
    selected_rows = edited_df.loc[edited_df['']==True]
    if len(selected_rows) > 0:
        merge_info.empty()
        if len(selected_rows) > 1:
            st.info("Currently only one-by-one merging is supported. Please select only one material")
        else:
            st.info(f"Selected accord {selected_rows['Material'].values[0]} for merging.")
            st.info(f"Please provide the accord you wish to add to the list using the uploaders below.")
            accord_text = st.text_area(
                    "Formula must include the following information: Material, Dilution, Amount in this exact order comma or space separated. " \
                    "Each material must be provided on a new line.",
                    height=120,
                    key="accord_text",
                )
            accord_csv_file = st.file_uploader("Upload CSV", type=["csv"], key="accord_csv")
            if accord_csv_file:
                try:
                    accord_value = accord_csv_file.getvalue()
                    accord_df = load_csv(accord_value, separator=separator, encoding=encoding)
                except Exception as exc:  # pragma: no cover - runtime UI path
                    st.error(f"Failed to read CSV: {exc}")
                    st.stop()
            if accord_text.strip():
                try:
                    accord_df = text_to_dataframe(accord_text.strip())
                except ValueError as exc:
                    st.error(f"Failed to read accord: {exc}")
                    st.stop()

            # Start replacing the selected row with the new accord_df
            if accord_df is not None:
                try:
                    analysed_df = compute_percentages(working_df, column=amount_column)
                    selected_row = analysed_df.loc[selected_rows.index[0]]
                    relative_factor = selected_row["Amount"] / analysed_df["Amount"].sum()
                    parent_used_dilution = float(selected_row["Dilution"].rstrip("%")) / 100.
                    working_df = working_df.drop(selected_rows.index)
                    working_df = merge_accords(
                        working_df, accord_df, relative_factor, parent_used_dilution
                    )
                    working_df = compute_percentages(working_df, column=amount_column)

                    new_column_list = working_df.columns.tolist()
                    st.dataframe(working_df, use_container_width=True,
                                 width='stretch', hide_index=True,
                                 column_order=(new_column_list[1:4] + new_column_list[5:6])
                                 )
                    st.button(
                        "Place to FIGbench",
                        on_click=place_to_figbench,
                        args=(working_df,),
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(f"Failed to merge accord: {exc}")