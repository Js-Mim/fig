# imports
import streamlit as st
from utils import *

# Headline & Title
st.set_page_config(page_title="FIG-Workbench", layout="wide")
st.title("FIGbench")
st.caption("Upload your CSV including the materials and select an operation to proceed.")

# Upload Sidebar
with st.sidebar:
    st.header("CSV Input")
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    separator = "," #st.text_input("Separator", value=",", max_chars=1)
    encoding = "utf-8" #st.text_input("Encoding", value="utf-8")
    st.header("Text Input")
    formula_text = st.text_area(
        "Add formula line by line, and comma-separate the values. For example:\n"
        "'Vetiver Haiti, 10%, 1.5', new line 'Rose Absolute, 1%, 0.5', etc.",
        height=120,
    )

if not uploaded_file and not formula_text.strip():
    st.info("Upload a CSV file or type your formula inside the Text Input to start.")
    st.stop()


if uploaded_file:
    try:
        raw_bytes = uploaded_file.getvalue()
        dataframe = load_csv(raw_bytes, separator=separator, encoding=encoding)
    except Exception as exc:  # pragma: no cover - runtime UI path
        st.error(f"Failed to read CSV: {exc}")
        st.stop()
else:
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
    st.subheader("Grab Percentages")
    amount_column = st.selectbox(
        "Amount column",
        options=list(working_df.columns),
        index=list(working_df.columns).index("Amount") if "Amount" in working_df.columns else 0,
    )
    if st.button("Apply percentage calculation"):
        try:
            working_df = compute_percentages(working_df, column=amount_column)
            st.success("Dataframe updated with Percentage column.")
        except ValueError as exc:
            st.error(str(exc))
    if st.button("Consider dilution"):
        try:
            working_df = compute_percentages(working_df, column=amount_column, consider_dilution=True)
            st.success("Dataframe updated with Percentage column considering dilution.")
        except ValueError as exc:
            st.error(str(exc))


with ops_fig_merge:
    st.subheader("Merge Accords")
    st.caption("Merge multiple accords into one accord.")
    st.info("This operation is not yet implemented.")

st.subheader("Updated Data")
st.dataframe(working_df, use_container_width=True, hide_index=True)

csv_out = working_df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download edited file",
    data=csv_out,
    file_name="processed_data.csv",
    mime="text/csv",
)



