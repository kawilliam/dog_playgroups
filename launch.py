# launch.py – starts your Streamlit app from a bundled executable
import os, sys

BASE = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
APP = os.path.join(BASE, "app.py")

os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"

from streamlit.web.cli import main as st_main

sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--server.headless=false",
    "--server.port=0",
]
st_main()
