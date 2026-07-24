# imports
import csv
import io
import pandas as pd
import streamlit as st
from typing import Optional


@st.cache_data
def load_csv(file_bytes: bytes, separator: str, encoding: str) -> pd.DataFrame:
    buffer = io.BytesIO(file_bytes)
    return pd.read_csv(buffer, sep=separator, encoding=encoding)


def choose_filter_column(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None
    return st.selectbox("Column", options=list(df.columns), index=0)

def compute_percentages(df: pd.DataFrame,
                        column: str = "Amount") -> pd.DataFrame:
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found.")

    df = df.astype({'Amount': float})

    df_copy = df.copy()
    dilution_values = [0] * len(df["Dilution"])
    for idx, value in enumerate(df["Dilution"]):
        if isinstance(value, str) and value.endswith("%"):
            dilution_values[idx] = float(value.rstrip("%")) / 100.0
        else:
            dilution_values[idx] = float(value)
    numeric_values = pd.to_numeric(df_copy[column], errors="coerce")
    total = numeric_values.sum()
    if total == 0:
        raise ValueError(f"Total of column '{column}' is zero, cannot compute percentages.")

    # basic calculations
    df_copy["Percentage (Relative)"] = pd.Series((numeric_values / total) * 100., index=df_copy.index)
    df_copy["Percentage (Absolute)"] = pd.Series(df_copy["Percentage (Relative)"] * dilution_values, index=df_copy.index)
    df_copy["Parts (/1000)"] = pd.Series((numeric_values / total) * 1000, index=df_copy.index)
    # add percentage symbol
    df_copy["Percentage (Relative)"] = df_copy["Percentage (Relative)"].apply(lambda x: f"{x:.2f}%")
    df_copy["Percentage (Absolute)"] = df_copy["Percentage (Absolute)"].apply(lambda x: f"{x:.2f}%")
    return df_copy

def list_to_dataframe(data: list) -> pd.DataFrame:
    if not data:
        return pd.DataFrame(columns=["Material", "Dilution", "Amount"])
    return pd.DataFrame(data, columns=["Material", "Dilution", "Amount"])

def text_to_dataframe(text: str) -> pd.DataFrame:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return pd.DataFrame(columns=["Material", "Dilution", "Amount"])

    rows = []
    max_len = 0
    for line in lines:
        parsed = next(csv.reader([line], skipinitialspace=True))
        cleaned = [value.strip() for value in parsed]
        rows.append(cleaned)
        max_len = max(max_len, len(cleaned))

    if max_len == 3:
        columns = ["Material", "Dilution", "Amount"]
    else:
        columns = [f"Column {idx + 1}" for idx in range(max_len)]

    padded_rows = [row + [""] * (max_len - len(row)) for row in rows]
    
    df = pd.DataFrame(padded_rows, columns=columns)
    df = df.astype({'Amount': float})
    return df