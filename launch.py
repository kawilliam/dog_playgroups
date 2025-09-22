# launch.py — robust launcher for packaged Streamlit on Windows
import os, sys, os.path as p, webbrowser

BASE = getattr(sys, "_MEIPASS", p.abspath(p.dirname(__file__)))
APP  = p.join(BASE, "app.py")

# Neutralize any conflicting env
os.environ.pop("STREAMLIT_SERVER_PORT", None)
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"

# Optional: write logs to Documents\DogPlaygroupsData\logs\launch.log
from pathlib import Path
log_dir = Path.home() / "Documents" / "DogPlaygroupsData" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "launch.log"
sys.stdout = open(log_file, "a", encoding="utf-8", buffering=1)
sys.stderr = sys.stdout
print("Launching…")

from streamlit.web.cli import main as st_main

# Open the URL ourselves (helps when Streamlit can't auto-open)
url = "http://localhost:8505"
try:
    webbrowser.open(url)
except Exception as e:
    print("Browser open failed:", e)

sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--server.headless=false",
    "--server.port=8505",
]
st_main()

