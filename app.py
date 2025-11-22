from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify  # Added jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash  # For secure passwords (optional)
from werkzeug.utils import secure_filename
import calendar
import datetime
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a random string for security

# Hardcoded Admin credentials (change these as needed)
ADMIN_ID = 'admin'
ADMIN_PASSWORD = 'admin123'

# Function to connect to DB
def get_db_connection():
    conn = sqlite3.connect('attendance_tracker.db')
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

# Home/Login page
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_type = request.form['user_type']  # 'teacher', 'student', or 'admin'
        user_id = request.form['user_id']
        password = request.form['password']
        
        if user_type == 'admin':
            # Check hardcoded admin credentials
            if user_id == ADMIN_ID and password == ADMIN_PASSWORD:
                session['user_id'] = ADMIN_ID
                session['user_type'] = 'admin'
                session['name'] = 'Admin'
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Invalid admin credentials!')
        else:
            conn = get_db_connection()
            if user_type == 'teacher':
                # Optional: Improved query for varying passwords
                teacher = conn.execute('SELECT DISTINCT T_id, T_name FROM Teacher WHERE T_id = ? AND password = ?', (user_id, password)).fetchone()
                if teacher:
                    session['user_id'] = teacher['T_id']
                    session['user_type'] = 'teacher'
                    session['name'] = teacher['T_name']
                    return redirect(url_for('teacher_dashboard'))
            elif user_type == 'student':
                student = conn.execute('SELECT * FROM Student WHERE S_id = ? AND password = ?', (user_id, password)).fetchone()
                if student:
                    session['user_id'] = student['S_id']
                    session['user_type'] = 'student'
                    session['name'] = student['S_name']
                    return redirect(url_for('student_dashboard'))
            conn.close()
            flash('Invalid credentials!')
    return render_template('login.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_type' not in session or session['user_type'] not in ['teacher', 'student']:
        return redirect(url_for('login'))
    
    user_type = session['user_type']
    user_id = session['user_id']
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Validate new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match!')
            return redirect(url_for('change_password'))
        
        # Validate new password is not empty
        if not new_password.strip():
            flash('New password cannot be empty!')
            return redirect(url_for('change_password'))
        
        conn = get_db_connection()
        
        # Verify old password
        if user_type == 'teacher':
            teacher = conn.execute('SELECT password FROM Teacher WHERE T_id = ? LIMIT 1', (user_id,)).fetchone()
            if not teacher or teacher['password'] != old_password:
                conn.close()
                flash('Old password is incorrect!')
                return redirect(url_for('change_password'))
            # Update password for all rows of this T_id
            conn.execute('UPDATE Teacher SET password = ? WHERE T_id = ?', (new_password, user_id))
        elif user_type == 'student':
            student = conn.execute('SELECT password FROM Student WHERE S_id = ?', (user_id,)).fetchone()
            if not student or student['password'] != old_password:
                conn.close()
                flash('Old password is incorrect!')
                return redirect(url_for('change_password'))
            # Update password for the student
            conn.execute('UPDATE Student SET password = ? WHERE S_id = ?', (new_password, user_id))
        
        conn.commit()
        conn.close()
        flash('Password updated successfully!')
        return redirect(url_for(user_type + '_dashboard'))
    
    return render_template('change_password.html')

# Teacher Dashboard (enhanced)
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Fetch all departments, semesters and subjects assigned to this teacher
    rows = conn.execute('''
        SELECT DISTINCT Teacher.Depart_id, Department.Depart_name, Teacher.Sem, Teacher.Subject
        FROM Teacher
        LEFT JOIN Department ON Teacher.Depart_id = Department.Depart_id AND Teacher.Sem = Department.Sem
        WHERE Teacher.T_id = ?
        ORDER BY Teacher.Depart_id ASC, Teacher.Sem ASC
    ''', (session['user_id'],)).fetchall()

    # Group by Depart_id -> sem -> subjects
    grouped_departments = {}
    for row in rows:
        dep_id = row['Depart_id']
        dep_name = row['Depart_name'] or ''
        sem = row['Sem']
        subject = row['Subject']

        if dep_id not in grouped_departments:
            grouped_departments[dep_id] = {'Depart_name': dep_name, 'sems': {}}
        # Ensure depart name is set (in case of multiple rows)
        if not grouped_departments[dep_id]['Depart_name'] and dep_name:
            grouped_departments[dep_id]['Depart_name'] = dep_name

        if sem not in grouped_departments[dep_id]['sems']:
            grouped_departments[dep_id]['sems'][sem] = []
        if subject not in grouped_departments[dep_id]['sems'][sem]:
            grouped_departments[dep_id]['sems'][sem].append(subject)

    conn.close()
    return render_template('teacher_dashboard.html', grouped_departments=grouped_departments)

# Mark Attendance Page
@app.route('/mark_attendance/<subject>/<sem>', methods=['GET', 'POST'])
def mark_attendance(subject, sem):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Verify the subject/sem belongs to the teacher
    teacher_check = conn.execute('SELECT 1 FROM Teacher WHERE T_id = ? AND Subject = ? AND Sem = ?', (session['user_id'], subject, sem)).fetchone()
    if not teacher_check:
        flash('Unauthorized access!')
        conn.close()
        return redirect(url_for('teacher_dashboard'))
    
    # Get department name
    depart_info = conn.execute('''
        SELECT DISTINCT Department.Depart_name
        FROM Teacher
        JOIN Department ON Teacher.Depart_id = Department.Depart_id
        WHERE Teacher.T_id = ? AND Teacher.Subject = ? AND Teacher.Sem = ?
    ''', (session['user_id'], subject, sem)).fetchone()
    
    # Get students for this depart_id and sem
    depart_id = conn.execute('SELECT Depart_id FROM Teacher WHERE T_id = ? AND Subject = ? AND Sem = ?', (session['user_id'], subject, sem)).fetchone()['Depart_id']
    students = conn.execute('SELECT S_id, S_name FROM Student WHERE Depart_id = ? AND Sem = ?', (depart_id, sem)).fetchall()
    # Normalize to list of dicts and sort by S_id ascending.
    # Sorting strategy: numeric IDs (all digits) are sorted numerically first, then non-numeric IDs sorted lexicographically.
    students = [dict(s) for s in students]
    def student_sort_key(s):
        sid = str(s.get('S_id', ''))
        if sid.isdigit():
            return (0, int(sid))
        return (1, sid.lower())
    students.sort(key=student_sort_key)
        
    if request.method == 'POST':
        date = request.form['date']
        if not date:
            flash('Please select a date!')
            return redirect(request.url)
        
        # Update attendance for each student
        for student in students:
            status = request.form.get(f'status_{student["S_id"]}', 'Absent')
            conn.execute('INSERT OR REPLACE INTO Attendance (S_id, T_id, Date, Subject, Status) VALUES (?, ?, ?, ?, ?)',
                         (student['S_id'], session['user_id'], date, subject, status))
        conn.commit()
        flash('Attendance marked successfully!')
        return redirect(url_for('teacher_dashboard'))
    
    conn.close()
    return render_template('mark_attendance.html', depart_info=depart_info, subject=subject, sem=sem, students=students)


@app.route('/teacher/get_attendance/<subject>/<sem>/<date>')
def get_attendance(subject, sem, date):
    # Return attendance records for the logged-in teacher for a given subject, sem and date
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    # Verify the teacher actually teaches this subject and sem
    teacher_check = conn.execute('SELECT 1 FROM Teacher WHERE T_id = ? AND Subject = ? AND Sem = ?', (session['user_id'], subject, sem)).fetchone()
    if not teacher_check:
        conn.close()
        return jsonify({'error': 'Unauthorized'}), 403

    rows = conn.execute('SELECT S_id, Status FROM Attendance WHERE T_id = ? AND Subject = ? AND Date = ?', (session['user_id'], subject, date)).fetchall()
    conn.close()
    return jsonify([{'S_id': r['S_id'], 'Status': r['Status']} for r in rows])

# Low Attendance Page
@app.route('/low_attendance/<subject>/<sem>', methods=['GET', 'POST'])
def low_attendance(subject, sem):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return redirect(url_for('login'))

    conn = get_db_connection()
    # Verify the subject/sem belongs to the teacher
    teacher_check = conn.execute('SELECT 1 FROM Teacher WHERE T_id = ? AND Subject = ? AND Sem = ?', (session['user_id'], subject, sem)).fetchone()
    if not teacher_check:
        flash('Unauthorized access!')
        conn.close()
        return redirect(url_for('teacher_dashboard'))

    # Get department name
    depart_info = conn.execute('''
        SELECT DISTINCT Department.Depart_name
        FROM Teacher
        JOIN Department ON Teacher.Depart_id = Department.Depart_id
        WHERE Teacher.T_id = ? AND Teacher.Subject = ? AND Teacher.Sem = ?
    ''', (session['user_id'], subject, sem)).fetchone()

    # Get students for this depart_id and sem
    depart_id = conn.execute('SELECT Depart_id FROM Teacher WHERE T_id = ? AND Subject = ? AND Sem = ?', (session['user_id'], subject, sem)).fetchone()['Depart_id']
    students = conn.execute('SELECT S_id, S_name FROM Student WHERE Depart_id = ? AND Sem = ?', (depart_id, sem)).fetchall()

    # Calculate attendance for each student
    low_attendance_students = []
    for student in students:
        s_id = student['S_id']
        # Total classes: count all attendance records for this student in this subject
        total_classes = conn.execute('SELECT COUNT(*) FROM Attendance WHERE S_id = ? AND Subject = ?', (s_id, subject)).fetchone()[0]
        if total_classes == 0:
            continue
        # Present count
        present_count = conn.execute('SELECT COUNT(*) FROM Attendance WHERE S_id = ? AND Subject = ? AND Status = "Present"', (s_id, subject)).fetchone()[0]
        # Approved absents
        approved_count = conn.execute('SELECT COUNT(*) FROM Attendance WHERE S_id = ? AND Subject = ? AND Status = "Absent" AND action_taken = "Approved"', (s_id, subject)).fetchone()[0]
        # Percentage
        percentage = ((present_count + approved_count) / total_classes) * 100
        if percentage < 75:
            # Get absent records
            absents = conn.execute('SELECT Date, reason, proof, action_taken, read_status FROM Attendance WHERE S_id = ? AND Subject = ? AND Status = "Absent"', (s_id, subject)).fetchall()
            absents_list = [{'date': a['Date'], 'reason': a['reason'], 'proof': a['proof'], 'action_taken': a['action_taken'], 'read_status': a['read_status']} for a in absents]
            # Group by action_taken and sort by action_taken ASC, then by date ASC
            absents_list.sort(key=lambda x: (x['action_taken'] or '', x['date']))
            # Check if any absence has reason or proof and is unread
            has_reason = any((a['reason'] or a['proof']) and a['read_status'] == 0 for a in absents_list)
            low_attendance_students.append({
                'S_id': s_id,
                'S_name': student['S_name'],
                'percentage': round(percentage, 2),
                'absents': absents_list,
                'has_reason': has_reason
            })

    # Mark these absences as read for the students (teacher has reviewed them)
    s_ids = [student['S_id'] for student in low_attendance_students]
    if s_ids:
        placeholders = ','.join('?' * len(s_ids))
        conn.execute(f'UPDATE Attendance SET read_status = 1 WHERE S_id IN ({placeholders}) AND Subject = ? AND Status = "Absent"', s_ids + [subject])
        conn.commit()

    conn.close()
    return render_template('low_attendance.html', depart_info=depart_info, subject=subject, sem=sem, low_attendance_students=low_attendance_students)

# Action routes for low attendance
@app.route('/approve_absent/<s_id>/<subject>/<date>', methods=['POST'])
def approve_absent(s_id, subject, date):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    # Verify the record exists and is absent
    record = conn.execute('SELECT * FROM Attendance WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (s_id, subject, date)).fetchone()
    if not record:
        conn.close()
        return jsonify({'error': 'Record not found or not absent'}), 404

    conn.execute('UPDATE Attendance SET action_taken = "Approved" WHERE S_id = ? AND Subject = ? AND Date = ?', (s_id, subject, date))
    # Insert notification
    conn.execute('INSERT INTO Notifications (S_id, message, date) VALUES (?, ?, ?)', (s_id, f'Your absence on {date} for {subject} has been approved.', datetime.datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/reject_absent/<s_id>/<subject>/<date>', methods=['POST'])
def reject_absent(s_id, subject, date):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    record = conn.execute('SELECT * FROM Attendance WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (s_id, subject, date)).fetchone()
    if not record:
        conn.close()
        return jsonify({'error': 'Record not found or not absent'}), 404

    conn.execute('UPDATE Attendance SET action_taken = "Reject" WHERE S_id = ? AND Subject = ? AND Date = ?', (s_id, subject, date))
    conn.execute('INSERT INTO Notifications (S_id, message, date) VALUES (?, ?, ?)', (s_id, f'Your absence on {date} for {subject} has been rejected.', datetime.datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/meet_me/<s_id>/<subject>/<date>', methods=['POST'])
def meet_me(s_id, subject, date):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    record = conn.execute('SELECT * FROM Attendance WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (s_id, subject, date)).fetchone()
    if not record:
        conn.close()
        return jsonify({'error': 'Record not found or not absent'}), 404

    conn.execute('UPDATE Attendance SET action_taken = "Meet Me" WHERE S_id = ? AND Subject = ? AND Date = ?', (s_id, subject, date))
    conn.execute('INSERT INTO Notifications (S_id, message, date) VALUES (?, ?, ?)', (s_id, f'You are requested to meet the teacher regarding your absence on {date} for {subject}.', datetime.datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/ask_reason/<s_id>/<subject>/<date>', methods=['POST'])
def ask_reason(s_id, subject, date):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    record = conn.execute('SELECT * FROM Attendance WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (s_id, subject, date)).fetchone()
    if not record:
        conn.close()
        return jsonify({'error': 'Record not found or not absent'}), 404

    conn.execute('UPDATE Attendance SET action_taken = "Ask Reason" WHERE S_id = ? AND Subject = ? AND Date = ?', (s_id, subject, date))
    conn.execute('INSERT INTO Notifications (S_id, message, date) VALUES (?, ?, ?)', (s_id, f'Please provide a reason for your absence on {date} for {subject}.', datetime.datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/ask_reason_all/<subject>/<sem>', methods=['POST'])
def ask_reason_all(subject, sem):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    s_id = data.get('s_id')
    if not s_id:
        return jsonify({'error': 'Student ID required'}), 400

    conn = get_db_connection()
    # Update records where action_taken is NULL for this student
    updated = conn.execute('UPDATE Attendance SET action_taken = "Ask Reason" WHERE S_id = ? AND Subject = ? AND Status = "Absent" AND action_taken IS NULL', (s_id, subject)).rowcount
    if updated > 0:
        conn.execute('INSERT INTO Notifications (S_id, message, date) VALUES (?, ?, ?)', (s_id, f'Please provide reasons for all your absences in {subject}.', datetime.datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/mark_read/<s_id>/<subject>', methods=['POST'])
def mark_read(s_id, subject):
    if 'user_type' not in session or session['user_type'] != 'teacher':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    conn.execute('UPDATE Attendance SET read_status = 1 WHERE S_id = ? AND Subject = ? AND Status = "Absent"', (s_id, subject))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/update_reason/<s_id>/<subject>/<date>', methods=['POST'])
def update_reason(s_id, subject, date):
    if 'user_type' not in session or session['user_type'] != 'student':
        return jsonify({'error': 'Unauthorized'}), 403

    reason = request.form.get('reason', '')
    proof_filename = None

    if 'proof' in request.files:
        file = request.files['proof']
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join('static', 'uploads', filename)
            file.save(file_path)
            proof_filename = f'uploads/{filename}'

    conn = get_db_connection()
    # Update the reason and proof for the specific absence
    if proof_filename:
        conn.execute('UPDATE Attendance SET reason = ?, proof = ? WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (reason, proof_filename, s_id, subject, date))
    else:
        conn.execute('UPDATE Attendance SET reason = ? WHERE S_id = ? AND Subject = ? AND Date = ? AND Status = "Absent"', (reason, s_id, subject, date))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/get_notification_count')
def get_notification_count():
    if 'user_type' not in session or session['user_type'] != 'student':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    notification_count = conn.execute('SELECT COUNT(*) FROM Notifications WHERE S_id = ? AND read_status = 0', (session['user_id'],)).fetchone()[0]
    conn.close()
    return jsonify({'count': notification_count})

@app.route('/get_notifications_json')
def get_notifications_json():
    if 'user_type' not in session or session['user_type'] != 'student':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    absences = conn.execute('SELECT Date, Subject, action_taken, reason, proof FROM Attendance WHERE S_id = ? AND Status = "Absent" AND action_taken IN ("Ask Reason", "Approved", "Reject", "Meet Me") ORDER BY Subject ASC, Date ASC', (session['user_id'],)).fetchall()
    # Mark these notifications as read
    conn.execute('UPDATE Attendance SET read_status = 1 WHERE S_id = ? AND Status = "Absent" AND action_taken IN ("Ask Reason", "Approved", "Reject", "Meet Me")', (session['user_id'],))
    # Also mark notifications in Notifications table as read
    conn.execute('UPDATE Notifications SET read_status = 1 WHERE S_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()

    # Group by subject
    grouped_absences = {}
    for absence in absences:
        subj = absence['Subject']
        if subj not in grouped_absences:
            grouped_absences[subj] = []
        grouped_absences[subj].append({
            'Date': absence['Date'],
            'Subject': absence['Subject'],
            'action_taken': absence['action_taken'],
            'reason': absence['reason'],
            'proof': absence['proof']
        })

    return jsonify(grouped_absences)

# Route to get student notifications
@app.route('/get_notifications')
def get_notifications():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))

    conn = get_db_connection()
    absences = conn.execute('SELECT Date, Subject, action_taken, reason, proof FROM Attendance WHERE S_id = ? AND Status = "Absent" AND action_taken IN ("Ask Reason", "Approved", "Reject", "Meet Me") ORDER BY Subject ASC, Date ASC', (session['user_id'],)).fetchall()
    # Mark these notifications as read
    conn.execute('UPDATE Attendance SET read_status = 1 WHERE S_id = ? AND Status = "Absent" AND action_taken IN ("Ask Reason", "Approved", "Reject", "Meet Me")', (session['user_id'],))
    # Also mark notifications in Notifications table as read
    conn.execute('UPDATE Notifications SET read_status = 1 WHERE S_id = ?', (session['user_id'],))
    conn.commit()
    conn.close()

    # Group by subject
    grouped_absences = {}
    for absence in absences:
        subj = absence['Subject']
        if subj not in grouped_absences:
            grouped_absences[subj] = []
        grouped_absences[subj].append({
            'Date': absence['Date'],
            'Subject': absence['Subject'],
            'action_taken': absence['action_taken'],
            'reason': absence['reason'],
            'proof': absence['proof']
        })

    return render_template('notifications.html', grouped_absences=grouped_absences)

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_type' not in session or session['user_type'] != 'student':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Fetch student details
    student = conn.execute('SELECT S_name, Depart_id, Sem FROM Student WHERE S_id = ?', (session['user_id'],)).fetchone()
    if not student:
        conn.close()
        return "Student not found", 404
    
    # Fetch department name
    depart_row = conn.execute('SELECT Depart_name FROM Department WHERE Depart_id = ? AND Sem = ? LIMIT 1', (student['Depart_id'], student['Sem'])).fetchone()
    depart_name = depart_row['Depart_name'] if depart_row else "Unknown"
    
    # Fetch subjects for this dept and sem
    subjects = conn.execute('SELECT DISTINCT Subject FROM Department WHERE Depart_id = ? AND Sem = ?', (student['Depart_id'], student['Sem'])).fetchall()
    
    # Fetch attendance grouped by subject
    attendance = conn.execute('SELECT Subject, Date, Status, action_taken FROM Attendance WHERE S_id = ? ORDER BY Date ASC', (session['user_id'],)).fetchall()
    grouped_attendance = {}
    for record in attendance:
        subj = record['Subject']
        if subj not in grouped_attendance:
            grouped_attendance[subj] = []
        grouped_attendance[subj].append({'date': record['Date'], 'status': record['Status'], 'action_taken': record['action_taken']})

    # Calculate eligibility: student is eligible only if all subjects have >=75% attendance
    is_eligible = True
    for subj in subjects:
        subj_name = subj['Subject']
        subj_attendance = grouped_attendance.get(subj_name, [])
        total_classes = len(subj_attendance)
        if total_classes == 0:
            is_eligible = False
            break
        present_count = sum(1 for rec in subj_attendance if rec['status'] == 'Present')
        approved_count = sum(1 for rec in subj_attendance if rec['status'] == 'Absent' and rec['action_taken'] == 'Approved')
        percentage = ((present_count + approved_count) / total_classes * 100)
        if percentage < 75:
            is_eligible = False
            break

    # Fetch notification count (unread notifications)
    notification_count = conn.execute('SELECT COUNT(*) FROM Notifications WHERE S_id = ? AND read_status = 0', (session['user_id'],)).fetchone()[0]

    # Fetch teacher notification count (number of distinct teachers who have sent notifications)
    teacher_notification_count = conn.execute('SELECT COUNT(DISTINCT T_id) FROM Attendance WHERE S_id = ? AND Status = "Absent" AND action_taken IN ("Ask Reason", "Approved", "Reject", "Meet Me") AND read_status = 0', (session['user_id'],)).fetchone()[0]
    
    # Generate full-year calendars for each subject
    current_year = datetime.datetime.now().year
    calendars = {}  # Initialize here to ensure it's always defined
    for subj in subjects:
        subj_name = subj['Subject']
        attendance_dict = {rec['date']: {'status': rec['status'], 'action_taken': rec['action_taken']} for rec in grouped_attendance.get(subj_name, [])}
        # Calculate percentages
        subj_attendance = grouped_attendance.get(subj_name, [])
        total_classes = len(subj_attendance)
        present_count = sum(1 for rec in subj_attendance if rec['status'] == 'Present')
        approved_count = sum(1 for rec in subj_attendance if rec['status'] == 'Absent' and rec['action_taken'] == 'Approved')
        percentage_with_approved = ((present_count + approved_count) / total_classes * 100) if total_classes > 0 else 0
        percentage_without = (present_count / total_classes * 100) if total_classes > 0 else 0
        # Build full-year calendar HTML (4x3 grid of months)
        cal_html = f'<div class="container"><h5 class="text-center mb-3">{current_year} Attendance Calendar</h5><p>Attendance: {percentage_with_approved:.2f}% (with approved), {percentage_without:.2f}% (without)</p><div class="row">'
        for month in range(1, 13):
            month_name = calendar.month_name[month]
            cal_html += f'<div class="col-md-4 mb-3"><table class="table table-bordered table-sm"><thead><tr><th colspan="7" class="text-center">{month_name} {current_year}</th></tr><tr><th>Su</th><th>Mo</th><th>Tu</th><th>We</th><th>Th</th><th>Fr</th><th>Sa</th></tr></thead><tbody>'
            try:
                month_cal = calendar.monthcalendar(current_year, month)
                for week in month_cal:
                    cal_html += '<tr>'
                    for day in week:
                        if day == 0:
                            cal_html += '<td></td>'  # Empty cell for days not in month
                        else:
                            date_str = f"{current_year}-{month:02d}-{day:02d}"
                            status_info = attendance_dict.get(date_str, {})
                            status = status_info.get('status')
                            action_taken = status_info.get('action_taken', '')
                            if status == 'Present':
                                cal_html += f'<td class="bg-success">{day}</td>'  # Green for present
                            elif status == 'Absent':
                                action_colors = {
                                    'Approved': 'bg-warning',  # Yellow for approved
                                    'Reject': 'bg-danger',     # Red for reject
                                    'Meet Me': 'bg-info'       # Light blue for meet me
                                }
                                color_class = action_colors.get(action_taken, 'bg-danger')  # Default to red for unknown
                                cal_html += f'<td class="{color_class}">{day}</td>'
                            else:
                                cal_html += f'<td>{day}</td>'  # Uncolored for no data
                    cal_html += '</tr>'
            except Exception as e:
                cal_html += f'<tr><td colspan="7">Error: {str(e)}</td></tr>'
            cal_html += '</tbody></table></div>'
            # Start new row every 3 months
            if month % 3 == 0:
                cal_html += '</div><div class="row">' if month < 12 else ''
        cal_html += '</div></div>'
        calendars[subj_name] = cal_html
    
    conn.close()
    return render_template('student_dashboard.html', student=student, depart_name=depart_name, subjects=subjects, grouped_attendance=grouped_attendance, calendars=calendars, notification_count=notification_count, teacher_notification_count=teacher_notification_count, is_eligible=is_eligible)


# Admin Dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    # Fetch Department records (unchanged)
    departments = conn.execute('SELECT * FROM Department ORDER BY Depart_id, Sem ASC').fetchall()
    # Build a simple list of unique department IDs to populate the dropdown in the template
    depart_ids = sorted({dept['Depart_id'] for dept in departments})
    grouped_departments = {}
    for dept in departments:
        key = (dept['Depart_id'], dept['Sem'])
        if key not in grouped_departments:
            grouped_departments[key] = {'Depart_name': dept['Depart_name'], 'subjects': []}
        grouped_departments[key]['subjects'].append(dept['Subject'])
    
    # Fetch Teacher records, group by Depart_id, sort by Sem
    teachers = conn.execute('SELECT * FROM Teacher ORDER BY Depart_id, Sem ASC').fetchall()
    grouped_teachers = {}
    for teacher in teachers:
        key = teacher['Depart_id']
        if key not in grouped_teachers:
            grouped_teachers[key] = {}
        sem_key = teacher['Sem']
        if sem_key not in grouped_teachers[key]:
            grouped_teachers[key][sem_key] = {'teachers': []}
        grouped_teachers[key][sem_key]['teachers'].append(teacher)
        
        # Fetch Student records, join with Department for Depart_name, group by Depart_id, sort by Sem
    students = conn.execute('''
    SELECT DISTINCT Student.S_id, Student.S_name, Student.Depart_id, Department.Depart_name, Student.Sem
    FROM Student
    JOIN Department ON Student.Depart_id = Department.Depart_id AND Student.Sem = Department.Sem
    ORDER BY Student.Depart_id, Student.Sem ASC
''').fetchall()
    grouped_students = {}
    for student in students:
        key = student['Depart_id']
        if key not in grouped_students:
            grouped_students[key] = {}
        sem_key = student['Sem']
        if sem_key not in grouped_students[key]:
            grouped_students[key][sem_key] = {'students': []}
        grouped_students[key][sem_key]['students'].append(student)
    
    conn.close()
    return render_template('admin_dashboard.html', grouped_departments=grouped_departments, grouped_teachers=grouped_teachers, grouped_students=grouped_students, departments=depart_ids)

# Add Department (unchanged)
@app.route('/admin/add_department', methods=['POST'])
def add_department():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    depart_id = request.form['depart_id']
    depart_name = request.form['depart_name']
    sem = request.form['sem']
    subjects = request.form.getlist('subjects[]')
    
    if not sem.isdigit():
        flash('Sem must be an integer!')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db_connection()
    for subject in subjects:
        try:
            conn.execute('INSERT INTO Department (Depart_id, Depart_name, Sem, Subject) VALUES (?, ?, ?, ?)',
                         (depart_id, depart_name, sem, subject))
        except sqlite3.IntegrityError:
            flash(f'Duplicate entry for Depart_id {depart_id}, Sem {sem}, Subject {subject}!')
            conn.close()
            return redirect(url_for('admin_dashboard'))
    conn.commit()
    conn.close()
    flash('Department(s) added successfully!')
    return redirect(url_for('admin_dashboard'))

# Edit Department (unchanged)
@app.route('/admin/edit_department/<depart_id>/<sem>/<subject>', methods=['GET', 'POST'])
def edit_department(depart_id, sem, subject):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        new_sem = request.form['sem']
        new_subject = request.form['subject']
        
        if not new_sem.isdigit():
            flash('Sem must be an integer!')
            return redirect(url_for('admin_dashboard'))
        
        conn.execute('UPDATE Department SET  Sem = ?, Subject = ? WHERE Depart_id = ? AND Sem = ? AND Subject = ?',
                     (new_sem, new_subject, depart_id, sem, subject))
        conn.commit()
        conn.close()
        flash('Department updated successfully!')
        return redirect(url_for('admin_dashboard'))
    
    dept = conn.execute('SELECT * FROM Department WHERE Depart_id = ? AND Sem = ? AND Subject = ?', (depart_id, sem, subject)).fetchone()
    conn.close()
    return render_template('edit_department.html', dept=dept)

# Delete Department (unchanged)
@app.route('/admin/delete_department/<depart_id>/<sem>/<subject>')
def delete_department(depart_id, sem, subject):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM Department WHERE Depart_id = ? AND Sem = ? AND Subject = ?', (depart_id, sem, subject))
    conn.commit()
    conn.close()
    flash('Department deleted successfully!')
    return redirect(url_for('admin_dashboard'))

# New route for autofill
@app.route('/admin/get_teacher/<t_id>')
def get_teacher(t_id):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    teacher = conn.execute('SELECT DISTINCT T_name, password FROM Teacher WHERE T_id = ? LIMIT 1', (t_id,)).fetchone()
    conn.close()
    if teacher:
        return jsonify({'t_name': teacher['T_name'], 'password': teacher['password']})
    return jsonify({})

# New route to fetch subjects for a given depart_id and sem
@app.route('/admin/get_subjects/<depart_id>/<int:sem>')
def get_subjects(depart_id, sem):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    conn = get_db_connection()
    subjects = conn.execute('SELECT DISTINCT Subject FROM Department WHERE Depart_id = ? AND Sem = ?', (depart_id, sem)).fetchall()
    conn.close()
    return jsonify([subj['Subject'] for subj in subjects])


@app.route('/admin/get_teacher_subjects/<t_id>/<depart_id>/<sem>')
def get_teacher_subjects(t_id, depart_id, sem):
    """Return list of subjects that teacher t_id already teaches for given depart_id and sem."""
    if 'user_type' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    subjects = conn.execute('SELECT DISTINCT Subject FROM Teacher WHERE T_id = ? AND Depart_id = ? AND Sem = ?', (t_id, depart_id, sem)).fetchall()
    conn.close()
    return jsonify([s['Subject'] for s in subjects])

# Add Teacher (updated for autofill)
@app.route('/admin/add_teacher', methods=['POST'])
def add_teacher():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    t_id = request.form['t_id']
    t_name = request.form['t_name']
    password = request.form['password']
    depart_id = request.form['depart_id']
    sem = request.form['sem']
    subjects = request.form.getlist('subjects[]')
    
    if not sem.isdigit():
        flash('Sem must be an integer!')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db_connection()
    # Validate Depart_id and Sem in Department table
    valid_dept = conn.execute('SELECT 1 FROM Department WHERE Depart_id = ? AND Sem = ? LIMIT 1', (depart_id, sem)).fetchone()
    if not valid_dept:
        flash(f'Invalid Depart_id {depart_id} or Sem {sem} - not found in Department table!')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    
    # If T_id exists, use existing T_name and password (autofill ensures this)
    existing = conn.execute('SELECT DISTINCT T_name, password FROM Teacher WHERE T_id = ? LIMIT 1', (t_id,)).fetchone()
    if existing:
        t_name = existing['T_name']
        password = existing['password']
        
    for subject in subjects:
        try:
            conn.execute('INSERT INTO Teacher (T_id, password, T_name, Depart_id, Sem, Subject) VALUES (?, ?, ?, ?, ?, ?)',
                         (t_id, password, t_name, depart_id, sem, subject))
        except sqlite3.IntegrityError:
            flash(f'Duplicate entry for T_id {t_id}, Depart_id{depart_id},Sem {sem}, Subject {subject}!')
            conn.close()
            return redirect(url_for('admin_dashboard'))
    conn.commit()
    conn.close()
    flash('Teacher(s) added successfully!')
    return redirect(url_for('admin_dashboard'))

# Edit Teacher (unchanged)
@app.route('/admin/edit_teacher/<t_id>/<sem>/<subject>', methods=['GET', 'POST'])
def edit_teacher(t_id, sem, subject):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        new_t_name = request.form['t_name']
        new_password = request.form['password']               
        conn.execute('UPDATE Teacher SET T_name = ?, password = ? WHERE T_id = ? AND Sem = ? AND Subject = ?',
                     (new_t_name, new_password, t_id, sem, subject))
        conn.commit()
        conn.close()
        flash('Teacher updated successfully!')
        return redirect(url_for('admin_dashboard'))
    
    teacher = conn.execute('SELECT * FROM Teacher WHERE T_id = ? AND Sem = ? AND Subject = ?', (t_id, sem, subject)).fetchone()
    conn.close()
    return render_template('edit_teacher.html', teacher=teacher)

# Delete Teacher (unchanged)
@app.route('/admin/delete_teacher/<t_id>/<sem>/<subject>')
def delete_teacher(t_id, sem, subject):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM Teacher WHERE T_id = ? AND Sem = ? AND Subject = ?', (t_id, sem, subject))
    conn.commit()
    conn.close()
    flash('Teacher deleted successfully!')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/get_department_details/<depart_id>')
def get_department_details(depart_id):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    dept = conn.execute(
        'SELECT DISTINCT Depart_name FROM Department WHERE Depart_id = ? LIMIT 1',
        (depart_id,)
    ).fetchone()
    semesters = conn.execute(
        'SELECT DISTINCT Sem FROM Department WHERE Depart_id = ? ORDER BY Sem ASC',
        (depart_id,)
    ).fetchall()
    conn.close()

    return jsonify({
        'name': dept['Depart_name'] if dept else '',
        'semesters': [s['Sem'] for s in semesters]
    })

# Add Student
@app.route('/admin/add_student', methods=['POST'])
def add_student():
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    s_id = request.form['s_id']
    s_name = request.form['s_name']
    password = request.form['password']
    depart_id = request.form['depart_id']
    sem = request.form['sem']
    
    if not sem.isdigit():
        flash('Sem must be an integer!')
        return redirect(url_for('admin_dashboard'))
    
    conn = get_db_connection()
    # Check if S_id is unique
    existing_student = conn.execute('SELECT 1 FROM Student WHERE S_id = ?', (s_id,)).fetchone()
    if existing_student:
        flash(f'S_id {s_id} already exists!')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    
    # Validate Depart_id and Sem in Department table
    valid_dept = conn.execute('SELECT 1 FROM Department WHERE Depart_id = ? AND Sem = ? LIMIT 1', (depart_id, sem)).fetchone()
    if not valid_dept:
        flash(f'Invalid Depart_id {depart_id} or Sem {sem} - not found in Department table!')
        conn.close()
        return redirect(url_for('admin_dashboard'))
    
    conn.execute('INSERT INTO Student (S_id, S_name, password, Depart_id, Sem) VALUES (?, ?, ?, ?, ?)',
                 (s_id, s_name, password, depart_id, sem))
    conn.commit()
    conn.close()
    flash('Student added successfully!')
    return redirect(url_for('admin_dashboard'))

# Edit Student (per S_id)
@app.route('/admin/edit_student/<s_id>', methods=['GET', 'POST'])
def edit_student(s_id):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        new_s_name = request.form['s_name']
        new_password = request.form['password']
        new_depart_id = request.form['depart_id']
        new_sem = request.form['sem']
        
        if not new_sem.isdigit():
            flash('Sem must be an integer!')
            return redirect(url_for('admin_dashboard'))
        
        # Validate new Depart_id and Sem
        valid_dept = conn.execute('SELECT 1 FROM Department WHERE Depart_id = ? AND Sem = ? LIMIT 1', (new_depart_id, new_sem)).fetchone()
        if not valid_dept:
            flash(f'Invalid Depart_id {new_depart_id} or Sem {new_sem} - not found in Department table!')
            return redirect(url_for('admin_dashboard'))
        
        conn.execute('UPDATE Student SET S_name = ?, password = ?, Depart_id = ?, Sem = ? WHERE S_id = ?',
                     (new_s_name, new_password, new_depart_id, new_sem, s_id))
        conn.commit()
        conn.close()
        flash('Student updated successfully!')
        return redirect(url_for('admin_dashboard'))
    
    student = conn.execute('SELECT * FROM Student WHERE S_id = ?', (s_id,)).fetchone()
    conn.close()
    return render_template('edit_student.html', student=student)

# Delete Student (per S_id)
@app.route('/admin/delete_student/<s_id>')
def delete_student(s_id):
    if 'user_type' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    conn.execute('DELETE FROM Student WHERE S_id = ?', (s_id,))
    conn.commit()
    conn.close()
    flash('Student deleted successfully!')
    return redirect(url_for('admin_dashboard'))


# Logout (unchanged)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
