# imports
import io
import requests
import streamlit as st
from utils.csv_utils import *
from utils.formula_utis import calculate_batch_amount
from utils.pdf_utils import grab_formula


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

# CSV Preview & Edit
st.subheader("Preview & Edit")
st.caption("Edit CSV data")
dataframe = dataframe.reset_index(drop=True)  # Reset index to ensure proper alignment
dataframe.insert(0, "", False)  
edited_df = st.data_editor(
    dataframe,
    use_container_width=True,
    num_rows="dynamic",
    key="csv_editor",
    hide_index=True,
)
st.metric("Materials found", value=len(edited_df))  # Point out number of materials
st.metric("Total Amount", value=edited_df["Amount"].sum())



# Features & Operations
st.subheader("Operations")
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
            st.metric("Total concentration of enlisted materials, minus detected diluent(s)", value=f"{compute_concentration(working_df):.2f}%")
            st.bar_chart(working_df, x="Material", y="Amount", horizontal=True, use_container_width=True)
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
                )
            accord_csv_file = st.file_uploader("Upload CSV", type=["csv"])
            if accord_csv_file:
                try:
                    accord_value = accord_csv_file.getvalue()
                    accord_df = load_csv(accord_value, separator=separator, encoding=encoding)
                except Exception as exc:  # pragma: no cover - runtime UI path
                    st.error(f"Failed to read CSV: {exc}")
                    st.stop()
            if accord_text:
                accord_df = text_to_dataframe(accord_text.strip())

            # Start replacing the selected row with the new accord_df
            try:
                _df_dump = compute_percentages(working_df, column=amount_column)
                relative_factor = float(_df_dump["Percentage (Relative)"][selected_rows[""].index.values[0]].replace("%", "")) / 100.                
                parent_used_dilution = float(_df_dump["Dilution"][selected_rows[""].index.values[0]].replace("%", "")) / 100.
                working_df = working_df.drop(selected_rows.index)
                working_df = merge_accords(working_df, accord_df, relative_factor, parent_used_dilution)
                working_df = compute_percentages(working_df, column=amount_column)

                new_column_list = working_df.columns.tolist()
                st.dataframe(working_df, use_container_width=True,
                             width='stretch', hide_index=True, 
                             column_order=(new_column_list[1:4] + new_column_list[5:6])
                             )
                
            except AttributeError as exc:
                pass