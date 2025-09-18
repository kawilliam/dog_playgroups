import os

APP_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(APP_DIR, "dogs.db")
IMAGES_DIR = os.path.join(APP_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)
