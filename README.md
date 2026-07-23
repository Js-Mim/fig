# Fragrance(-formula) Information Grabber (FIG)
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
- Basic calculation of percentage (absolute / relative), and parts (/1000)


## Repository Layout

- `app.py`: main Streamlit app
- `pixi.toml`: Pixi environment onfiguration
- `pyproject.toml`: project metadata and optional linter config
- `.gitignore`: common Python and Streamlit ignores

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
