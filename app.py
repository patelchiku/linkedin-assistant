import streamlit as st
import pandas as pd
import csv
import io
from datetime import date

from database import (
    init_db,
    build_todays_queue,
    get_todays_queue,
    mark_queue_done,
    add_profile,
    bulk_add_profiles,
    get_all_profiles,
    delete_profile,
    add_notification,
    get_pending_notifications,
    mark_notification_done,
    delete_notification,
    update_notification_message,
    get_stats,
)
from templates import get_event_label, generate_connection_message, generate_event_message

# ── Init ────────────────────────────────────────────────────────────────────

init_db()
build_todays_queue(daily_limit=15)

st.set_page_config(
    page_title="LinkedIn Assistant",
    page_icon="💼",
    layout="wide",
)

# ── Sidebar nav ─────────────────────────────────────────────────────────────

st.sidebar.title("💼 LinkedIn Assistant")
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Navigate",
    ["🏠 Today's Tasks", "➕ Add Profiles", "📋 All Profiles", "🔔 Notifications"],
)
st.sidebar.markdown("---")

stats = get_stats()
st.sidebar.metric("Total Profiles", stats["total"])
st.sidebar.metric("Sent", stats["sent"])
st.sidebar.metric("Pending", stats["pending"])
st.sidebar.metric("Notifications", stats["notif_pending"])

st.sidebar.markdown("---")
st.sidebar.caption("Safe mode: you do all the clicking on LinkedIn. This app only drafts messages.")


# ════════════════════════════════════════════════════════════════════════════
# PAGE: TODAY'S TASKS
# ════════════════════════════════════════════════════════════════════════════

if page == "🏠 Today's Tasks":
    st.title("🏠 Today's Connection Queue")
    st.caption(f"Date: {date.today().strftime('%A, %B %d %Y')}  •  Daily limit: 15 requests")

    queue = get_todays_queue()

    if not queue:
        st.info("No profiles queued for today. Add profiles in the **Add Profiles** tab.")
    else:
        done_count = sum(1 for q in queue if q["done"])
        st.progress(done_count / len(queue), text=f"{done_count} / {len(queue)} done today")
        st.markdown("")

        for q in queue:
            status_icon = "✅" if q["done"] else "⏳"
            with st.expander(
                f"{status_icon} {q['first_name']} {q['last_name']}",
                expanded=not q["done"],
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown("**LinkedIn Profile**")
                    st.markdown(f"[Open on LinkedIn ↗]({q['linkedin_url']})")

                    st.markdown("**Connection Note (copy this)**")
                    st.code(q["message"], language=None)

                    if q["note"]:
                        st.caption(f"Your note: {q['note']}")

                with col2:
                    if not q["done"]:
                        if st.button("✅ Mark as Sent", key=f"done_{q['queue_id']}"):
                            mark_queue_done(q["queue_id"], q["profile_id"])
                            st.rerun()
                    else:
                        st.success("Sent!")

    st.markdown("---")
    st.markdown("### How to send a connection request on LinkedIn")
    st.markdown(
        """
1. Click **Open on LinkedIn ↗** above
2. Click **Connect** on their profile
3. Click **Add a note**
4. Paste the message above
5. Click **Send** — then come back and mark as Sent ✅
        """
    )


# ════════════════════════════════════════════════════════════════════════════
# PAGE: ADD PROFILES
# ════════════════════════════════════════════════════════════════════════════

elif page == "➕ Add Profiles":
    st.title("➕ Add Profiles")

    tab1, tab2 = st.tabs(["Add Single Profile", "Bulk Upload CSV"])

    # ── Single add ──────────────────────────────────────────────────────────
    with tab1:
        st.markdown("#### Add one profile manually")
        with st.form("add_single"):
            col1, col2 = st.columns(2)
            with col1:
                first_name = st.text_input("First Name *")
                last_name = st.text_input("Last Name *")
            with col2:
                linkedin_url = st.text_input("LinkedIn URL *", placeholder="https://linkedin.com/in/username")
                note = st.text_input("Note (optional)", placeholder="e.g. works in AI, Mumbai")

            submitted = st.form_submit_button("Add Profile")
            if submitted:
                if not first_name or not last_name or not linkedin_url:
                    st.error("First name, last name, and LinkedIn URL are required.")
                elif "linkedin.com" not in linkedin_url:
                    st.error("Please enter a valid LinkedIn URL.")
                else:
                    ok, msg = add_profile(first_name, last_name, linkedin_url, note)
                    if ok:
                        st.success(f"Added {first_name} {last_name} to the queue!")
                    else:
                        st.warning(msg)

    # ── Bulk CSV ────────────────────────────────────────────────────────────
    with tab2:
        st.markdown("#### Bulk upload via CSV")
        st.markdown(
            """
Your CSV must have these columns (in any order):

| Column | Required | Example |
|---|---|---|
| `first_name` | Yes | Chirag |
| `last_name` | Yes | Patel |
| `linkedin_url` | Yes | https://linkedin.com/in/chiragpatel |
| `note` | No | works in fintech |
            """
        )

        # Download sample CSV
        sample = "first_name,last_name,linkedin_url,note\nJohn,Doe,https://linkedin.com/in/johndoe,works in AI\nJane,Smith,https://linkedin.com/in/janesmith,"
        st.download_button(
            "⬇️ Download Sample CSV",
            data=sample,
            file_name="sample_profiles.csv",
            mime="text/csv",
        )

        uploaded = st.file_uploader("Upload your CSV", type=["csv"])
        if uploaded:
            try:
                content = uploaded.read().decode("utf-8")
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)

                # Validate columns
                required_cols = {"first_name", "last_name", "linkedin_url"}
                if not required_cols.issubset(set(reader.fieldnames or [])):
                    st.error(f"CSV must have columns: {', '.join(required_cols)}")
                else:
                    # Preview
                    df = pd.DataFrame(rows)
                    st.dataframe(df, use_container_width=True)

                    if st.button(f"Import {len(rows)} profiles"):
                        added, skipped = bulk_add_profiles(rows)
                        st.success(f"Imported {added} profiles. Skipped {skipped} duplicates.")

            except Exception as e:
                st.error(f"Could not read CSV: {e}")


