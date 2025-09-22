import html
from itertools import combinations

import pandas as pd
import streamlit as st

from db import fetch_df
from relationships import get_relationship, upsert_relationship

def page_relationships():
    st.header("Relationships")
    dogs = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs.empty:
        st.info("Add dogs first.")
        return
    name_by_id = dict(dogs.values)

    c1, c2, c3 = st.columns([2, 2, 2])
    dog_ids = list(name_by_id.keys())
    if len(dog_ids) < 2:
        st.info("Add at least two dogs to manage relationships.")
        return
    a = c1.selectbox("Dog A", options=dog_ids, format_func=lambda i: name_by_id[i])
    b_default_index = 1 if len(dog_ids) > 1 else 0
    b = c2.selectbox(
        "Dog B", options=dog_ids, index=b_default_index, format_func=lambda i: name_by_id[i]
    )

    current_status = get_relationship(a, b)
    status_options = ["friend", "foe", "unknown"]
    status_index = status_options.index(current_status) if current_status in status_options else 2
    status = c3.radio("Status", status_options, index=status_index, horizontal=True)
    if st.button("Save relationship"):
        upsert_relationship(a, b, status)
        st.success(f"Saved: {name_by_id[a]} ↔ {name_by_id[b]} = {status}")
        current_status = status

    if a == b:
        st.info("Select two different dogs to see their relationship details.")
    else:
        st.subheader("Relationship details")
        st.markdown(
            f"**{name_by_id[a]}** and **{name_by_id[b]}** are currently **{current_status}**."
        )

    st.subheader("Browse relationships")
    status_view = st.selectbox(
        "Show pairs with status", status_options, index=status_index, key="relationship_status_filter"
    )

    raw_pairs = []
    if status_view == "unknown":
        for i, j in combinations(dog_ids, 2):
            if get_relationship(i, j) == "unknown":
                raw_pairs.append((name_by_id[i], name_by_id[j]))
    else:
        rel_df = fetch_df(
            "SELECT dog_a_id, dog_b_id FROM relationships WHERE status=? ORDER BY id",
            (status_view,),
        )
        for _, row in rel_df.iterrows():
            dog_a = name_by_id.get(int(row["dog_a_id"]))
            dog_b = name_by_id.get(int(row["dog_b_id"]))
            if dog_a and dog_b:
                raw_pairs.append((dog_a, dog_b))

    seen_pairs = set()
    pairs = []
    for name_a, name_b in raw_pairs:
        key = tuple(sorted((name_a, name_b)))
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        pairs.append(key)

    if not pairs:
        st.caption("No pairs saved with that status yet.")
    else:
        if len(pairs) > 10:
            items = "<br>".join(
                f"{idx}. {html.escape(name_a)} ↔ {html.escape(name_b)}"
                for idx, (name_a, name_b) in enumerate(pairs, start=1)
            )
            st.markdown(
                f"<div style='max-height: 300px; overflow-y: auto; padding-right: 8px;'>{items}</div>",
                unsafe_allow_html=True,
            )
        else:
            for idx, (name_a, name_b) in enumerate(pairs, start=1):
                st.write(f"{idx}. {name_a} ↔ {name_b}")

    st.subheader("Import relationships from CSV")
    st.caption(
        "CSV columns expected: dog_a, dog_b, status (friend/foe/unknown). Additional columns are ignored."
    )
    csv_file = st.file_uploader("Upload relationships CSV", type=["csv"], key="rel_csv_upload")
    if csv_file is not None:
        try:
            csv_df = pd.read_csv(csv_file)
        except Exception as exc:
            st.error(f"Failed to read CSV: {exc}")
            csv_df = None

        if csv_df is not None and not csv_df.empty:
            renamed = {
                c: c.strip().lower().replace(" ", "_") for c in csv_df.columns
            }
            csv_df = csv_df.rename(columns=renamed)
            required = {"dog_a", "dog_b", "status"}
            if not required.issubset(csv_df.columns):
                missing = ", ".join(sorted(required - set(csv_df.columns)))
                st.error(f"CSV missing required column(s): {missing}")
            else:
                preview = csv_df[list(required)].copy()
                st.dataframe(preview.head(20), use_container_width=True)

                id_by_name = {name.lower(): did for did, name in name_by_id.items()}

                def normalize_status(value: str):
                    if pd.isna(value):
                        return None
                    s = str(value).strip().lower()
                    mapping = {
                        "friend": "friend",
                        "friends": "friend",
                        "foe": "foe",
                        "enemy": "foe",
                        "unknown": "unknown",
                        "unsure": "unknown",
                    }
                    return mapping.get(s)

                if st.button("Import relationships", key="import_rel_csv_btn"):
                    created = changed = unchanged = skipped = 0
                    errors = []
                    existing_rel = fetch_df(
                        "SELECT dog_a_id, dog_b_id, status FROM relationships"
                    )
                    existing_map = {
                        tuple(sorted((int(row["dog_a_id"]), int(row["dog_b_id"])))): row["status"]
                        for _, row in existing_rel.iterrows()
                    }
                    for idx, row in csv_df.iterrows():
                        name_a = str(row.get("dog_a", "")).strip()
                        name_b = str(row.get("dog_b", "")).strip()
                        status_val = normalize_status(row.get("status"))

                        if not name_a or not name_b:
                            skipped += 1
                            errors.append(f"Row {idx+1}: missing dog name(s)")
                            continue
                        if name_a.lower() == name_b.lower():
                            skipped += 1
                            errors.append(f"Row {idx+1} ({name_a}): cannot relate dog to itself")
                            continue
                        if status_val is None:
                            skipped += 1
                            errors.append(
                                f"Row {idx+1} ({name_a} ↔ {name_b}): invalid status '{row.get('status')}'"
                            )
                            continue

                        ida = id_by_name.get(name_a.lower())
                        idb = id_by_name.get(name_b.lower())
                        if ida is None or idb is None:
                            skipped += 1
                            errors.append(
                                f"Row {idx+1} ({name_a} ↔ {name_b}): dog not found in database"
                            )
                            continue

                        key = tuple(sorted((ida, idb)))
                        previous = existing_map.get(key)
                        upsert_relationship(ida, idb, status_val)
                        existing_map[key] = status_val
                        if previous is None:
                            created += 1
                        elif previous == status_val:
                            unchanged += 1
                        else:
                            changed += 1

                    summary = (
                        "Import complete — Created: {created}, Changed: {changed}, "
                        "Unchanged: {unchanged}, Skipped: {skipped}"
                    ).format(
                        created=created, changed=changed, unchanged=unchanged, skipped=skipped
                    )
                    st.success(summary)
                    if errors:
                        with st.expander("Show import messages"):
                            for msg in errors[:200]:
                                st.write("-", msg)
                    st.rerun()
