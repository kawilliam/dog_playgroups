# launch.py — fully self-contained, no user steps required
import os
import sys
import os.path as p
import webbrowser
from pathlib import Path

BASE = getattr(sys, "_MEIPASS", p.abspath(p.dirname(__file__)))
APP = p.join(BASE, "app.py")
CFG = p.join(BASE, "streamlit_config.toml")
PORT = "8510"

log_dir = Path.home() / "Documents" / "DogPlaygroupsData" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "launch.log"
log_handle = open(log_file, "a", encoding="utf-8", buffering=1)
sys.stdout = log_handle
sys.stderr = log_handle

print("=== Launching Dog Playgroups ===")
print("BASE:", BASE)
print("APP exists:", p.exists(APP))
print("CFG exists:", p.exists(CFG))
print("Python:", sys.version)

usr_streamlit = Path.home() / ".streamlit"
usr_streamlit.mkdir(parents=True, exist_ok=True)

cred_path = usr_streamlit / "credentials.toml"
if not cred_path.exists():
    cred_path.write_text("[general]\nemail = \"\"\n", encoding="utf-8")
    print("Created credentials.toml to disable onboarding prompt.")

cfg_user = usr_streamlit / "config.toml"
if not cfg_user.exists():
    cfg_user.write_text(
        "[global]\n"
        "developmentMode = false\n\n"
        "[browser]\n"
        "gatherUsageStats = false\n",
        encoding="utf-8"
    )
    print("Created user config.toml to disable telemetry.")

os.environ["STREAMLIT_CONFIG_FILE"] = CFG
os.environ.pop("STREAMLIT_SERVER_PORT", None)
os.environ["STREAMLIT_GLOBAL_DEVELOPMENTMODE"] = "false"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

url = f"http://localhost:{PORT}"
try:
    webbrowser.open(url)
    print("Opening:", url)
except Exception as exc:
    print("Browser open failed:", exc)

from streamlit.web.cli import main as st_main
sys.argv = ["streamlit", "run", APP]
print("Args:", sys.argv)

try:
    st_main()
except Exception as exc:
    print("Streamlit exited with error:", exc)
    raise
finally:
    log_handle.flush()
