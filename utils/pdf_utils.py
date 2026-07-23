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
    
    # output list
    exported_formula = []

    with pdfplumber.open(pdf_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            # table = page.extract_table()

            # Split text into lines to avoid cross-line match contamination
            lines = text.strip().split('\n')

            for line in lines:
                match = re.match(pattern, line.strip())
                if match:
                    material, amount = match.groups()
                    material = material.replace('[', '').replace(']', '')  # Remove brackets from material name

                    try:
                        amount = float(amount) if '.' in amount else int(amount)
                        if amount <= 0 or amount > 1000 or material == "Total":  # Sanity check, accept max value in parts of a thousand
                            continue
                        else:
                            # check if material has dilution information
                            if any(char.isdigit() for char in material) and ('%' in material):
                                dilution_str_indices = re.search(r'\d+(?:\.\d+)?%$', material).span()
                                dilution = material[dilution_str_indices[0]:dilution_str_indices[1]]

                                # trim material name to remove dilution information
                                material = material[:dilution_str_indices[0]]
                            else:
                                dilution = "100%"
                            exported_formula.append((material, dilution, amount))
                    except ValueError:
                        continue  # Skip lines where amount is not a valid number
                
    return exported_formula

if __name__ == "__main__":


    print(grab_formula("./jany.pdf"))
    #print(text)