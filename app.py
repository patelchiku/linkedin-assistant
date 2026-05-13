import io
import csv
from datetime import datetime
from functools import wraps

import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, Response, session)

from database import (
    init_db, build_todays_queue, get_todays_queue, mark_queue_done,
    add_profile, bulk_add_profiles, get_all_profiles, delete_profile,
    add_notification, get_pending_notifications, mark_notification_done,
    delete_notification, update_notification_message, get_stats,
    verify_login, get_user_by_id,
    get_team_today_stats, get_team_week_chart_data,
)
from templates import generate_event_message

app = Flask(__name__)
app.secret_key = 'la-secret-2024-x7k9m'

with app.app_context():
    init_db()


# ── Auth guards ───────────────────────────────────────────────────────────────

PUBLIC_ENDPOINTS = {'login', 'static'}


@app.before_request
def require_login():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if 'user_id' not in session:
        return redirect(url_for('login'))


def manager_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'manager':
            flash('Access denied.', 'danger')
            return redirect(url_for('today'))
        return f(*args, **kwargs)
    return decorated


def salesperson_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'salesperson':
            return redirect(url_for('manager_dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        dest = 'today' if session['role'] == 'salesperson' else 'manager_dashboard'
        return redirect(url_for(dest))

    if request.method == 'POST':
        user = verify_login(request.form['username'].strip().lower(), request.form['password'])
        if user:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['name'] = user['name']
            session['role'] = user['role']
            dest = 'today' if user['role'] == 'salesperson' else 'manager_dashboard'
            return redirect(url_for(dest))
        flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Salesperson routes ────────────────────────────────────────────────────────

@app.route('/')
@salesperson_only
def today():
    uid = session['user_id']
    build_todays_queue(uid, 15)
    queue = get_todays_queue(uid)
    stats = get_stats(uid)
    return render_template('today.html', queue=queue, stats=stats, now=datetime.now())


@app.route('/mark-sent', methods=['POST'])
@salesperson_only
def mark_sent():
    mark_queue_done(int(request.form['queue_id']), int(request.form['profile_id']))
    flash('Marked as sent!', 'success')
    return redirect(url_for('today'))


@app.route('/add-profiles')
@salesperson_only
def add_profiles():
    return render_template('add_profiles.html')


@app.route('/add-profile', methods=['POST'])
@salesperson_only
def add_profile_route():
    ok, msg = add_profile(
        session['user_id'],
        request.form['first_name'],
        request.form['last_name'],
        request.form['linkedin_url'],
        request.form.get('note', ''),
    )
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('add_profiles'))


@app.route('/bulk-upload', methods=['POST'])
@salesperson_only
def bulk_upload():
    file = request.files.get('csv_file')
    if file and file.filename:
        df = pd.read_csv(file)
        df.columns = [c.lower().strip() for c in df.columns]
        added, skipped = bulk_add_profiles(session['user_id'], df.to_dict('records'))
        flash(f'Added {added} profiles. Skipped {skipped} duplicates.', 'success')
    return redirect(url_for('add_profiles'))


@app.route('/download-sample')
def download_sample():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'linkedin_url', 'note'])
    writer.writerow(['Jane', 'Doe', 'https://linkedin.com/in/janedoe', 'Met at conference'])
    writer.writerow(['John', 'Smith', 'https://linkedin.com/in/johnsmith', ''])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=sample_profiles.csv'})


@app.route('/all-profiles')
@salesperson_only
def all_profiles():
    return render_template('all_profiles.html', profiles=get_all_profiles(session['user_id']))


@app.route('/delete-profile', methods=['POST'])
@salesperson_only
def delete_profile_route():
    delete_profile(int(request.form['profile_id']))
    flash('Profile deleted.', 'success')
    return redirect(url_for('all_profiles'))


@app.route('/notifications')
@salesperson_only
def notifications():
    return render_template('notifications.html',
                           notifications=get_pending_notifications(session['user_id']))


@app.route('/add-notification', methods=['POST'])
@salesperson_only
def add_notification_route():
    add_notification(
        session['user_id'],
        request.form['first_name'],
        request.form['last_name'],
        request.form['event_type'],
        request.form.get('linkedin_url', ''),
    )
    flash('Notification drafted!', 'success')
    return redirect(url_for('notifications'))


@app.route('/regenerate-message', methods=['POST'])
@salesperson_only
def regenerate_message():
    new_msg = generate_event_message(request.form['first_name'], request.form['event_type'])
    update_notification_message(int(request.form['notif_id']), new_msg)
    return redirect(url_for('notifications'))


@app.route('/mark-notification-done', methods=['POST'])
@salesperson_only
def mark_notification_done_route():
    mark_notification_done(int(request.form['notif_id']))
    flash('Marked as done.', 'success')
    return redirect(url_for('notifications'))


@app.route('/delete-notification', methods=['POST'])
@salesperson_only
def delete_notification_route():
    delete_notification(int(request.form['notif_id']))
    return redirect(url_for('notifications'))


# ── Manager routes ────────────────────────────────────────────────────────────

@app.route('/dashboard')
@manager_only
def manager_dashboard():
    team_stats = get_team_today_stats()
    chart_data = get_team_week_chart_data(7)
    return render_template('manager_dashboard.html',
                           team_stats=team_stats,
                           chart_data=chart_data,
                           now=datetime.now())


@app.route('/dashboard/user/<int:uid>')
@manager_only
def manager_user_detail(uid):
    user = get_user_by_id(uid)
    if not user or user['role'] != 'salesperson':
        flash('User not found.', 'danger')
        return redirect(url_for('manager_dashboard'))
    queue = get_todays_queue(uid)
    stats = get_stats(uid)
    return render_template('manager_user_detail.html',
                           viewed_user=user,
                           queue=queue,
                           stats=stats,
                           now=datetime.now())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
