import os
import psycopg2
import psycopg2.extras
from datetime import date


def get_conn():
    return psycopg2.connect(os.environ["DB_URL"])


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id SERIAL PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            linkedin_url TEXT NOT NULL UNIQUE,
            note TEXT,
            status TEXT DEFAULT 'pending',
            added_on DATE DEFAULT CURRENT_DATE,
            sent_on DATE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id SERIAL PRIMARY KEY,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            queued_date DATE NOT NULL,
            message TEXT NOT NULL,
            done INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            linkedin_url TEXT,
            event_type TEXT NOT NULL,
            event_date DATE DEFAULT CURRENT_DATE,
            drafted_message TEXT,
            done INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def _row_to_dict(cursor, row):
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


# ── Profile operations ──────────────────────────────────────────────────────

def add_profile(first_name, last_name, linkedin_url, note=""):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO profiles (first_name, last_name, linkedin_url, note) VALUES (%s, %s, %s, %s)",
            (first_name.strip(), last_name.strip(), linkedin_url.strip(), note.strip()),
        )
        conn.commit()
        return True, "Profile added."
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "This LinkedIn URL already exists."
    finally:
        conn.close()


def bulk_add_profiles(rows):
    added, skipped = 0, 0
    for r in rows:
        ok, _ = add_profile(r["first_name"], r["last_name"], r["linkedin_url"], r.get("note", ""))
        if ok:
            added += 1
        else:
            skipped += 1
    return added, skipped


def get_pending_profiles():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE status = 'pending' ORDER BY added_on ASC")
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def get_all_profiles():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM profiles ORDER BY added_on DESC")
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_profile(profile_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))
    conn.commit()
    conn.close()


# ── Queue operations ────────────────────────────────────────────────────────

def get_todays_queue():
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT q.id as queue_id, q.message, q.done, q.queued_date,
               p.first_name, p.last_name, p.linkedin_url, p.note, p.id as profile_id
        FROM queue q
        JOIN profiles p ON q.profile_id = p.id
        WHERE q.queued_date = %s
        ORDER BY q.id ASC
        """,
        (today,),
    )
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def build_todays_queue(daily_limit=15):
    from templates import generate_connection_message

    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM queue WHERE queued_date = %s", (today,))
    if c.fetchone()[0] > 0:
        conn.close()
        return 0

    c.execute(
        "SELECT * FROM profiles WHERE status = 'pending' ORDER BY added_on ASC LIMIT %s",
        (daily_limit,),
    )
    pending = [_row_to_dict(c, r) for r in c.fetchall()]

    for p in pending:
        msg = generate_connection_message(p["first_name"], p.get("note", ""))
        c.execute(
            "INSERT INTO queue (profile_id, queued_date, message) VALUES (%s, %s, %s)",
            (p["id"], today, msg),
        )

    conn.commit()
    conn.close()
    return len(pending)


def mark_queue_done(queue_id, profile_id):
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE queue SET done = 1 WHERE id = %s", (queue_id,))
    c.execute(
        "UPDATE profiles SET status = 'sent', sent_on = %s WHERE id = %s",
        (today, profile_id),
    )
    conn.commit()
    conn.close()


# ── Notification operations ─────────────────────────────────────────────────

def add_notification(first_name, last_name, event_type, linkedin_url="", event_date=None):
    from templates import generate_event_message

    msg = generate_event_message(first_name, event_type)
    ed = event_date or date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO notifications (first_name, last_name, linkedin_url, event_type, event_date, drafted_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (first_name.strip(), last_name.strip(), linkedin_url.strip(), event_type, ed, msg),
    )
    conn.commit()
    conn.close()


def get_pending_notifications():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM notifications WHERE done = 0 ORDER BY event_date DESC")
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_notification_done(notif_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE notifications SET done = 1 WHERE id = %s", (notif_id,))
    conn.commit()
    conn.close()


def delete_notification(notif_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM notifications WHERE id = %s", (notif_id,))
    conn.commit()
    conn.close()


def update_notification_message(notif_id, new_msg):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE notifications SET drafted_message = %s WHERE id = %s", (new_msg, notif_id))
    conn.commit()
    conn.close()


# ── Stats ───────────────────────────────────────────────────────────────────

def get_stats():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM profiles"); total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM profiles WHERE status = 'sent'"); sent = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM profiles WHERE status = 'pending'"); pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE queued_date = CURRENT_DATE AND done = 1"); today_done = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE queued_date = CURRENT_DATE"); today_total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM notifications WHERE done = 0"); notif_pending = c.fetchone()[0]

    conn.close()
    return {
        "total": total,
        "sent": sent,
        "pending": pending,
        "today_done": today_done,
        "today_total": today_total,
        "notif_pending": notif_pending,
    }
