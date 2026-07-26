# imports
import math
import pandas as pd

# defs
Q_THREHSOLD = 0.015

def calculate_batch_amount(df: pd.DataFrame, batch_amount: float) -> tuple[pd.Series, pd.Series]:
    if "Percentage (Relative)" not in df.columns or "Dilution" not in df.columns:
        raise ValueError("Necessary columns were not found in the DataFrame. Please compute percentages and dilution(s) first.")
    if batch_amount <= 0:
        raise ValueError("Batch amount must be greater than zero.")

    dilution_series = df["Dilution"].copy()
    amount_series = df["Percentage (Relative)"].copy().apply(lambda x: (float(x.rstrip("%")) / 100.0))
    for index, element in enumerate(amount_series):
        output_amount = element * batch_amount
        if output_amount < Q_THREHSOLD:
            print(df["Material"].iloc[index], "is below the threshold. Adjusting amount and dilution.")
            leading_decimals = math.ceil(abs(math.log10(output_amount))) - 1 # Calculate the number of leading decimal

            if leading_decimals > 1:
                output_amount = output_amount * (10.0 ** (leading_decimals - 1))
                dilution_amount = str(float(df.at[index, "Dilution"].rstrip("%")) / (10.0 ** (leading_decimals-1))) + "%"
                dilution_series[index] = dilution_amount
            else:
                output_amount = output_amount * 2.0
                dilution_amount = str(float(df.at[index, "Dilution"].rstrip("%")) / (2.0)) + "%"
                dilution_series[index] = dilution_amount

        amount_series[index] = output_amount 

    if amount_series.sum() > batch_amount:
        scale_factor = batch_amount / amount_series.sum()
        print(f"Scaling down amounts by factor of {scale_factor:.4f} to match the desired batch amount.")
        amount_series *= scale_factor
    
    return amount_series, dilution_series