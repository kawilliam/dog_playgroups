# launch.py – starts your Streamlit app from a bundled executable
import os, sys
# When frozen by PyInstaller, files live under _MEIPASS
BASE = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
APP = os.path.join(BASE, "app.py")

# Don’t phone home; pick a random free port
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_PORT", "0")

# Start Streamlit programmatically
from streamlit.web.cli import main as st_main  # Streamlit 1.20+
sys.argv = ["streamlit", "run", APP, "--server.headless=false"]
st_main()
