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

    df = fetch_df("SELECT name, size, plays_hard, shy, intact, notes FROM dogs ORDER BY name")
    st.dataframe(df, use_container_width=True)
    if st.button("Seed demo dogs"):
        seed_demo_dogs()
        st.rerun()

    # CSV Import section
    st.subheader("Import dogs from CSV")
    st.caption("Columns supported: name, size (S/M/L), plays_hard, shy, intact, notes. Booleans accept true/false/1/0/yes/no/on/off/y/n/t/f/enabled/disabled. Optional: temperament (Neither/Plays hard/Shy). Existing names are updated.")
    csv_file = st.file_uploader("Upload CSV", type=["csv"], key="dogs_csv_upload")
    if csv_file is not None:
        try:
            csv_df = pd.read_csv(csv_file)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
            csv_df = None

        if csv_df is not None and not csv_df.empty:
            # Normalize columns to snake_case lowercase for matching
            norm_map = {c: c.strip().lower().replace(" ", "_").replace("-", "_") for c in csv_df.columns}
            csv_df = csv_df.rename(columns=norm_map)

            preview_cols = [c for c in [
                "name", "size", "temperament", "plays_hard", "shy", "intact", "notes"
            ] if c in csv_df.columns]
            st.write("Preview (first 10 rows):")
            st.dataframe(csv_df[preview_cols].head(10), use_container_width=True)

            def as_bool(v):
                # Robust boolean parser for common spellings
                if pd.isna(v):
                    return False
                if isinstance(v, bool):
                    return v
                if isinstance(v, (int, float)):
                    try:
                        return bool(int(v))
                    except Exception:
                        return False
                s = str(v).strip().lower()
                true_vals = {"1", "true", "t", "yes", "y", "on", "enable", "enabled", "active", "checked", "x", "✔", "✓"}
                false_vals = {"0", "false", "f", "no", "n", "off", "disable", "disabled", "inactive", "unchecked", "", "none", "null", "nan"}
                if s in true_vals:
                    return True
                if s in false_vals:
                    return False
                # default: treat unknown as False
                return False

            if st.button("Import CSV rows", key="import_dogs_csv_btn"):
                existing = set(fetch_df("SELECT name FROM dogs")["name"].tolist())
                added = updated = skipped = 0
                errors = []
                conn = get_conn()
                for idx, row in csv_df.iterrows():
                    name = str(row.get("name", "")).strip()
                    if not name:
                        skipped += 1
                        errors.append(f"Row {idx+1}: missing name")
                        continue

                    # Determine temperament/flags
                    temperament = str(row.get("temperament", "")).strip()
                    if temperament:
                        ph = temperament.lower() == "plays hard"
                        shy = temperament.lower() == "shy"
                    else:
                        ph = as_bool(row.get("plays_hard", 0))
                        shy = as_bool(row.get("shy", 0))

                    if ph and shy:
                        skipped += 1
                        errors.append(f"Row {idx+1} ({name}): cannot be both plays_hard and shy")
                        continue

                    intact = as_bool(row.get("intact", 0))
                    size = str(row.get("size", "M")).strip().upper()
                    size = size if size in {"S","M","L"} else "M"
                    notes = row.get("notes", None)
                    if isinstance(notes, float) and pd.isna(notes):
                        notes = None

                    try:
                        # Upsert by unique name, preserve existing photo_path if not provided
                        conn.execute(
                            """
                            INSERT INTO dogs(name, plays_hard, shy, intact, size, notes, photo_path)
                            VALUES(?,?,?,?,?,?,NULL)
                            ON CONFLICT(name) DO UPDATE SET
                              plays_hard=excluded.plays_hard,
                              shy=excluded.shy,
                              intact=excluded.intact,
                              size=excluded.size,
                              notes=excluded.notes,
                              photo_path=COALESCE(excluded.photo_path, dogs.photo_path)
                            """,
                            (name, int(ph), int(shy), int(intact), size, notes)
                        )
                        if name in existing:
                            updated += 1
                        else:
                            added += 1
                            existing.add(name)
                    except Exception as e:
                        skipped += 1
                        errors.append(f"Row {idx+1} ({name}): {e}")

                conn.commit()
                st.success(f"Import complete — Added: {added}, Updated: {updated}, Skipped: {skipped}")
                if errors:
                    with st.expander("Show import messages"):
                        for msg in errors[:200]:
                            st.write("- ", msg)
                st.rerun()

    # Edit dogs section
    st.subheader("Edit dog")
    dogs_edit_df = fetch_df("SELECT id, name, size, plays_hard, shy, intact, notes, photo_path FROM dogs ORDER BY name")
    if dogs_edit_df.empty:
        st.caption("No dogs to edit.")
    else:
        sel_id = st.selectbox(
            "Choose a dog",
            options=dogs_edit_df["id"].tolist(),
            format_func=lambda i: dogs_edit_df.loc[dogs_edit_df["id"]==i, "name"].values[0]
        )
        rec = dogs_edit_df.loc[dogs_edit_df["id"]==sel_id].iloc[0]
        ec1, ec2, ec3, ec4 = st.columns([2,1,2,1])
        new_name = ec1.text_input("Name *", value=str(rec["name"]))
        new_size = ec2.selectbox("Size", ["S","M","L"], index=["S","M","L"].index(rec["size"] or "M"))
        temp_default = 1 if rec["plays_hard"] else (2 if rec["shy"] else 0)
        new_temperament = ec3.radio("Temperament", ["Neither", "Plays hard", "Shy"], index=temp_default, horizontal=True, key=f"edit_temp_{sel_id}")
        new_intact = ec4.checkbox("Intact", value=bool(rec["intact"]), key=f"edit_intact_{sel_id}")
        new_notes = st.text_area("Notes", value=rec["notes"] or "", key=f"edit_notes_{sel_id}")
        st.caption(f"Current photo: {rec['photo_path'] or 'None'}")
        new_photo = st.file_uploader("Replace photo (optional)", type=["png","jpg","jpeg"], key=f"edit_photo_{sel_id}")

        if st.button("Update dog", key=f"update_dog_{sel_id}"):
            if not new_name.strip():
                st.error("Name is required.")
            else:
                try:
                    photo_path = rec["photo_path"]
                    if new_photo is not None:
                        fn = f"{new_name.strip().replace(' ','_')}.jpg"
                        out = os.path.join(IMAGES_DIR, fn)
                        with open(out, "wb") as f:
                            f.write(new_photo.getbuffer())
                        photo_path = out
                    new_ph = int(new_temperament == "Plays hard")
                    new_shy = int(new_temperament == "Shy")
                    conn = get_conn()
                    conn.execute(
                        """
                        UPDATE dogs
                        SET name=?, plays_hard=?, shy=?, intact=?, size=?, notes=?, photo_path=?
                        WHERE id=?
                        """,
                        (
                            new_name.strip(), new_ph, new_shy, int(bool(new_intact)),
                            new_size, new_notes, photo_path, int(sel_id)
                        )
                    )
                    conn.commit()
                    st.success(f"Updated {new_name}.")
                    st.rerun()
                except sqlite3.IntegrityError as e:
                    st.error(f"Failed to update dog: {e}")

    # Delete dogs section
    st.subheader("Delete dogs")
    dogs_for_delete = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs_for_delete.empty:
        st.caption("No dogs to delete.")
    else:
        to_delete = st.multiselect(
            "Select dogs to delete",
            options=list(dogs_for_delete["id"]),
            format_func=lambda i: dogs_for_delete.loc[dogs_for_delete["id"]==i, "name"].values[0]
        )
        st.warning(
            "Deleting a dog will also remove their relationships, group memberships, and attendance (via cascading deletes)."
        )
        confirm_del = st.checkbox("I understand and want to delete the selected dogs.", key="confirm_delete_dogs")
        if st.button("Delete selected dogs", disabled=(len(to_delete)==0 or not confirm_del)):
            conn = get_conn()
            cur = conn.cursor()
            cur.executemany("DELETE FROM dogs WHERE id=?", [(int(i),) for i in to_delete])
            conn.commit()
            st.success(f"Deleted {len(to_delete)} dog(s).")
            st.rerun()

