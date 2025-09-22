from db import get_conn

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
