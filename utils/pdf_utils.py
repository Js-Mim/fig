# imports
import re
import pdfplumber


def grab_formula(pdf_bytes: bytes) -> list:
    # Regex patterns:
    # ^(.+?)          -> Ingredient name match
    # \s+             -> Spacing match
    # (\d+(?:\.\d+)?) -> Amount match (integer or decimal)
    # $               -> Number at the end
    pattern = r"^(.+?)\s+(\d+(?:\.\d+)?%?)$"
    cas_number_pattern = r'\b\d+(?:-\d+)+\b'
    bakedin_solvent_pattern = r"\d+\.?\d*\s*(?:IPM|TEC|DPG)"
    
    # output list
    exported_formula = []

    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            # Split text into lines to avoid cross-line match contamination
            lines = text.strip().split('\n')

            for line in lines:
                # pass 1: Check for CAS number and skip if found
                line = re.sub(cas_number_pattern, '', line).strip()
                match = re.match(pattern, line)
                if match:
                    material, amount = match.groups()
                    material = material.replace('[', '').replace(']', '')  # Remove brackets from material name
                    try:
                        amount = float(amount) if '.' in amount else int(amount)
                        if amount <= 0 or amount > 1000 or material.upper() == "TOTAL":  # Sanity check, accept max value in parts of a thousand
                            continue
                        else:
                            # check if material has dilution information (two conventions: either a percentage at the end of the material name or a baked solvent)
                            solvent_case1 = any(char.isdigit() for char in material) and ('%' in material)
                            solvent_case2 = re.search(bakedin_solvent_pattern, material)
                            if solvent_case1:
                                pattern_search = re.search(r'\d+(?:\.\d+)?%$', material)
                                if pattern_search:
                                    dilution_str_indices = pattern_search.span()
                                    dilution = material[dilution_str_indices[0]:dilution_str_indices[1]]
                                else:
                                    continue  # Skip if no valid dilution information is found

                                # trim material name to remove dilution information
                                material = material[:dilution_str_indices[0]]
                            elif solvent_case2:
                                search_indices = solvent_case2.span()
                                dilution = material[search_indices[0]:search_indices[1]]
                                dilution = re.findall(r'\b\d+\b', dilution)[0] + '%'
                            else:
                                dilution = "100%"
                            exported_formula.append((material, dilution, amount))
                    except ValueError:
                        continue  # Skip lines where amount is not a valid number

    return exported_formula