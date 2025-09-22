# launch.py — robust launcher with logging
import os, sys, os.path as p, webbrowser
from pathlib import Path

BASE = getattr(sys, "_MEIPASS", p.abspath(p.dirname(__file__)))
APP = p.join(BASE, "app.py")
CONFIG = p.join(BASE, "streamlit_config.toml")

log_dir = Path.home() / "Documents" / "DogPlaygroupsData" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "launch.log"
log_handle = open(log_file, "a", encoding="utf-8", buffering=1)
sys.stdout = log_handle
sys.stderr = log_handle

print("=== Launching Dog Playgroups ===")
print("BASE:", BASE)
print("APP exists:", p.exists(APP))
print("Python:", sys.version)

if p.exists(CONFIG):
    os.environ["STREAMLIT_CONFIG_FILE"] = CONFIG
    print("Using config:", CONFIG)

os.environ.pop("STREAMLIT_SERVER_PORT", None)
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"

PORT = "8510"
url = f"http://localhost:{PORT}"
try:
    webbrowser.open(url)
    print("Opening:", url)
except Exception as e:
    print("Browser open failed:", e)

try:
    from streamlit.web.cli import main as st_main
except Exception as exc:
    print("Streamlit import failed:", exc)
    raise

sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--server.headless=false",
    f"--server.port={PORT}",
]
print("Args:", sys.argv)

try:
    st_main()
except Exception as exc:
    print("Streamlit exited with error:", exc)
    raise
finally:
    log_handle.flush()
