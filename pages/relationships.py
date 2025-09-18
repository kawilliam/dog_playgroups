import html
from itertools import combinations

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
