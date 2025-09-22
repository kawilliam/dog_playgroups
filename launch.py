# launch.py — packaged launcher for Streamlit
import os, sys, os.path as p

BASE = getattr(sys, "_MEIPASS", p.abspath(p.dirname(__file__)))
APP = p.join(BASE, "app.py")

os.environ.pop("STREAMLIT_SERVER_PORT", None)

os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"

from streamlit.web.cli import main as st_main

sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--server.headless=false",
]
st_main()
