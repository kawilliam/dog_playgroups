from itertools import combinations

from db import fetch_df, get_conn
from relationships_service import get_relationship

def allowed_pair(a_id, b_id, rules, status, attrs):
    if status == "foe":
        return False
    if status == "unknown" and not rules["allow_unknown"]:
        return False

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

    query = "SELECT id, plays_hard, shy, intact, size FROM dogs WHERE id IN ({})".format(
        ",".join("?" * len(dog_ids))
    )
    df = fetch_df(query, dog_ids)
    attrs = {
        int(r.id): (bool(r.plays_hard), bool(r.shy), bool(r.intact), (r.size or "M"))
        for _, r in df.iterrows()
    }

    rel_cache = {}

    def rel(a, b):
        key = tuple(sorted((a, b)))
        if key not in rel_cache:
            rel_cache[key] = get_relationship(a, b)
        return rel_cache[key]

    remaining = set(dog_ids)
    groups, leftovers = [], []

    def compatibility_score(cand, group):
        score = 0
        for g in group:
            s = rel(cand, g)
            score += 2 if s == "friend" else (1 if s == "unknown" else -999)
        return score

    while remaining:
        seed = remaining.pop()
        group = [seed]

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

        fully_ok = all(
            allowed_pair(a, b, rules, rel(a, b), attrs) for a, b in combinations(group, 2)
        )
        if fully_ok and len(group) > 1:
            statuses = [rel(a, b) for a, b in combinations(group, 2)]
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
        cur.execute(
            "INSERT OR IGNORE INTO attendance(date,slot,dog_id) VALUES(?,?,?)",
            (selected_date, slot, did)
        )
    for i, grp in enumerate(groups, start=1):
        gname = f"Group {i}"
        cur.execute(
            "INSERT OR IGNORE INTO groups(date,slot,group_name,notes) VALUES(?,?,?,?)",
            (selected_date, slot, gname, grp["status"])
        )
        for did in grp["dogs"]:
            cur.execute(
                "INSERT OR IGNORE INTO group_members(date,slot,group_name,dog_id) VALUES(?,?,?,?)",
                (selected_date, slot, gname, did)
            )
    conn.commit()
