# Microlearning v2

This project extracts content from PDF files into Markdown while preserving associated images. It is driven by `scripts/extraction/main.py` and uses environment variables defined in `scripts/config/settings.py`.

## Installation

1. Create and activate a Python 3 virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. Install the required packages:
   ```bash
   pip install python-dotenv google-generativeai PyMuPDF Pillow numpy tenacity langsmith PyYAML
   ```
   You can run `python scripts/extraction/main.py --check-deps` to verify that all dependencies are available.

## Environment Variables

`scripts/config/settings.py` loads the following variables from a `.env` file located in the project root or from the environment:

- `GEMINI_API_KEY` – Google Generative AI API key.
- `LANGSMITH_API_KEY` – API key for LangSmith.
- `LANGSMITH_PROJECT` – project name used by LangSmith (defaults to `microlearning-extraction`).
- `LANGSMITH_ENDPOINT` – LangSmith API endpoint (defaults to `https://api.smith.langchain.com`).
- `LANGSMITH_TRACING_V2` – set to `true` to enable tracing.
- `LANGSMITH_DEBUG` – set to `true` for verbose LangSmith logging.

Example lines from `settings.py`:
```python
ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))
load_dotenv(ENV_PATH)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
```

## Example Usage

After configuring the environment variables and installing the dependencies, a single PDF can be processed with:
```bash
python scripts/extraction/main.py --file path/to/file.pdf --log-level INFO
```
The script also accepts options such as `--dir` to process a directory of PDFs.
