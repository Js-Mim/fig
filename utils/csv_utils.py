# imports
import re
import io
import pandas as pd
import streamlit as st
from typing import Optional

# defs
SOLVENT_KEYWORDS = ["IPM", "TEC", "DEP", "DPG", "MCT",
                    "DIETHYL PHTALATE", "DIETHYL PHTALATE DILUENT",
                    "ISO-PROPYL MYRISTATE", "ISO-PROPYL MYRISTATE DILUENT",
                    "ISOPROPYL MYRISTATE", "ISOPROPYL MYRISTATE DILUENT",
                    "TRIETHYL CITRATE", "TRIETHYL CITRATE DILUENT",
                    "DIPROPYLENE GLYCOL", "DIPROPYLENE GLYCOL DILUENT",
                    "MCT OIL",
                    "SOLVENT",
                    "ETHANOL", "ETOH", 
                    "CARRIER", "DILUENT"]


@st.cache_data
def load_csv(file_bytes: bytes, separator: str, encoding: str) -> pd.DataFrame:
    buffer = io.BytesIO(file_bytes)
    # check if default columns exist
    first_line = buffer.readline().decode(encoding).strip()
    has_header = "Material" in first_line and "Dilution" in first_line and "Amount" in first_line
    if has_header:
        buffer.seek(0)  # Reset buffer position to the beginning
        return pd.read_csv(buffer, sep=separator, encoding=encoding)
    else:
        buffer.seek(0)
        df = pd.read_csv(buffer, sep=separator, encoding=encoding, header=None)
        df.columns = ["Material", "Dilution", "Amount"]  # Assign default column names
        return df


def choose_filter_column(df: pd.DataFrame) -> Optional[str]:
    if df.empty:
        return None
    return st.selectbox("Column", options=list(df.columns), index=0)

def compute_concentration(df: pd.DataFrame) -> float:
    if "Percentage (Relative)" not in df.columns:
        raise ValueError(f"Column 'Percentage (Relative)' not found.")
    material_name = df["Material"].tolist()
    relative_percentages = df["Percentage (Relative)"]
    dilution_values = df["Dilution"]
    total = 0
    for material, p_value, d_value in zip(material_name, relative_percentages, dilution_values):
        if any(key.strip() == material.upper().strip() for key in SOLVENT_KEYWORDS):
            continue  # Skip solvent materials
        else:
            p_value_check = isinstance(p_value, str) and p_value.endswith("%")
            d_value_check = isinstance(d_value, str) and d_value.endswith("%")
            if p_value_check and d_value_check:
                dilution_values = float(d_value.rstrip("%")) / 100.0
                percentage_values = float(p_value.rstrip("%")) / 100.0
                total += percentage_values * dilution_values  # how much was used in the formula x the dilution
            else:
                raise ValueError(f"Invalid values. Expected a string ending with '%'.")
                
    total = total * 100  # convert back to percentage
    return total


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
            sum = pd.to_numeric(df["Dilution"]).mean()
            if sum > 1:  # in case the "%" sign is missing
                dilution_values[idx] = float(value) / 100.0
            else:  # in case the dilution in the formula is already in decimal form
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
    try:
        df_copy["Dilution"] = df_copy["Dilution"].apply(lambda x: f"{x:.1f}%")
    except ValueError:
        pass # it's already in string format with "%"
    df_copy["Percentage (Relative)"] = df_copy["Percentage (Relative)"].apply(lambda x: f"{x:.3f}%")
    df_copy["Percentage (Absolute)"] = df_copy["Percentage (Absolute)"].apply(lambda x: f"{x:.6f}%")
    return df_copy

def list_to_dataframe(data: list) -> pd.DataFrame:
    if not data:
        return pd.DataFrame(columns=["Material", "Dilution", "Amount"])
    return pd.DataFrame(data, columns=["Material", "Dilution", "Amount"])

def text_to_dataframe(text: str) -> pd.DataFrame:
    lines = text.strip().split('\n')
    if not lines:
        return pd.DataFrame(columns=["Material", "Dilution", "Amount"])
    
    rows = []
    for line in lines:
        cleaned_line = re.sub(r'[\s.,]{2,}', ' ', line).strip()
        # remove any brackets
        cleaned_line = re.sub(r'[\[\]\(\)\{\}]', '', cleaned_line)
        match = re.match(r"^(.*?)\s+((?:\d+\s*)+)$", cleaned_line)
        if not match:
            # combo pattern: numbers + numbers followed by %
            pattern = re.compile(r"^(.*?)\s+((?:\d+(?:\s*%|%)\s*)+|\b(?:\d+\s*)+)$")
            match = pattern.match(cleaned_line)
        groups = match.groups()
        
        if len(groups) < 3:
            # case dilution is included in the material
            material = groups[0]
            dilution = "100%"
            amount = groups[1]
            if "%" in groups[0]:
                dilution = re.findall(r"\d+(?=\s*%)", groups[0])[0] # neglect additional numerical information
                dilution = str(dilution) + "%"
                material = groups[0]
                # case that amount is written in percentage
            if groups[1].endswith("%"):
                amount = groups[1][:-1]  # Remove the trailing '%' from the second group

            groups = (material, dilution, amount)

        rows.append(list(groups))

    df = pd.DataFrame(rows, columns=['Material', 'Dilution', 'Amount'])
    df = df.astype({'Amount': float})
    return df