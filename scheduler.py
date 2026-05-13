"""
Run this once daily (e.g. on system startup or via Task Scheduler) to
build today's connection queue. The Streamlit app also calls this
automatically when you open the Today tab.

Usage:
    python scheduler.py
"""

from database import init_db, build_todays_queue


def run():
    init_db()
    added = build_todays_queue(daily_limit=15)
    if added:
        print(f"✅ Queued {added} profiles for today.")
    else:
        print("ℹ️  Today's queue already exists or no pending profiles.")


if __name__ == "__main__":
    run()