def seed_demo_dogs():
    conn = get_conn()
    cur = conn.cursor()
    names = ["Callie","Merle","Archie","Ryder","Pickles"]
    for n in names:
        cur.execute("INSERT OR IGNORE INTO dogs(name) VALUES(?)", (n,))
    conn.commit()
    ids = dict(fetch_df("SELECT id, name FROM dogs").set_index("name")["id"])
    def setrel(a,b,status):
        upsert_relationship(ids[a], ids[b], status)
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

    c1, c2 = st.columns(2)
    selected_date_obj = c1.date_input("Date", value=date.today(), min_value=date.today())
    # Custom time slot: choose start and end times (12-hour format)
    sc1, sc2, sc3 = c2.columns([1,1,1])
    start_hour = sc1.selectbox("Start hour", list(range(1,13)), index=8)
    start_minute = sc2.selectbox("Start minute", [f"{m:02d}" for m in range(0,60)], index=0)
    start_ampm = sc3.selectbox("Start AM/PM", ["AM","PM"], index=0)
    ec1, ec2, ec3 = c2.columns([1,1,1])
    end_hour = ec1.selectbox("End hour", list(range(1,13)), index=11)
    end_minute = ec2.selectbox("End minute", [f"{m:02d}" for m in range(0,60)], index=0)
    end_ampm = ec3.selectbox("End AM/PM", ["AM","PM"], index=0)
    slot = f"{start_hour}:{start_minute} {start_ampm} - {end_hour}:{end_minute} {end_ampm}"
    # Normalize date to string for DB/session use
    selected_date = selected_date_obj.isoformat() if hasattr(selected_date_obj, "isoformat") else str(selected_date_obj)

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
        # Clear previous selection checkboxes
        for k in list(st.session_state.keys()):
            if str(k).startswith("sel_grp_"):
                del st.session_state[k]
        st.session_state["last_groups"] = groups
        st.session_state["last_selection"] = selected
        st.session_state["last_date"] = selected_date
        st.session_state["last_slot"] = slot

    # Allow selecting specific groups to save
    if "last_groups" in st.session_state and st.session_state["last_groups"]:
        st.subheader("Review suggested groups")
        for i, grp in enumerate(st.session_state["last_groups"], start=1):
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?"*len(grp["dogs"]))),
                grp["dogs"]
            )["name"].tolist()
            st.checkbox(
                f"Save Group {i} — {grp['status']}: " + ", ".join(names),
                value=True,
                key=f"sel_grp_{i}"
            )
        # Show leftovers based on the last selection
        all_in_groups = {d for grp in st.session_state["last_groups"] for d in grp["dogs"]}
        leftovers = sorted(set(st.session_state.get("last_selection", [])) - all_in_groups)
        if leftovers:
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?"*len(leftovers))),
                leftovers
            )["name"].tolist()
            st.info("Leftovers: " + ", ".join(names))

        if st.button("Save selected groups"):
            selected_groups = []
            selected_ids = set()
            for i, grp in enumerate(st.session_state["last_groups"], start=1):
                if st.session_state.get(f"sel_grp_{i}"):
                    selected_groups.append(grp)
                    selected_ids.update(grp["dogs"])
            if not selected_groups:
                st.warning("Select at least one group to save.")
            else:
                save_groups(
                    selected_groups,
                    sorted(selected_ids),
                    st.session_state["last_date"],
                    st.session_state["last_slot"]
                )
                st.success(f"Saved {len(selected_groups)} group(s) and attendance.")

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

    # Per-group deletion controls
    st.subheader("Delete specific groups")
    st.caption("Select groups to remove from this date/slot. Attendance remains unchanged.")
    del_keys = []
    for i, gname in enumerate(groups_df["group_name"].tolist(), start=1):
        key = f"del_grp_{sel_date}_{sel_slot}_{i}"
        del_keys.append((key, gname))
        st.checkbox(f"Delete {gname}", key=key, value=False)
    confirm_groups = st.checkbox(
        "I understand selected groups and their members will be permanently removed.",
        key=f"confirm_del_groups_{sel_date}_{sel_slot}"
    )
    if st.button("Delete selected groups", disabled=not confirm_groups):
        to_delete = [g for k, g in del_keys if st.session_state.get(k)]
        if not to_delete:
            st.warning("Select at least one group to delete.")
        else:
            conn = get_conn()
            cur = conn.cursor()
            for gname in to_delete:
                cur.execute("DELETE FROM group_members WHERE date=? AND slot=? AND group_name=?",
                            (sel_date, sel_slot, gname))
                cur.execute("DELETE FROM groups WHERE date=? AND slot=? AND group_name=?",
                            (sel_date, sel_slot, gname))
            conn.commit()
            st.success(f"Deleted {len(to_delete)} group(s) from {sel_date} / {sel_slot}.")
            # Refresh the page to reflect deletions
            st.rerun()

    if st.button("Export CSV"):
        out = os.path.join(APP_DIR, f"groups_{sel_date}_{sel_slot}.csv")
        members_df.to_csv(out, index=False)
        st.success(f"Exported to {out}")

    st.subheader("Danger zone")
    st.warning(
        "Deleting history will permanently remove groups, group members, and attendance for the selected date and slot.")
    confirm = st.checkbox("I understand and want to delete this date/slot.")
    if st.button("Delete selected date/slot", disabled=not confirm):
        conn = get_conn()
        cur = conn.cursor()
        # Remove in safe order since there are no explicit FKs from group_members to groups
        cur.execute("DELETE FROM group_members WHERE date=? AND slot=?", (sel_date, sel_slot))
        cur.execute("DELETE FROM groups WHERE date=? AND slot=?", (sel_date, sel_slot))
        cur.execute("DELETE FROM attendance WHERE date=? AND slot=?", (sel_date, sel_slot))
        conn.commit()
        st.success(f"Deleted history for {sel_date} / {sel_slot}.")
        st.rerun()

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
