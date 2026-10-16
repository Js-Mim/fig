import math
import re
import unicodedata
import pandas as pd
from pathlib import Path

# defs
STANDARD_NAME = "Name of the IFRA Standard"
LIMIT = "Category 4 (%)"
NCS_NAME = "NCS NAME"
BOTANICAL_NAME = "NCS BOTANICAL NAME"
CONSTITUENT = "CONSTITUENT NAME (IFRA STANDARD)"
NCS_CONCENTRATION = "CONCENTRATION OF CONSTITUENT IN NATURALS (NCS) (%)"
ASSETS = Path(__file__).resolve().parents[1] / "assets"
EXPLANATORY_NOTE = re.compile(
    r"\s*\((?:commercial name|mixture of isomers|mixed isomers|isomer mixture|"
    r"including all geometric isomers|isomer unspecified|unspecified isomer)\)",
    re.IGNORECASE,
)


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\u200b", "")
    value = value.translate(str.maketrans({"\u2010": "-", "\u2011": "-", "\u2013": "-"}))
    return " ".join(EXPLANATORY_NOTE.sub("", value).casefold().split())


def load_ifra_tables(assets_dir: Path = ASSETS) -> tuple[pd.DataFrame, pd.DataFrame]:
    standards = pd.read_excel(
        assets_dir / "ifra-51st-amendment-ifra-standards-overview.xlsx", header=2
    )
    naturals = pd.read_excel(
        assets_dir / "ifra-51st-amendment-annex-on-contributions-from-other-sources.xlsx",
        sheet_name="Natural contributions",
        header=6,
    )
    _require_columns(standards, [STANDARD_NAME, "Synonyms", LIMIT], "IFRA standards")
    _require_columns(
        naturals, [NCS_NAME, BOTANICAL_NAME, CONSTITUENT, NCS_CONCENTRATION],
        "Natural contributions",
    )
    return standards, naturals


