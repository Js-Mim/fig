# imports
import io
import base64
import streamlit as st
from utils.pdf_utils import grab_formula
from utils.csv_utils import load_csv, text_to_dataframe, compute_percentages, list_to_dataframe, compute_concentration

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
        "Each material must be on a new line.",
        height=120,
    )
    st.header("PDF Input")
    uploaded_pdf_file = st.file_uploader("Upload PDF", type=["pdf"])
    st.header("CSV Input")
    uploaded_csv_file = st.file_uploader("Upload CSV", type=["csv"])
    separator = "," #st.text_input("Separator", value=",", max_chars=1)
    encoding = "utf-8" #st.text_input("Encoding", value="utf-8")


if not uploaded_csv_file and not formula_text.strip() and not uploaded_pdf_file:
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
if formula_text.strip():
    dataframe = text_to_dataframe(formula_text)

# CSV Preview & Edit
st.subheader("Preview & Edit")
st.caption("Edit CSV data")
edited_df = st.data_editor(
    dataframe,
    use_container_width=True,
    num_rows="dynamic",
    key="csv_editor",
)
st.metric("Materials found", value=len(edited_df))  # Point out number of materials
working_df = edited_df.copy()


# Features & Operations
st.subheader("Operations")
ops_percentages, ops_fig_merge,  = st.tabs(
    ["Grab Percentages", "Merge Accords"]
)
with ops_percentages:
    amount_column = "Amount"  # Defaults to "Amount" column
    if st.button("Analyse"):
        try:
            working_df = compute_percentages(working_df, column=amount_column)
            st.success("Dataframe updated with Percentage column.")
            st.subheader("Updated Data")
            st.dataframe(working_df, use_container_width=True, hide_index=True)
            st.metric("Materials found", value=len(edited_df))  # Point out number of materials
            st.metric("Total Concentration", value=f"{compute_concentration(working_df):.2f}%")
        except ValueError as exc:
            st.error(str(exc))

with ops_fig_merge:
    st.subheader("Merge Accords")
    st.caption("Merge multiple accords into one accord.")
    st.info("This operation is not yet implemented.")
