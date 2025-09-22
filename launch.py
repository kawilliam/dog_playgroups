# launch.py – starts your Streamlit app from a bundled executable
import os, sys, os.path as p

BASE = getattr(sys, "_MEIPASS", p.abspath(p.dirname(__file__)))
APP  = p.join(BASE, "app.py")

os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"  # ensure not in dev mode

from streamlit.web.cli import main as st_main
sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--server.headless=false",
]
st_main()
