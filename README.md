# Fragrance(-formula) Information Grabber (FIG)
<p align="center">
    <img src="./assets/fig.png" alt="drawing" width="300"/>
</p>

You just discovered FIG! A python-based repository for grabbing and displaying information from fragrance-related formulas. Built for personal use, based on everyday-hobbyist needs.


# Install
## Pixi Quick Start
1. Install Pixi (if needed).

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```
or
```bash
wget -qO- https://pixi.sh/install.sh | sh
```

In case pixi is not found after restarting your terminal session, consider doing the following:

```bash
echo 'export PATH="$HOME/.pixi/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```
or
```bash
echo 'export PATH="$HOME/.pixi/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```


2. Start the app with Pixi (creates environment automatically).

```bash
pixi run start
```

If that is the first time using the repository, it may take a while to install the required dependencies.

3. Open the local URL shown by Streamlit (most commonly http://localhost:8501).

## Implemented Features

- Formula grabbing from CSV, PDF, and text input
- Basic formula editing
- Basic calculation of percentage (absolute / relative), parts (/1000), and total concentration
- Interactive batch preparation for trialing
- FIG Merge: replace a selected material with an accord

## Testing FIG Merge

Both the parent formula and the accord are assumed to use parts/100 (each totals 100).
For example, enter this parent formula in the sidebar text input:

```text
Base A 100% 40
Accord 100% 20
Base B 100% 40
```

Select the checkbox beside `Accord` in Preview & Edit, open FIG Merge, and enter:

```text
New A 100% 60
New B 100% 40
```

The result contains Base A = 40, Base B = 40, New A = 12, and New B = 8.
The selected row's dilution also multiplies each accord component's dilution.
Material names match case-insensitively. Matching materials at the same dilution
have their amounts added; at different dilutions they are combined at the stronger
dilution, preserving active-material quantity. In that case the total parts can
decrease; no compensating solvent is added.

Run the helper and Streamlit UI regression tests in the Pixi environment:

```bash
pixi run python -m unittest discover -s tests -v
```

## Repository Layout

- `app.py`: main Streamlit app
- `pixi.toml`: Pixi environment onfiguration
- `pyproject.toml`: project metadata and optional linter config
- `.gitignore`: common Python and Streamlit ignores

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
