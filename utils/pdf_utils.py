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
    multi_amount_pattern = r"^(.+?)\s+(\d+(?:\.\d+)?%?)\s+(\d+(?:\.\d+)?%?)$"
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
                line = re.sub(cas_number_pattern, '', line).strip().replace('Mixture', '')
                # Massage the line to remove code numbers
                line = re.sub(r"\b\d{4,}\b\s*", "", line).strip()
                match = re.match(pattern, line)

                if match:
                    # check for multiple amount columns
                    material, amount = match.groups()
                    material = re.sub(r'\d+\.\d+', '', material)
                    # double check for amount leaking in the material name
                    if len(re.findall(r'\d+(?:\.\d+)?', material)) > 1:
                        match = re.match(multi_amount_pattern, line)
                        material, _, amount = match.groups()
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
                                pattern_search = re.search(r'\d+(?:\.\d+)?%', material)
                                if pattern_search:
                                    dilution_str_indices = pattern_search.span()
                                    dilution = material[dilution_str_indices[0]:dilution_str_indices[1]]
                                    material = material[:dilution_str_indices[0]]
                                else:
                                    continue  # Skip if no valid dilution found
                                
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

                
def _correct_groups_for_mutiple_amounts(material: str, amount: str) -> tuple:
    numbers_in_material = re.findall(r"\d+\.\d+(?!\s*%)|\d+(?!\s*%)", material)
    
    if "%" in material:
        if len(numbers_in_material) > 1:
            numbers_in_amount = re.findall(r"\d+\.\d+|\d+", amount)
            flags = []
            for num in numbers_in_material:
                for n in numbers_in_amount:
                    float_div = float(n) / float(num)
                    if (float_div) == 10 or (float_div) == 100 or (float_div) == 1000:
                        flags.append(True)
            if all(flags):
                material = re.sub(r"\d+\.\d+|\d+", "", material).strip()  # Remove all numbers from material

    return material, amount # If there's a percentage in the material, we assume it's correct