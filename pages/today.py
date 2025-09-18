from datetime import date

import streamlit as st

from db import fetch_df
from grouping import save_groups, suggest_groups

def page_today():
    st.header("Today & Auto-Grouping")
    dogs = fetch_df("SELECT id, name FROM dogs ORDER BY name")
    if dogs.empty:
        st.info("Add dogs first.")
        return

    c1, c2 = st.columns(2)
    selected_date_obj = c1.date_input("Date", value=date.today(), min_value=date.today())
    sc1, sc2, sc3 = c2.columns([1, 1, 1])
    start_hour = sc1.selectbox("Start hour", list(range(1, 13)), index=8)
    start_minute = sc2.selectbox("Start minute", [f"{m:02d}" for m in range(0, 60)], index=0)
    start_ampm = sc3.selectbox("Start AM/PM", ["AM", "PM"], index=0)
    ec1, ec2, ec3 = c2.columns([1, 1, 1])
    end_hour = ec1.selectbox("End hour", list(range(1, 13)), index=11)
    end_minute = ec2.selectbox("End minute", [f"{m:02d}" for m in range(0, 60)], index=0)
    end_ampm = ec3.selectbox("End AM/PM", ["AM", "PM"], index=0)
    slot = f"{start_hour}:{start_minute} {start_ampm} - {end_hour}:{end_minute} {end_ampm}"
    selected_date = (
        selected_date_obj.isoformat() if hasattr(selected_date_obj, "isoformat") else str(selected_date_obj)
    )

    selected = st.multiselect(
        "Who is here today?",
        options=list(dogs["id"]),
        format_func=lambda i: dogs.loc[dogs["id"] == i, "name"].values[0],
    )

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
        same_size_only=same_size_only,
    )

    if st.button("Suggest groups", disabled=len(selected) == 0):
        groups, leftovers = suggest_groups(selected, rules, target_size)
        if not groups:
            st.warning("No compatible groups with current rules.")
        for k in list(st.session_state.keys()):
            if str(k).startswith("sel_grp_"):
                del st.session_state[k]
        st.session_state["last_groups"] = groups
        st.session_state["last_selection"] = selected
        st.session_state["last_date"] = selected_date
        st.session_state["last_slot"] = slot

    if "last_groups" in st.session_state and st.session_state["last_groups"]:
        st.subheader("Review suggested groups")
        for i, grp in enumerate(st.session_state["last_groups"], start=1):
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?" * len(grp["dogs"]))),
                grp["dogs"],
            )["name"].tolist()
            st.checkbox(
                f"Save Group {i} — {grp['status']}: " + ", ".join(names),
                value=True,
                key=f"sel_grp_{i}",
            )
        all_in_groups = {d for grp in st.session_state["last_groups"] for d in grp["dogs"]}
        leftovers = sorted(set(st.session_state.get("last_selection", [])) - all_in_groups)
        if leftovers:
            names = fetch_df(
                "SELECT name FROM dogs WHERE id IN ({})".format(",".join("?" * len(leftovers))),
                leftovers,
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
                    st.session_state["last_slot"],
                )
                st.success(f"Saved {len(selected_groups)} group(s) and attendance.")
