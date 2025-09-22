import os

import pandas as pd
import streamlit as st

from config import IMAGES_DIR
from db import fetch_df, get_conn
from relationships_service import upsert_relationship

def page_dogs():
    st.header("Dogs")
    with st.form("add_dog", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 1, 2, 1])
        name = c1.text_input("Name *")
        size = c2.selectbox("Size", ["S", "M", "L"], index=1)
        temperament = c3.radio(
            "Temperament", ["Neither", "Plays hard", "Shy"], index=0, horizontal=True
        )
        plays_hard = temperament == "Plays hard"
        shy = temperament == "Shy"
        intact = c4.checkbox("Intact")
        notes = st.text_area("Notes")
        photo = st.file_uploader("Photo (optional)", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Add dog"):
            if name.strip():
                photo_path = None
                if photo:
                    fn = f"{name.strip().replace(' ', '_')}.jpg"
                    out = os.path.join(IMAGES_DIR, fn)
                    with open(out, "wb") as f:
                        f.write(photo.getbuffer())
                    photo_path = out
                conn = get_conn()
                conn.execute(
                    """INSERT OR REPLACE INTO dogs
                                    (name,plays_hard,shy,intact,size,notes,photo_path)
                                    VALUES(?,?,?,?,?,?,?)""",
                    (
                        name.strip(),
                        int(plays_hard),
                        int(shy),
                        int(intact),
                        size,
                        notes,
                        photo_path,
                    ),
                )
                conn.commit()
                st.success(f"Added {name}")

    df = fetch_df(
        "SELECT name, size, plays_hard, shy, intact, notes, photo_path FROM dogs ORDER BY name"
    )
    table_col, profile_col = st.columns([1.5, 2])

    table_df = df[["name", "size"]].copy() if not df.empty else pd.DataFrame(columns=["name", "size"])
    if not table_df.empty:
        table_df.index = range(1, len(table_df) + 1)
    table_col.dataframe(table_df, use_container_width=True)

    if df.empty:
        profile_col.caption("Add dogs to see profile details here.")
    else:
        selected_name = profile_col.selectbox("View profile", df["name"].tolist(), index=0)
        rec = df.loc[df["name"] == selected_name].iloc[0]

        profile_col.markdown(f"### {selected_name}")
        photo_path = rec.get("photo_path")
        photo_area, info_area = profile_col.columns([1, 2])

        if photo_path and os.path.exists(photo_path):
            photo_area.image(photo_path, caption=selected_name, width=180)
        else:
            photo_area.caption("No photo")

        details = [
            f"**Size:** {rec.get('size', 'N/A') or 'N/A'}",
            f"**Plays hard:** {'Yes' if bool(rec.get('plays_hard')) else 'No'}",
            f"**Shy:** {'Yes' if bool(rec.get('shy')) else 'No'}",
            f"**Intact:** {'Yes' if bool(rec.get('intact')) else 'No'}",
        ]
        info_area.markdown("\n\n".join(details))

        notes = rec.get("notes")
        if isinstance(notes, str) and notes.strip():
            info_area.markdown("**Notes:**")
            info_area.write(notes)
    if st.button("Seed demo dogs"):
        seed_demo_dogs()
        st.rerun()

    st.subheader("Import dogs from CSV")
    st.caption(
        "Columns supported: name, size (S/M/L), plays_hard, shy, intact, notes. Booleans accept true/false/1/0/yes/no/on/off/y/n/t/f/enabled/disabled. Optional: temperament (Neither/Plays hard/Shy). Existing names are updated."
    )
    csv_file = st.file_uploader("Upload CSV", type=["csv"], key="dogs_csv_upload")
    if csv_file is not None:
        try:
            csv_df = pd.read_csv(csv_file)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
            csv_df = None

        if csv_df is not None and not csv_df.empty:
            norm_map = {c: c.strip().lower().replace(" ", "_").replace("-", "_") for c in csv_df.columns}
            csv_df = csv_df.rename(columns=norm_map)

            preview_cols = [
                c
                for c in ["name", "size", "temperament", "plays_hard", "shy", "intact", "notes"]
                if c in csv_df.columns
            ]
            st.write("Preview (first 10 rows):")
            st.dataframe(csv_df[preview_cols].head(10), use_container_width=True)

            def as_bool(v):
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
                true_vals = {
                    "1",
                    "true",
                    "t",
                    "yes",
                    "y",
                    "on",
                    "enable",
                    "enabled",
                    "active",
                    "checked",
                    "x",
                    "✔",
                    "✓",
                }
                false_vals = {
                    "0",
                    "false",
                    "f",
                    "no",
                    "n",
                    "off",
                    "disable",
                    "disabled",
                    "inactive",
                    "unchecked",
                    "",
                    "none",
                    "null",
                    "nan",
                }
                if s in true_vals:
                    return True
                if s in false_vals:
                    return False
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
                    size = size if size in {"S", "M", "L"} else "M"
                    notes = row.get("notes", None)
                    if isinstance(notes, float) and pd.isna(notes):
                        notes = None

                    try:
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
                            (name, int(ph), int(shy), int(intact), size, notes),
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
                st.success(
                    f"Import complete — Added: {added}, Updated: {updated}, Skipped: {skipped}"
                )
                if errors:
                    with st.expander("Show import messages"):
                        for msg in errors[:200]:
                            st.write("- ", msg)
                st.rerun()

    st.subheader("Edit dog")
    dogs_edit_df = fetch_df(
        "SELECT id, name, size, plays_hard, shy, intact, notes, photo_path FROM dogs ORDER BY name"
    )
    if dogs_edit_df.empty:
        st.caption("No dogs to edit.")
    else:
        sel_id = st.selectbox(
            "Choose a dog",
            options=dogs_edit_df["id"].tolist(),
            format_func=lambda i: dogs_edit_df.loc[dogs_edit_df["id"] == i, "name"].values[0],
        )
        rec = dogs_edit_df.loc[dogs_edit_df["id"] == sel_id].iloc[0]
        ec1, ec2, ec3, ec4 = st.columns([2, 1, 2, 1])
        new_name = ec1.text_input("Name *", value=str(rec["name"]))
        new_size = ec2.selectbox(
            "Size", ["S", "M", "L"], index=["S", "M", "L"].index(rec["size"] or "M")
        )
        temp_default = 1 if rec["plays_hard"] else (2 if rec["shy"] else 0)
        new_temperament = ec3.radio(
            "Temperament",
            ["Neither", "Plays hard", "Shy"],
            index=temp_default,
            horizontal=True,
            key=f"edit_temp_{sel_id}",
        )
        new_intact = ec4.checkbox("Intact", value=bool(rec["intact"]), key=f"edit_intact_{sel_id}")
        new_notes = st.text_area("Notes", value=rec["notes"] or "", key=f"edit_notes_{sel_id}")
        st.caption(f"Current photo: {rec['photo_path'] or 'None'}")
        new_photo = st.file_uploader(
            "Replace photo (optional)",
            type=["png", "jpg", "jpeg"],
            key=f"edit_photo_{sel_id}",
        )

        if st.button("Update dog", key=f"update_dog_{sel_id}"):
            if not new_name.strip():
                st.error("Name is required.")
            else:
                try:
                    photo_path = rec["photo_path"]
                    if new_photo is not None:
                        fn = f"{new_name.strip().replace(' ', '_')}.jpg"
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
                            new_name.strip(),
                            new_ph,
                            new_shy,
                            int(bool(new_intact)),
                            new_size,
                            new_notes,
                            photo_path,
                            int(sel_id),
                        ),
                    )
                    conn.commit()
                    st.success(f"Updated {new_name}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update dog: {e}")

    st.subheader("Delete dogs")
    dogs_for_delete = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs_for_delete.empty:
        st.caption("No dogs to delete.")
    else:
        to_delete = st.multiselect(
            "Select dogs to delete",
            options=list(dogs_for_delete["id"]),
            format_func=lambda i: dogs_for_delete.loc[dogs_for_delete["id"] == i, "name"].values[0],
        )
        st.warning(
            "Deleting a dog will also remove their relationships, group memberships, and attendance (via cascading deletes)."
        )
        confirm_del = st.checkbox(
            "I understand and want to delete the selected dogs.", key="confirm_delete_dogs"
        )
        if st.button("Delete selected dogs", disabled=(len(to_delete) == 0 or not confirm_del)):
            conn = get_conn()
            cur = conn.cursor()
            cur.executemany("DELETE FROM dogs WHERE id=?", [(int(i),) for i in to_delete])
            conn.commit()
            st.success(f"Deleted {len(to_delete)} dog(s).")
            st.rerun()

def seed_demo_dogs():
    conn = get_conn()
    cur = conn.cursor()
    names = ["Callie", "Merle", "Archie", "Ryder", "Pickles"]
    for n in names:
        cur.execute("INSERT OR IGNORE INTO dogs(name) VALUES(?)", (n,))
    conn.commit()
    ids = dict(fetch_df("SELECT id, name FROM dogs").set_index("name")["id"])

    def setrel(a, b, status):
        upsert_relationship(ids[a], ids[b], status)

    setrel("Callie", "Archie", "friend")
    setrel("Callie", "Merle", "friend")
    setrel("Archie", "Merle", "friend")
    setrel("Ryder", "Pickles", "friend")
    setrel("Ryder", "Merle", "foe")
    conn.commit()
    st.success("Seeded demo dogs + relationships.")
