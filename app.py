import io
import csv
import calendar as cal_module
from datetime import datetime, date, timedelta
from functools import wraps

import pandas as pd
from flask import (Flask, render_template, request, redirect,
                   url_for, flash, Response, session)

from database import (
    init_db, build_todays_queue, get_todays_queue, mark_queue_done,
    add_profile, add_contacts_to_user, get_all_profiles, delete_profile,
    add_notification, get_pending_notifications, mark_notification_done,
    delete_notification, update_notification_message, get_stats,
    verify_login, get_user_by_id,
    get_team_today_stats, get_team_week_chart_data,
    get_daily_report, get_period_stats,
    get_all_salespersons,
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
    is_weekend = datetime.now().weekday() >= 5
    build_todays_queue(uid, 15)
    queue = get_todays_queue(uid)
    stats = get_stats(uid)
    return render_template('today.html', queue=queue, stats=stats,
                           now=datetime.now(), is_weekend=is_weekend)


@app.route('/mark-sent', methods=['POST'])
@salesperson_only
def mark_sent():
    mark_queue_done(int(request.form['queue_id']), int(request.form['profile_id']))
    flash('Marked as sent!', 'success')
    return redirect(url_for('today'))




@app.route('/my-contacts')
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

@app.route('/manager/upload', methods=['GET', 'POST'])
@manager_only
def manager_upload():
    salespersons = get_all_salespersons()
    team_stats   = get_team_today_stats()

    if request.method == 'POST':
        try:
            assign_to_id = int(request.form['assign_to'])
            file = request.files.get('csv_file')
            if not file or not file.filename:
                flash('Please select a CSV file.', 'warning')
                return redirect(url_for('manager_upload'))

            df = pd.read_csv(file)
            df.columns = [c.lower().strip() for c in df.columns]
            df = df.fillna('')          # ← fixes NaN → 'nan' string bug

            added, skipped = add_contacts_to_user(assign_to_id, df.to_dict('records'))
            sp_name = next((sp['name'] for sp in salespersons if sp['id'] == assign_to_id), 'Unknown')
            flash(
                f'Added {added} contacts to {sp_name}.'
                f'{" " + str(skipped) + " skipped (duplicates or missing data)." if skipped else ""}',
                'success' if added else 'warning',
            )
        except Exception as e:
            flash(f'Upload failed: {e}', 'danger')

        return redirect(url_for('manager_upload'))

    return render_template('manager_upload.html',
                           salespersons=salespersons,
                           team_stats=team_stats)


@app.route('/manager/download-sample')
@manager_only
def manager_download_sample():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['first_name', 'last_name', 'linkedin_url', 'source'])
    writer.writerow(['Jane', 'Doe', 'https://linkedin.com/in/janedoe', 'LinkedIn Search'])
    writer.writerow(['John', 'Smith', 'https://linkedin.com/in/johnsmith', 'Conference - BLR 2025'])
    writer.writerow(['Priya', 'Kumar', 'https://linkedin.com/in/priyakumar', 'Referral'])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=contacts_template.csv'})

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


# ── Report helpers ────────────────────────────────────────────────────────────

DAILY_LIMIT = 15
_PERSON_COLORS = {'Aaryan': '#0a66c2', 'Palak': '#057642', 'Piyush': '#e7a33e'}


def _prev_working_day(d):
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _next_working_day(d):
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _build_weekly_data(week_monday, week_friday, today_utc):
    days = [week_monday + timedelta(days=i) for i in range(5)]
    raw = get_period_stats(week_monday.isoformat(), week_friday.isoformat())

    by_person = {}
    for name, date_str, sent in raw:
        by_person.setdefault(name, {})[date_str] = sent

    persons = []
    for name in sorted(by_person):
        daily = [
            by_person[name].get(d.isoformat(), 0) if d <= today_utc else None
            for d in days
        ]
        persons.append({
            'name': name,
            'daily': daily,
            'total': sum(s for s in daily if s is not None),
        })

    team_daily = [
        sum(p['daily'][i] or 0 for p in persons) if days[i] <= today_utc else None
        for i in range(5)
    ]

    chart_datasets = [{
        'label': p['name'],
        'data': [s if s is not None else 0 for s in p['daily']],
        'backgroundColor': _PERSON_COLORS.get(p['name'], '#888'),
        'borderRadius': 4,
    } for p in persons]

    return {
        'week_monday': week_monday,
        'week_friday': week_friday,
        'days': days,
        'day_labels': [d.strftime('%a, %b ') + str(d.day) for d in days],
        'persons': persons,
        'team_daily': team_daily,
        'team_total': sum(t or 0 for t in team_daily),
        'max_per_day': DAILY_LIMIT * len(persons),
        'chart_data': {
            'labels': [d.strftime('%a ') + str(d.day) for d in days],
            'datasets': chart_datasets,
        },
    }


