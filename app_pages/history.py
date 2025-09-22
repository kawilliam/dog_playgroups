from pathlib import Path

import streamlit as st

from config import DATA_DIR
from db import fetch_df, get_conn

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
        (sel_date, sel_slot),
    )
    members_df = fetch_df(
        """
        SELECT g.group_name, d.name
        FROM group_members gm
        JOIN dogs d ON d.id = gm.dog_id
        JOIN groups g ON g.date=gm.date AND g.slot=gm.slot AND g.group_name=gm.group_name
        WHERE gm.date=? AND gm.slot=?
        ORDER BY g.group_name, d.name
    """,
        (sel_date, sel_slot),
    )

    for gname in groups_df["group_name"].tolist():
        note = groups_df.loc[groups_df["group_name"] == gname, "notes"].values[0]
        names = members_df.loc[members_df["group_name"] == gname, "name"].tolist()
        st.write(f"**{gname}** — {note or 'Saved'}")
        st.write(", ".join(names) if names else "_(empty)_")
        st.markdown("---")

    st.subheader("Delete specific groups")
    st.caption("Select groups to remove from this date/slot. Attendance remains unchanged.")
    del_keys = []
    for i, gname in enumerate(groups_df["group_name"].tolist(), start=1):
        key = f"del_grp_{sel_date}_{sel_slot}_{i}"
        del_keys.append((key, gname))
        st.checkbox(f"Delete {gname}", key=key, value=False)
    confirm_groups = st.checkbox(
        "I understand selected groups and their members will be permanently removed.",
        key=f"confirm_del_groups_{sel_date}_{sel_slot}",
    )
    if st.button("Delete selected groups", disabled=not confirm_groups):
        to_delete = [g for k, g in del_keys if st.session_state.get(k)]
        if not to_delete:
            st.warning("Select at least one group to delete.")
        else:
            conn = get_conn()
            cur = conn.cursor()
            for gname in to_delete:
                cur.execute(
                    "DELETE FROM group_members WHERE date=? AND slot=? AND group_name=?",
                    (sel_date, sel_slot, gname),
                )
                cur.execute(
                    "DELETE FROM groups WHERE date=? AND slot=? AND group_name=?",
                    (sel_date, sel_slot, gname),
                )
            conn.commit()
            st.success(f"Deleted {len(to_delete)} group(s) from {sel_date} / {sel_slot}.")
            st.rerun()

    if st.button("Export CSV"):
        out = Path(DATA_DIR) / f"groups_{sel_date}_{sel_slot}.csv"
        members_df.to_csv(out, index=False)
        st.success(f"Exported to {out}")

    st.subheader("Danger zone")
    st.warning(
        "Deleting history will permanently remove groups, group members, and attendance for the selected date and slot."
    )
    confirm = st.checkbox("I understand and want to delete this date/slot.")
    if st.button("Delete selected date/slot", disabled=not confirm):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM group_members WHERE date=? AND slot=?", (sel_date, sel_slot))
        cur.execute("DELETE FROM groups WHERE date=? AND slot=?", (sel_date, sel_slot))
        cur.execute("DELETE FROM attendance WHERE date=? AND slot=?", (sel_date, sel_slot))
        conn.commit()
        st.success(f"Deleted history for {sel_date} / {sel_slot}.")
        st.rerun()
