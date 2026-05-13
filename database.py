import os
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash


def get_conn():
    return psycopg2.connect(os.environ["DB_URL"])


def _row_to_dict(cursor, row):
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'salesperson',
            password_hash TEXT NOT NULL
        )
    """)

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

    # Migration-safe: add user_id to existing tables
    c.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
    c.execute("ALTER TABLE queue ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")
    c.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)")

    conn.commit()
    _seed_users(conn)
    conn.close()


def _seed_users(conn):
    c = conn.cursor()
    users = [
        ('palak',  'Palak',  'salesperson', '123'),
        ('piyush', 'Piyush', 'salesperson', '123'),
        ('aaryan', 'Aaryan', 'salesperson', '123'),
        ('chirag', 'Chirag', 'manager',     '123'),
    ]
    for username, name, role, password in users:
        c.execute("SELECT id FROM users WHERE username = %s", (username,))
        if not c.fetchone():
            c.execute(
                "INSERT INTO users (username, name, role, password_hash) VALUES (%s, %s, %s, %s)",
                (username, name, role, generate_password_hash(password)),
            )
    conn.commit()


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_user_by_username(username):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = %s", (username,))
    row = c.fetchone()
    result = _row_to_dict(c, row) if row else None
    conn.close()
    return result


def verify_login(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None


def get_user_by_id(uid):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (uid,))
    row = c.fetchone()
    result = _row_to_dict(c, row) if row else None
    conn.close()
    return result


# ── Profile operations ────────────────────────────────────────────────────────

def add_profile(user_id, first_name, last_name, linkedin_url, note=""):
    conn = get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO profiles (user_id, first_name, last_name, linkedin_url, note) VALUES (%s, %s, %s, %s, %s)",
            (user_id, first_name.strip(), last_name.strip(), linkedin_url.strip(), note.strip()),
        )
        conn.commit()
        return True, "Profile added."
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return False, "This LinkedIn URL already exists."
    finally:
        conn.close()


def bulk_add_profiles(user_id, rows):
    added, skipped = 0, 0
    for r in rows:
        ok, _ = add_profile(user_id, r["first_name"], r["last_name"], r["linkedin_url"], r.get("note", ""))
        if ok:
            added += 1
        else:
            skipped += 1
    return added, skipped


def get_pending_profiles(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE status = 'pending' AND user_id = %s ORDER BY added_on ASC", (user_id,))
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def get_all_profiles(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM profiles WHERE user_id = %s ORDER BY added_on DESC", (user_id,))
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def delete_profile(profile_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM profiles WHERE id = %s", (profile_id,))
    conn.commit()
    conn.close()


# ── Queue operations ──────────────────────────────────────────────────────────

def get_todays_queue(user_id):
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT q.id as queue_id, q.message, q.done, q.queued_date,
               p.first_name, p.last_name, p.linkedin_url, p.note, p.id as profile_id
        FROM queue q
        JOIN profiles p ON q.profile_id = p.id
        WHERE q.queued_date = %s AND q.user_id = %s
        ORDER BY q.id ASC
        """,
        (today, user_id),
    )
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def build_todays_queue(user_id, daily_limit=15):
    from templates import generate_connection_message

    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM queue WHERE queued_date = %s AND user_id = %s", (today, user_id))
    if c.fetchone()[0] > 0:
        conn.close()
        return 0

    c.execute(
        "SELECT * FROM profiles WHERE status = 'pending' AND user_id = %s ORDER BY added_on ASC LIMIT %s",
        (user_id, daily_limit),
    )
    pending = [_row_to_dict(c, r) for r in c.fetchall()]

    for p in pending:
        msg = generate_connection_message(p["first_name"], p.get("note", ""))
        c.execute(
            "INSERT INTO queue (user_id, profile_id, queued_date, message) VALUES (%s, %s, %s, %s)",
            (user_id, p["id"], today, msg),
        )

    conn.commit()
    conn.close()
    return len(pending)


def mark_queue_done(queue_id, profile_id):
    today = date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE queue SET done = 1 WHERE id = %s", (queue_id,))
    c.execute("UPDATE profiles SET status = 'sent', sent_on = %s WHERE id = %s", (today, profile_id))
    conn.commit()
    conn.close()


# ── Notification operations ───────────────────────────────────────────────────

