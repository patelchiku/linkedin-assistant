import io
import csv
from datetime import datetime

import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, Response)

from database import (init_db, build_todays_queue, get_todays_queue,
                      mark_queue_done, add_profile, bulk_add_profiles,
                      get_all_profiles, delete_profile, add_notification,
                      get_pending_notifications, mark_notification_done,
                      delete_notification, update_notification_message,
                      get_stats)
from templates import generate_event_message

app = Flask(__name__)
app.secret_key = 'la-secret-2024-x7k9m'

with app.app_context():
    init_db()


@app.route('/')
def today():
    build_todays_queue(15)
    queue = get_todays_queue()
    stats = get_stats()
    return render_template('today.html', queue=queue, stats=stats, now=datetime.now())


@app.route('/mark-sent', methods=['POST'])
def mark_sent():
    mark_queue_done(int(request.form['queue_id']), int(request.form['profile_id']))
    flash('Marked as sent!', 'success')
    return redirect(url_for('today'))


@app.route('/add-profiles')
def add_profiles():
    return render_template('add_profiles.html')


@app.route('/add-profile', methods=['POST'])
def add_profile_route():
    ok, msg = add_profile(
        request.form['first_name'],
        request.form['last_name'],
        request.form['linkedin_url'],
        request.form.get('note', '')
    )
    flash(msg, 'success' if ok else 'danger')
    return redirect(url_for('add_profiles'))


@app.route('/bulk-upload', methods=['POST'])
def bulk_upload():
    file = request.files.get('csv_file')
    if file and file.filename:
        df = pd.read_csv(file)
        df.columns = [c.lower().strip() for c in df.columns]
        added, skipped = bulk_add_profiles(df.to_dict('records'))
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
def all_profiles():
    return render_template('all_profiles.html', profiles=get_all_profiles())


@app.route('/delete-profile', methods=['POST'])
def delete_profile_route():
    delete_profile(int(request.form['profile_id']))
    flash('Profile deleted.', 'success')
    return redirect(url_for('all_profiles'))


@app.route('/notifications')
def notifications():
    return render_template('notifications.html', notifications=get_pending_notifications())


@app.route('/add-notification', methods=['POST'])
def add_notification_route():
    add_notification(
        request.form['first_name'],
        request.form['last_name'],
        request.form['event_type'],
        request.form.get('linkedin_url', '')
    )
    flash('Notification drafted!', 'success')
    return redirect(url_for('notifications'))


@app.route('/regenerate-message', methods=['POST'])
def regenerate_message():
    new_msg = generate_event_message(request.form['first_name'], request.form['event_type'])
    update_notification_message(int(request.form['notif_id']), new_msg)
    return redirect(url_for('notifications'))


@app.route('/mark-notification-done', methods=['POST'])
def mark_notification_done_route():
    mark_notification_done(int(request.form['notif_id']))
    flash('Marked as done.', 'success')
    return redirect(url_for('notifications'))


@app.route('/delete-notification', methods=['POST'])
def delete_notification_route():
    delete_notification(int(request.form['notif_id']))
    return redirect(url_for('notifications'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
