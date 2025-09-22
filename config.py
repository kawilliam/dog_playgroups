import os
import sys
from pathlib import Path


def get_data_dir() -> Path:
    """Return the directory where runtime data (db, images) should live."""
    if getattr(sys, "frozen", False):
        base = Path.home() / "Documents" / "DogPlaygroupsData"
    else:
        base = Path(__file__).resolve().parent
    base.mkdir(parents=True, exist_ok=True)
    return base


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = get_data_dir()
DB_PATH = str(DATA_DIR / "dogs.db")
IMAGES_DIR = str(DATA_DIR / "images")
Path(IMAGES_DIR).mkdir(parents=True, exist_ok=True)
