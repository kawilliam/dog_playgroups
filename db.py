import sqlite3
import pandas as pd

from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dogs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        plays_hard INTEGER DEFAULT 0,
        shy INTEGER DEFAULT 0,
        intact INTEGER DEFAULT 0,
        size TEXT DEFAULT 'M',
        notes TEXT,
        photo_path TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS relationships(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dog_a_id INTEGER NOT NULL,
        dog_b_id INTEGER NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('friend','foe','unknown')),
        UNIQUE(dog_a_id, dog_b_id),
        FOREIGN KEY(dog_a_id) REFERENCES dogs(id) ON DELETE CASCADE,
        FOREIGN KEY(dog_b_id) REFERENCES dogs(id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        date TEXT NOT NULL,
        slot TEXT NOT NULL,
        dog_id INTEGER NOT NULL,
        PRIMARY KEY(date, slot, dog_id),
        FOREIGN KEY(dog_id) REFERENCES dogs(id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS groups(
        date TEXT NOT NULL,
        slot TEXT NOT NULL,
        group_name TEXT NOT NULL,
        notes TEXT,
        PRIMARY KEY(date, slot, group_name)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS group_members(
        date TEXT NOT NULL,
        slot TEXT NOT NULL,
        group_name TEXT NOT NULL,
        dog_id INTEGER NOT NULL,
        PRIMARY KEY(date, slot, group_name, dog_id),
        FOREIGN KEY(dog_id) REFERENCES dogs(id) ON DELETE CASCADE
    )
    """)
    conn.commit()

def fetch_df(sql, params=()):
    return pd.read_sql_query(sql, get_conn(), params=params)
