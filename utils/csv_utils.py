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
        df = pd.read_csv(buffer, sep=separator, encoding=encoding)
        if len(df.columns) > 3:
            df = df[["Material", "Dilution", "Amount"]]
        return df
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
    diluents = []
    for material, p_value, d_value in zip(material_name, relative_percentages, dilution_values):
        if any(key.strip() == material.upper().strip() for key in SOLVENT_KEYWORDS):
            diluents.append(material)
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
    diluents = ', '.join(diluents) if diluents else "None"
    return total, diluents


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
        explicit_columns = re.fullmatch(
            r"(.+?)(?:\s*,\s*|\s+)(\d+(?:\.\d+)?%?)"
            r"(?:\s*,\s*|\s+)(\d+(?:\.\d+)?%?)",
            cleaned_line,
        )
        if explicit_columns:
            material, dilution, amount = explicit_columns.groups()
            rows.append([material, dilution.rstrip("%") + "%", amount.rstrip("%")])
            continue
        match = re.match(r"^(.*?)\s+((?:\d+\s*)+)$", cleaned_line)
        if not match:
            # combo pattern: numbers + numbers followed by %
            pattern = re.compile(r"^(.*?)\s+((?:\d+(?:\s*%|%)\s*)+|\b(?:\d+\s*)+)$")
            match = pattern.match(cleaned_line)
            if not match:
                pattern = re.compile(r'^(.*?)\s+((?:\d+(?:\.\d+)?(?:\s*%|%)\s*)+|\b(?:\d+(?:\.\d+)?\s*)+)$')
                match = pattern.match(cleaned_line)

        if match is None:
            raise ValueError(f"Could not parse formula line: {line!r}")
        groups = match.groups()

        if len(groups) < 3:
            if len(groups[1].split()) > 1:
                split_groups = groups[1].split()  # Check if the second group can be split into multiple parts
                # If it can be split, we assume the first part is the dilution and the second part is the amount
                if not split_groups[0].endswith("%"):
                    split_groups[0] = split_groups[0] + "%"
                groups = (groups[0], split_groups[0], split_groups[1])
            else: # case dilution is included in the material
                material = groups[0]
                if any(char.isdigit() for char in material) and "%" in groups[1]:
                    material = groups[0]
                    amount = re.findall(r"\d+(?=\s*)", groups[0])[0]
                    dilution = "100%"
                    # modify group information to escape last check
                    groups = (material, str(groups[1].replace("%", "")))
                elif any(char.isdigit() for char in material) and "%" in groups[0]:
                    material = re.sub(r"\d+(?=\s*%)%", "", groups[0]).strip()  # Remove the numerical part from the material
                    dilution = re.findall(r"\d+(?=\s*%)", groups[0])[0]  # Extract the numerical part as dilution
                    dilution = str(dilution) + "%"
                    amount = groups[1]
                else:
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
    df["Dilution"] = df["Dilution"].apply(lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x)
    return df

def merge_accords(parent_df: pd.DataFrame,
                  added_df:pd.DataFrame,
                  relative_factor: float,
                  parent_used_dilution: float) -> pd.DataFrame:
    """Expand a parts/100 accord, combining duplicates at the stronger dilution."""
    parent_df = parent_df.reset_index(drop=True).copy()
    parent_df["Amount"] = pd.to_numeric(parent_df["Amount"]).astype(float)
    parent_df["Dilution"] = parent_df["Dilution"].apply(
        lambda value: f"{float(str(value).rstrip('%'))}%"
    )
    for _, row in added_df.iterrows():
        added_material = row['Material']
        added_dilution_float = float(str(row['Dilution']).rstrip("%")) * parent_used_dilution
        added_amount = float(row['Amount']) * relative_factor
        existing_indices = parent_df.index[
            parent_df["Material"].str.upper() == added_material.upper()
        ]
        if len(existing_indices):
            existing_idx = existing_indices[0]
            existing_dilution_float = float(
                str(parent_df.at[existing_idx, 'Dilution']).rstrip("%")
            )
            existing_amount = parent_df.at[existing_idx, 'Amount']
            if existing_dilution_float == added_dilution_float:
                parent_df.at[existing_idx, 'Amount'] = existing_amount + added_amount
            else:
                max_dilution = max(existing_dilution_float, added_dilution_float)
                parent_df.at[existing_idx, 'Amount'] = (
                    existing_amount * existing_dilution_float
                    + added_amount * added_dilution_float
                ) / max_dilution
                parent_df.at[existing_idx, 'Dilution'] = f"{max_dilution}%"
        else:
            new_row = {
                "Material": added_material,
                "Dilution": f"{added_dilution_float}%",
                "Amount": added_amount,
            }
            if "" in parent_df.columns:
                new_row[""] = False
            parent_df = pd.concat([parent_df, pd.DataFrame([new_row])], ignore_index=True)

    return parent_df