# ════════════════════════════════════════════════════════════════════════════
# PAGE: ALL PROFILES
# ════════════════════════════════════════════════════════════════════════════

elif page == "📋 All Profiles":
    st.title("📋 All Profiles")

    profiles = get_all_profiles()

    if not profiles:
        st.info("No profiles yet. Go to **Add Profiles** to get started.")
    else:
        # Filter
        status_filter = st.selectbox("Filter by status", ["All", "pending", "sent"])

        filtered = profiles
        if status_filter != "All":
            filtered = [p for p in profiles if p["status"] == status_filter]

        st.caption(f"Showing {len(filtered)} of {len(profiles)} profiles")

        for p in filtered:
            status_badge = "⏳ Pending" if p["status"] == "pending" else "✅ Sent"
            with st.expander(f"{status_badge}  {p['first_name']} {p['last_name']}"):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"**LinkedIn:** [{p['linkedin_url']}]({p['linkedin_url']})")
                    if p["note"]:
                        st.markdown(f"**Note:** {p['note']}")
                with col2:
                    st.markdown(f"**Added:** {p['added_on']}")
                    if p["sent_on"]:
                        st.markdown(f"**Sent:** {p['sent_on']}")
                    # Preview message
                    msg = generate_connection_message(p["first_name"], p["note"])
                    st.code(msg, language=None)
                with col3:
                    if st.button("🗑️ Delete", key=f"del_{p['id']}"):
                        delete_profile(p["id"])
                        st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# PAGE: NOTIFICATIONS
# ════════════════════════════════════════════════════════════════════════════

elif page == "🔔 Notifications":
    st.title("🔔 Notifications")
    st.markdown(
        "Log birthdays, work anniversaries, new jobs, and promotions here. "
        "The system drafts a message — you copy and send it on LinkedIn."
    )

    tab1, tab2 = st.tabs(["➕ Add Notification", "📬 Pending Messages"])

    # ── Add notification ────────────────────────────────────────────────────
    with tab1:
        st.markdown("#### Add a notification from LinkedIn")
        st.info(
            "Open LinkedIn Notifications, find the event (birthday, anniversary, etc.), "
            "and fill in the details below."
        )

        with st.form("add_notif"):
            col1, col2 = st.columns(2)
            with col1:
                n_first = st.text_input("First Name *")
                n_last = st.text_input("Last Name *")
                n_url = st.text_input("LinkedIn URL (optional)")
            with col2:
                event_type = st.selectbox(
                    "Event Type *",
                    options=["birthday", "work_anniversary", "new_job", "promotion"],
                    format_func=get_event_label,
                )
                event_date = st.date_input("Event Date", value=date.today())

            submitted = st.form_submit_button("Add & Draft Message")
            if submitted:
                if not n_first or not n_last:
                    st.error("First name and last name are required.")
                else:
                    add_notification(n_first, n_last, event_type, n_url, event_date.isoformat())
                    st.success(f"Added! Message drafted for {n_first} {n_last}.")

    # ── Pending messages ────────────────────────────────────────────────────
    with tab2:
        notifications = get_pending_notifications()

        if not notifications:
            st.info("No pending notifications. Add one in the **Add Notification** tab.")
        else:
            st.caption(f"{len(notifications)} pending")
            for n in notifications:
                event_label = get_event_label(n["event_type"])
                with st.expander(
                    f"🎉 {event_label} — {n['first_name']} {n['last_name']}  ({n['event_date']})"
                ):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if n["linkedin_url"]:
                            st.markdown(f"**Profile:** [{n['linkedin_url']}]({n['linkedin_url']})")
                        st.markdown("**Drafted Message (copy this)**")
                        st.code(n["drafted_message"], language=None)

                        # Regenerate option
                        if st.button("🔄 Regenerate message", key=f"regen_{n['id']}"):
                            new_msg = generate_event_message(n["first_name"], n["event_type"])
                            update_notification_message(n["id"], new_msg)
                            st.rerun()

                    with col2:
                        if st.button("✅ Mark Done", key=f"notif_done_{n['id']}"):
                            mark_notification_done(n["id"])
                            st.rerun()
                        if st.button("🗑️ Delete", key=f"notif_del_{n['id']}"):
                            delete_notification(n["id"])
                            st.rerun()