def add_notification(user_id, first_name, last_name, event_type, linkedin_url="", event_date=None):
    from templates import generate_event_message

    msg = generate_event_message(first_name, event_type)
    ed = event_date or date.today().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO notifications (user_id, first_name, last_name, linkedin_url, event_type, event_date, drafted_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, first_name.strip(), last_name.strip(), linkedin_url.strip(), event_type, ed, msg),
    )
    conn.commit()
    conn.close()


def get_pending_notifications(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM notifications WHERE done = 0 AND user_id = %s ORDER BY event_date DESC", (user_id,))
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


# ── Stats (per user) ──────────────────────────────────────────────────────────

def get_stats(user_id):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM profiles WHERE user_id = %s", (user_id,))
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM profiles WHERE user_id = %s AND status = 'sent'", (user_id,))
    sent = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM profiles WHERE user_id = %s AND status = 'pending'", (user_id,))
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE user_id = %s AND queued_date = CURRENT_DATE AND done = 1", (user_id,))
    today_done = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE user_id = %s AND queued_date = CURRENT_DATE", (user_id,))
    today_total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM notifications WHERE user_id = %s AND done = 0", (user_id,))
    notif_pending = c.fetchone()[0]

    conn.close()
    return {
        "total": total,
        "sent": sent,
        "pending": pending,
        "today_done": today_done,
        "today_total": today_total,
        "notif_pending": notif_pending,
    }


# ── Manager stats ─────────────────────────────────────────────────────────────

def get_all_salespersons():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, username FROM users WHERE role = 'salesperson' ORDER BY name")
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def get_team_today_stats():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT
            u.id,
            u.name,
            COALESCE(q_total.cnt, 0)   AS today_total,
            COALESCE(q_done.cnt, 0)    AS today_done,
            COALESCE(p_sent.cnt, 0)    AS total_sent,
            COALESCE(p_pending.cnt, 0) AS total_pending,
            COALESCE(n_pend.cnt, 0)    AS notif_pending
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS cnt
            FROM queue WHERE queued_date = CURRENT_DATE
            GROUP BY user_id
        ) q_total ON q_total.user_id = u.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS cnt
            FROM queue WHERE queued_date = CURRENT_DATE AND done = 1
            GROUP BY user_id
        ) q_done ON q_done.user_id = u.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS cnt
            FROM profiles WHERE status = 'sent'
            GROUP BY user_id
        ) p_sent ON p_sent.user_id = u.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS cnt
            FROM profiles WHERE status = 'pending'
            GROUP BY user_id
        ) p_pending ON p_pending.user_id = u.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS cnt
            FROM notifications WHERE done = 0
            GROUP BY user_id
        ) n_pend ON n_pend.user_id = u.id
        WHERE u.role = 'salesperson'
        ORDER BY u.name
    """)
    rows = [_row_to_dict(c, r) for r in c.fetchall()]
    conn.close()
    return rows


def get_team_week_chart_data(days=7):
    conn = get_conn()
    c = conn.cursor()

    start_date = (date.today() - timedelta(days=days - 1)).isoformat()

    c.execute("""
        SELECT u.name, q.queued_date::TEXT, COUNT(*) AS cnt
        FROM queue q
        JOIN users u ON q.user_id = u.id
        WHERE u.role = 'salesperson'
          AND q.queued_date >= %s
          AND q.done = 1
        GROUP BY u.name, q.queued_date
        ORDER BY q.queued_date ASC
    """, (start_date,))

    rows = c.fetchall()
    conn.close()

    date_strs = [(date.today() - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    labels = [(date.today() - timedelta(days=days - 1 - i)).strftime("%b %d") for i in range(days)]

    user_data = {}
    for name, queued_date, cnt in rows:
        if name not in user_data:
            user_data[name] = {d: 0 for d in date_strs}
        user_data[name][queued_date] = cnt

    colors = ['#0a66c2', '#057642', '#e7a33e', '#b24020']
    datasets = []
    for i, (name, daily) in enumerate(sorted(user_data.items())):
        datasets.append({
            'label': name,
            'data': [daily.get(d, 0) for d in date_strs],
            'backgroundColor': colors[i % len(colors)],
            'borderRadius': 4,
        })

    return {'labels': labels, 'datasets': datasets}
