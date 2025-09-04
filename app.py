import os
import sqlite3
from itertools import combinations
from datetime import date
import pandas as pd
import streamlit as st

# --- Paths ---
APP_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(APP_DIR, "dogs.db")
IMAGES_DIR = os.path.join(APP_DIR, "images")
os.makedirs(IMAGES_DIR, exist_ok=True)

# --- DB helpers ---
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

def upsert_relationship(a_id, b_id, status):
    if a_id == b_id:
        return
    a, b = sorted([a_id, b_id])
    conn = get_conn()
    conn.execute(
        "INSERT INTO relationships(dog_a_id,dog_b_id,status) VALUES(?,?,?) "
        "ON CONFLICT(dog_a_id,dog_b_id) DO UPDATE SET status=excluded.status",
        (a, b, status)
    )
    conn.commit()

def get_relationship(a_id, b_id):
    if a_id == b_id:
        return "friend"
    a, b = sorted([a_id, b_id])
    cur = get_conn().execute(
        "SELECT status FROM relationships WHERE dog_a_id=? AND dog_b_id=?",
        (a, b)
    )
    row = cur.fetchone()
    return row[0] if row else "unknown"

# --- Grouping rules ---
def allowed_pair(a_id, b_id, rules, status, attrs):
    # relationship
    if status == "foe":
        return False
    if status == "unknown" and not rules["allow_unknown"]:
        return False

    # attributes
    ah, ashy, ai, asize = attrs[a_id]
    bh, bshy, bi, bsize = attrs[b_id]
    if rules["separate_hard_shy"] and ((ah and bshy) or (bh and ashy)):
        return False
    if rules["separate_intact"] and ai and bi:
        return False
    if rules["same_size_only"] and asize != bsize:
        return False
    return True

def suggest_groups(dog_ids, rules, target_size):
    if not dog_ids:
        return [], []

    # attributes map: id -> (plays_hard, shy, intact, size)
    df = fetch_df(
        "SELECT id, plays_hard, shy, intact, size FROM dogs WHERE id IN ({})"
        .format(",".join("?" * len(dog_ids))),
        dog_ids
    )
    attrs = {
        int(r.id): (bool(r.plays_hard), bool(r.shy), bool(r.intact), (r.size or "M"))
        for _, r in df.iterrows()
    }

    # cache relationship lookups
    rel_cache = {}
    def rel(a,b):
        key = tuple(sorted((a,b)))
        if key not in rel_cache:
            rel_cache[key] = get_relationship(a,b)
        return rel_cache[key]

    remaining = set(dog_ids)
    groups, leftovers = [], []

    def compatibility_score(cand, group):
        # prefer friends, then unknowns
        score = 0
        for g in group:
            s = rel(cand, g)
            score += 2 if s == "friend" else (1 if s == "unknown" else -999)
        return score

    while remaining:
        seed = remaining.pop()
        group = [seed]

        # try to add best-compatible until cap
        while len(group) < target_size:
            best = None
            best_score = -10
            for cand in list(remaining):
                if all(allowed_pair(cand, g, rules, rel(cand, g), attrs) for g in group):
                    sc = compatibility_score(cand, group)
                    if sc > best_score:
                        best = cand
                        best_score = sc
            if best is None:
                break
            group.append(best)
            remaining.remove(best)

        # validate full compatibility
        fully_ok = all(
            allowed_pair(a, b, rules, rel(a, b), attrs) for a, b in combinations(group, 2)
        )
        if fully_ok and len(group) > 1:
            statuses = [rel(a,b) for a,b in combinations(group,2)]
            groups.append({
                "dogs": group,
                "status": "Needs Intro" if any(s == "unknown" for s in statuses) else "Safe"
            })
        else:
            leftovers.extend(group)

    return groups, leftovers

def save_groups(groups, selected_ids, selected_date, slot):
    conn = get_conn()
    cur = conn.cursor()
    for did in selected_ids:
        cur.execute("INSERT OR IGNORE INTO attendance(date,slot,dog_id) VALUES(?,?,?)",
                    (selected_date, slot, did))
    for i, grp in enumerate(groups, start=1):
        gname = f"Group {i}"
        cur.execute("INSERT OR IGNORE INTO groups(date,slot,group_name,notes) VALUES(?,?,?,?)",
                    (selected_date, slot, gname, grp["status"]))
        for did in grp["dogs"]:
            cur.execute("INSERT OR IGNORE INTO group_members(date,slot,group_name,dog_id) VALUES(?,?,?,?)",
                        (selected_date, slot, gname, did))
    conn.commit()

