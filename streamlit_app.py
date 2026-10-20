"""ShiftLens entry point.

    streamlit run streamlit_app.py  # replay UI
    python streamlit_app.py         # CLI dataset check, exit code 1 on errors
"""
import os
import sys

from matchpulse.validator import ROOT as _ROOT

try:  # optional: read a local, uncommitted .env; real environment variables always win
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env", override=False)
except ImportError:
    pass

from matchpulse.validator import CONFIG_PATH, DEFAULT_DATASET, ROOT, fingerprint, load_json, load_match, validate_config


def dataset_path() -> str:
    path = os.environ.get("MATCHPULSE_DATASET_PATH")
    return str(ROOT / path if path else DEFAULT_DATASET)


def check() -> tuple[str, list[str], str | None]:
    path = dataset_path()
    match, errors = load_match(path)
    errors += validate_config(load_json(CONFIG_PATH))
    return str(path), errors, (fingerprint(match) if match and not errors else None)


def main_cli() -> int:
    path, errors, digest = check()
    if errors:
        print(f"dataset INVALID: {path}")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"dataset valid: {path}\nfingerprint: {digest}")
    return 0


def _in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except ImportError:
        return False


if _in_streamlit():
    from matchpulse.ui import render

    render(dataset_path())
elif __name__ == "__main__":
    sys.exit(main_cli())