def _build_monthly_data(year, month, today_utc):
    first_day = date(year, month, 1)
    last_day = date(year, month, cal_module.monthrange(year, month)[1])
    raw = get_period_stats(first_day.isoformat(), last_day.isoformat())

    by_person = {}
    for name, date_str, sent in raw:
        by_person.setdefault(name, {})[date_str] = sent

    # All working days in the month
    working_days = [
        first_day + timedelta(days=i)
        for i in range((last_day - first_day).days + 1)
        if (first_day + timedelta(days=i)).weekday() < 5
    ]
    past_days = [d for d in working_days if d <= today_utc]

    # Group into calendar weeks
    weeks = []
    for d in working_days:
        week_label = 'Week of ' + (d - timedelta(days=d.weekday())).strftime('%b ') + \
                     str((d - timedelta(days=d.weekday())).day)
        if not weeks or weeks[-1]['label'] != week_label:
            weeks.append({'label': week_label, 'days': [], 'totals': {}, 'team': 0})
        weeks[-1]['days'].append(d)

    for w in weeks:
        for d in w['days']:
            ds = d.isoformat()
            for name in by_person:
                w['totals'][name] = w['totals'].get(name, 0) + by_person[name].get(ds, 0)
        w['team'] = sum(w['totals'].values())
        w['is_future'] = all(d > today_utc for d in w['days'])
        w['is_partial'] = not w['is_future'] and any(d > today_utc for d in w['days'])

    # Per-person summary
    persons = []
    for name in sorted(by_person):
        total = sum(by_person[name].get(d.isoformat(), 0) for d in past_days)
        max_possible = DAILY_LIMIT * len(working_days)
        days_active = sum(1 for d in past_days if by_person[name].get(d.isoformat(), 0) > 0)
        avg = round(total / max(len(past_days), 1), 1)
        persons.append({
            'name': name,
            'total': total,
            'avg': avg,
            'days_active': days_active,
            'max_possible': max_possible,
            'pct': min(round(total / max(max_possible, 1) * 100), 100),
        })

    # Cumulative line chart
    chart_labels = [d.strftime('%b ') + str(d.day) for d in past_days]
    chart_datasets = []
    for name in sorted(by_person):
        running, data = 0, []
        for d in past_days:
            running += by_person[name].get(d.isoformat(), 0)
            data.append(running)
        chart_datasets.append({
            'label': name,
            'data': data,
            'borderColor': _PERSON_COLORS.get(name, '#888'),
            'backgroundColor': 'transparent',
            'tension': 0.3,
            'pointRadius': 2,
        })

    return {
        'month_name': first_day.strftime('%B %Y'),
        'year': year, 'month': month,
        'working_days_total': len(working_days),
        'past_days': len(past_days),
        'weeks': weeks,
        'persons': persons,
        'chart_data': {'labels': chart_labels, 'datasets': chart_datasets},
    }


@app.route('/manager/reports')
@manager_only
def manager_reports():
    today_utc = date.today()
    view = request.args.get('view', 'daily')

    # ── Daily ──
    date_str = request.args.get('date', today_utc.isoformat())
    try:
        report_date = date.fromisoformat(date_str)
    except ValueError:
        report_date = today_utc

    is_weekend = report_date.weekday() >= 5
    prev_date = _prev_working_day(report_date)
    next_date = _next_working_day(report_date)
    can_go_next = next_date <= today_utc

    daily_data = get_daily_report(report_date.isoformat()) if not is_weekend else []

    # ── Weekly ──
    week_offset = int(request.args.get('week_offset', 0))
    this_monday = today_utc - timedelta(days=today_utc.weekday())
    week_monday = this_monday + timedelta(weeks=week_offset)
    week_friday = week_monday + timedelta(days=4)
    weekly_data = _build_weekly_data(week_monday, week_friday, today_utc)

    # ── Monthly ──
    month_offset = int(request.args.get('month_offset', 0))
    # Compute target year/month
    total_months = today_utc.year * 12 + (today_utc.month - 1) + month_offset
    target_year = total_months // 12
    target_month = total_months % 12 + 1
    monthly_data = _build_monthly_data(target_year, target_month, today_utc)

    return render_template('manager_reports.html',
                           view=view,
                           today_utc=today_utc,
                           report_date=report_date,
                           is_weekend=is_weekend,
                           prev_date=prev_date.isoformat(),
                           next_date=next_date.isoformat(),
                           can_go_next=can_go_next,
                           daily_data=daily_data,
                           daily_limit=DAILY_LIMIT,
                           week_offset=week_offset,
                           weekly_data=weekly_data,
                           month_offset=month_offset,
                           monthly_data=monthly_data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