# --- Pages ---
def page_dogs():
    st.header("Dogs")
    with st.form("add_dog", clear_on_submit=True):
        c1,c2,c3,c4 = st.columns([2,1,2,1])
        name = c1.text_input("Name *")
        size = c2.selectbox("Size", ["S","M","L"], index=1)
        temperament = c3.radio("Temperament", ["Neither", "Plays hard", "Shy"], index=0, horizontal=True)
        plays_hard = temperament == "Plays hard"
        shy = temperament == "Shy"
        intact = c4.checkbox("Intact")
        notes = st.text_area("Notes")
        photo = st.file_uploader("Photo (optional)", type=["png","jpg","jpeg"])
        if st.form_submit_button("Add dog"):
            if name.strip():
                photo_path = None
                if photo:
                    fn = f"{name.strip().replace(' ','_')}.jpg"
                    out = os.path.join(IMAGES_DIR, fn)
                    with open(out, "wb") as f: f.write(photo.getbuffer())
                    photo_path = out
                conn = get_conn()
                conn.execute("""INSERT OR REPLACE INTO dogs
                                (name,plays_hard,shy,intact,size,notes,photo_path)
                                VALUES(?,?,?,?,?,?,?)""",
                             (name.strip(), int(plays_hard), int(shy), int(intact),
                              size, notes, photo_path))
                conn.commit()
                st.success(f"Added {name}")

    df = fetch_df("SELECT id, name, size, plays_hard, shy, intact, notes FROM dogs ORDER BY name")
    st.dataframe(df, use_container_width=True)
    if st.button("Seed demo dogs"):
        seed_demo_dogs()

def seed_demo_dogs():
    conn = get_conn()
    cur = conn.cursor()
    for n in ["Callie","Merle","Archie","Ryder","Pickles"]:
        cur.execute("INSERT OR IGNORE INTO dogs(name) VALUES(?)", (n,))
    ids = dict(fetch_df("SELECT id, name FROM dogs").set_index("name")["id"])
    def setrel(a,b,status):
        a_id, b_id = sorted([ids[a], ids[b]])
        cur.execute("""INSERT OR REPLACE INTO relationships(dog_a_id,dog_b_id,status)
                       VALUES(?,?,?)""", (a_id,b_id,status))
    # Based on the example
    setrel("Callie","Archie","friend")
    setrel("Callie","Merle","friend")
    setrel("Archie","Merle","friend")
    setrel("Ryder","Pickles","friend")
    setrel("Ryder","Merle","foe")
    conn.commit()
    st.success("Seeded demo dogs + relationships.")

def page_relationships():
    st.header("Relationships")
    dogs = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs.empty:
        st.info("Add dogs first.")
        return
    name_by_id = dict(dogs.values)

    c1,c2,c3 = st.columns([2,2,2])
    a = c1.selectbox("Dog A", options=list(name_by_id.keys()),
                     format_func=lambda i: name_by_id[i])
    b = c2.selectbox("Dog B", options=list(name_by_id.keys()), index=1,
                     format_func=lambda i: name_by_id[i])
    status = c3.radio("Status", ["friend","foe","unknown"], index=2, horizontal=True)
    if st.button("Save relationship"):
        upsert_relationship(a, b, status)
        st.success(f"Saved: {name_by_id[a]} ↔ {name_by_id[b]} = {status}")

    # Matrix view
    df = pd.DataFrame(index=[name_by_id[i] for i in name_by_id],
                      columns=[name_by_id[i] for i in name_by_id])
    for i in name_by_id:
        for j in name_by_id:
            df.loc[name_by_id[i], name_by_id[j]] = get_relationship(i, j)
    st.write("friend / foe / unknown")
    st.dataframe(df, use_container_width=True)