def _require_columns(table: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = set(columns) - set(table.columns)
    if missing:
        raise ValueError(f"{label} is missing columns: {', '.join(sorted(missing))}")


def _aliases(value) -> list[str]:
    if pd.isna(value):
        return []
    return [normalize_name(name) for name in str(value).splitlines() if name.strip()]


def _percentage(value) -> float:
    text = str(value).strip().removesuffix("%").strip().replace(",", ".")
    if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
        raise ValueError(f"Not a plain numeric percentage: {value!r}")
    number = float(text)
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError(f"Percentage must be between 0 and 100: {value!r}")
    return number


def _absolute_percentages(formula: pd.DataFrame) -> pd.Series:
    _require_columns(formula, ["Material", "Dilution", "Amount"], "Formula")
    amounts = pd.to_numeric(formula["Amount"], errors="raise").astype(float)
    if (
        formula.empty or not amounts.map(math.isfinite).all()
        or (amounts < 0).any() or not math.isfinite(amounts.sum()) or amounts.sum() <= 0
    ):
        raise ValueError("Formula amounts must be finite, nonnegative, and have a positive total.")
    dilutions = formula["Dilution"]
    # Match the workbench's numeric dilution convention (fractions or percent values).
    numeric = pd.to_numeric(dilutions, errors="coerce")
    numeric_is_fraction = numeric.notna().all() and numeric.mean() <= 1
    dilution_percentages = dilutions.map(_percentage)
    if numeric_is_fraction:
        dilution_percentages *= 100
    if (dilution_percentages > 100).any():
        raise ValueError("Formula dilutions must not exceed 100%.")
    return amounts / amounts.sum() * dilution_percentages


def scan_ifra(
    formula: pd.DataFrame, standards: pd.DataFrame, naturals: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare finished-product absolute percentages with the supplied Category 4 data."""
    _require_columns(standards, [STANDARD_NAME, "Synonyms", LIMIT], "IFRA standards")
    _require_columns(
        naturals, [NCS_NAME, BOTANICAL_NAME, CONSTITUENT, NCS_CONCENTRATION],
        "Natural contributions",
    )
    standards = standards.reset_index(drop=True)
    naturals = naturals.reset_index(drop=True)
    absolute = _absolute_percentages(formula)
    standard_index: dict[str, set[int]] = {}
    natural_index: dict[str, set[int]] = {}
    for idx, row in standards.iterrows():
        for name in _aliases(row[STANDARD_NAME]) + _aliases(row["Synonyms"]):
            standard_index.setdefault(name, set()).add(idx)
    for idx, row in naturals.iterrows():
        for name in _aliases(row[NCS_NAME]) + _aliases(row[BOTANICAL_NAME]):
            natural_index.setdefault(name, set()).add(idx)

    contributions = []
    issues = []
    totals: dict[int, float] = {}

    def issue(material, reason):
        issues.append({"Material": material, "Issue": reason})

    def contribute(material, material_absolute, constituent, concentration, matches, source):
        if len(matches) > 1:
            issue(material, f"Multiple standards match {constituent!r}; all are shown for review.")
        for idx in sorted(matches):
            amount = material_absolute * concentration / 100
            totals[idx] = totals.get(idx, 0.0) + amount
            contributions.append({
                "Material": material,
                "Absolute Percentage (%)": material_absolute,
                "Match": source,
                "Constituent": constituent,
                "Constituent in natural (%)": concentration if source == "Natural" else None,
                STANDARD_NAME: standards.at[idx, STANDARD_NAME],
                "Contribution (%)": amount,
            })

    for (_, row), material_absolute in zip(formula.iterrows(), absolute):
        material = row["Material"]
        if not isinstance(material, str) or not material.strip():
            raise ValueError("Every formula row must have a nonempty material name.")
        name = normalize_name(material)
        direct = standard_index.get(name, set())
        if direct:
            contribute(material, material_absolute, material, 100, direct, "Direct")
            continue
        natural_matches = natural_index.get(name, set())
        if not natural_matches:
            issue(material, "Not found in either workbook; not assessed.")
            continue
        natural_rows = naturals.loc[sorted(natural_matches)]
        identities = {normalize_name(str(value)) for value in natural_rows[NCS_NAME]}
        if len(identities) > 1:
            issue(
                material,
                "Botanical name matches multiple natural materials; use an exact NCS NAME: "
                + "; ".join(sorted(set(natural_rows[NCS_NAME].astype(str)))),
            )
            continue
        natural_rows = naturals[
            naturals[NCS_NAME].map(lambda value: normalize_name(str(value))).isin(identities)
        ]
        for constituent, group in natural_rows.groupby(CONSTITUENT, dropna=False):
            if not isinstance(constituent, str) or not constituent.strip():
                issue(material, "Natural record has no constituent name; not assessed.")
                continue
            try:
                concentrations = {_percentage(value) for value in group[NCS_CONCENTRATION]}
            except ValueError as exc:
                issue(material, f"{constituent}: {exc}; contribution not assessed.")
                continue
            if len(concentrations) != 1:
                issue(material, f"{constituent}: conflicting natural concentrations; not assessed.")
                continue
            matches = standard_index.get(normalize_name(constituent), set())
            if not matches:
                issue(
                    material, f"Constituent {constituent!r} not found in standards; not assessed."
                )
                continue
            contribute(
                material, material_absolute, constituent, concentrations.pop(), matches, "Natural"
            )

    summary = []
    for idx, total in totals.items():
        row = standards.loc[idx]
        raw_limit = row[LIMIT]
        standard_type = str(row.get("IFRA Standard type", "")).strip()
        limit = None
        status = "Manual review required"
        if pd.isna(raw_limit) and standard_type in {"PROHIBITION", "PROHIBITION_SPECIFICATION"}:
            limit = 0.0
            status = "Prohibited" if total > 0 else "No contribution"
        elif isinstance(raw_limit, str) and raw_limit.strip().casefold() == "no restriction":
            status = "No Category 4 restriction listed"
        else:
            try:
                limit = _percentage(raw_limit)
            except ValueError:
                status = "Manual review required"
            else:
                if math.isclose(total, limit, rel_tol=1e-12, abs_tol=1e-12):
                    status = "At limit"
                else:
                    status = "Above limit" if total > limit else "Below limit"
        notes = [
            str(row[column]) for column in [
                "Prohibited fragrance ingredients: notes",
                "Restricted ingredients due to phototoxicity considerations: notes",
                "Restricted ingredients: notes", "Specified ingredients: notes",
                "Contributions from other sources: notes",
            ] if column in row.index and pd.notna(row[column])
        ]
        summary.append({
            STANDARD_NAME: row[STANDARD_NAME],
            "Total Absolute Percentage (%)": total,
            LIMIT: limit,
            "Headroom (percentage points)": None if limit is None else limit - total,
            "Limit used (%)": None if limit in (None, 0) else total / limit * 100,
            "Status": status,
            "Category 4 entry": "" if pd.isna(raw_limit) else str(raw_limit),
            "Standard type": standard_type,
            "Standard notes": "\n".join(notes),
        })
    return (
        pd.DataFrame(summary, columns=[
            STANDARD_NAME, "Total Absolute Percentage (%)", LIMIT,
            "Headroom (percentage points)", "Limit used (%)", "Status",
            "Category 4 entry", "Standard type", "Standard notes",
        ]),
        pd.DataFrame(contributions, columns=[
            "Material", "Absolute Percentage (%)", "Match", "Constituent",
            "Constituent in natural (%)", STANDARD_NAME, "Contribution (%)",
        ]),
        pd.DataFrame(issues, columns=["Material", "Issue"]),
    )
