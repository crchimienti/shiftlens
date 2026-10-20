import os

# Automated tests never call a real model: force offline before any app code reads the environment.
# (load_dotenv in streamlit_app.py does not override variables that are already set.)
os.environ["MATCHPULSE_OFFLINE"] = "1"