def page_today():
    st.header("Today & Auto-Grouping")
    dogs = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs.empty:
        st.info("Add dogs first.")
        return

    dflt_date = date.today().isoformat()
    c1, c2 = st.columns(2)
    selected_date = c1.text_input("Date (YYYY-MM-DD)", value=dflt_date)
    slot = c2.selectbox("Slot", ["AM","PM","Midday","Custom"])
    if slot == "Custom":
        slot = st.text_input("Custom slot name")

    selected = st.multiselect("Who is here today?",
                              options=list(dogs["id"]),
                              format_func=lambda i: dogs.loc[dogs["id"]==i, "name"].values[0])

    st.subheader("Rules")
    cc = st.columns(5)
    target_size = cc[0].slider("Max group size", 2, 8, 4)
    allow_unknown = cc[1].checkbox("Allow Unknown pairs", True)
    separate_hard_shy = cc[2].checkbox("Separate hard/shy", True)
    separate_intact = cc[3].checkbox("Separate intact", False)
    same_size_only = cc[4].checkbox("Same size only", False)
    rules = dict(
        allow_unknown=allow_unknown,
        separate_hard_shy=separate_hard_shy,
        separate_intact=separate_intact,
        same_size_only=same_size_only
    )

    if st.button("Suggest groups", disabled=len(selected)==0):
        groups, leftovers = suggest_groups(selected, rules, target_size)
        if not groups:
            st.warning("No compatible groups with current rules.")
        for i, grp in enumerate(groups, start=1):
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?"*len(grp["dogs"]))),
                grp["dogs"]
            )["name"].tolist()
            st.success(f"Group {i} — {grp['status']}: " + ", ".join(names))
        if leftovers:
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?"*len(leftovers))),
                leftovers
            )["name"].tolist()
            st.info("Leftovers: " + ", ".join(names))
        st.session_state["last_groups"] = groups
        st.session_state["last_selection"] = selected
        st.session_state["last_date"] = selected_date
        st.session_state["last_slot"] = slot

    if "last_groups" in st.session_state and st.button("Save these groups"):
        save_groups(
            st.session_state["last_groups"],
            st.session_state["last_selection"],
            st.session_state["last_date"],
            st.session_state["last_slot"]
        )
        st.success("Saved groups + attendance.")

def page_history():
    st.header("Saved Groups (History)")
    dates = fetch_df("SELECT DISTINCT date FROM groups ORDER BY date DESC")
    if dates.empty:
        st.info("No saved groups yet.")
        return
    sel_date = st.selectbox("Date", dates["date"].tolist())
    slots = fetch_df("SELECT DISTINCT slot FROM groups WHERE date=? ORDER BY slot", (sel_date,))
    sel_slot = st.selectbox("Slot", slots["slot"].tolist())

    groups_df = fetch_df(
        "SELECT group_name, notes FROM groups WHERE date=? AND slot=? ORDER BY group_name",
        (sel_date, sel_slot)
    )
    members_df = fetch_df("""
        SELECT g.group_name, d.name
        FROM group_members gm
        JOIN dogs d ON d.id = gm.dog_id
        JOIN groups g ON g.date=gm.date AND g.slot=gm.slot AND g.group_name=gm.group_name
        WHERE gm.date=? AND gm.slot=?
        ORDER BY g.group_name, d.name
    """, (sel_date, sel_slot))

    for gname in groups_df["group_name"].tolist():
        note = groups_df.loc[groups_df["group_name"]==gname, "notes"].values[0]
        names = members_df.loc[members_df["group_name"]==gname, "name"].tolist()
        st.write(f"**{gname}** — {note or 'Saved'}")
        st.write(", ".join(names) if names else "_(empty)_")
        st.markdown("---")

    if st.button("Export CSV"):
        out = os.path.join(APP_DIR, f"groups_{sel_date}_{sel_slot}.csv")
        members_df.to_csv(out, index=False)
        st.success(f"Exported to {out}")

# --- App entry ---
def main():
    st.set_page_config(page_title="Dog Playgroups", page_icon="🐶", layout="wide")
    init_db()
    page = st.sidebar.radio("Pages", ["Dogs", "Relationships", "Today", "History"])
    if page == "Dogs": page_dogs()
    elif page == "Relationships": page_relationships()
    elif page == "Today": page_today()
    else: page_history()

if __name__ == "__main__":
    main()
