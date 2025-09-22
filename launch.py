# launch.py — robust launcher for packaged Streamlit on Windows
import os
import sys
import os.path as p
import webbrowser
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
    print("Using bundled config:", CONFIG)

os.environ.pop("STREAMLIT_SERVER_PORT", None)
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

try:
    cfg_dir = Path.home() / ".streamlit"
    cfg_dir.mkdir(exist_ok=True)
    cfg_path = cfg_dir / "config.toml"
    if not cfg_path.exists():
        cfg_path.write_text(
            "[global]\n"
            "developmentMode = false\n\n"
            "[browser]\n"
            "gatherUsageStats = false\n",
            encoding="utf-8"
        )
        print("Created user config to disable onboarding prompts.")
except Exception as exc:
    print("Config write skipped:", exc)

PORT = "8510"
url = f"http://localhost:{PORT}"
try:
    webbrowser.open(url)
    print("Opening:", url)
except Exception as exc:
    print("Browser open failed:", exc)

try:
    from streamlit.web.cli import main as st_main
except Exception as exc:
    print("Streamlit import failed:", exc)
    raise

sys.argv = [
    "streamlit", "run", APP,
    "--global.developmentMode=false",
    "--browser.gatherUsageStats=false",
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
