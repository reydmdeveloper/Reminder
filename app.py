"""
REYDM – REY Datamind Multi-Tool Platform
Flask + MySQL + Email Notifications
Tools: Reminder, Night Shift Attendance
Admin assigns tools per user; users only see their assigned tools.
"""

import os
import json
import random
import string
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

# ─── App Configuration ───────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")
app.permanent_session_lifetime = timedelta(hours=2)

# ─── Database Configuration ──────────────────────────────────────────
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "mysql-21f1e29c-reydmdeveloper-2e13.i.aivencloud.com"),
    "port": int(os.environ.get("DB_PORT", 17090)),
    "user": os.environ.get("DB_USER", "avnadmin"),
    "password": os.environ.get("DB_PASSWORD", "AVNS_l-v67tdYKfQUCJZmrp9"),
    "database": os.environ.get("DB_NAME", "reydm_db"),
}

# ─── Email Configuration ─────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "reydmdeveloper@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "txebwrbrwtvuqttc")

# ─── Available Tools ─────────────────────────────────────────────────
AVAILABLE_TOOLS = {
    "reminder": {
        "name": "Reminder",
        "icon": "fa-solid fa-bell",
        "description": "Project reminder with countdown & email alerts",
    },
    "nightshift": {
        "name": "Night Shift",
        "icon": "fa-solid fa-moon",
        "description": "Night shift attendance tracker with dashboard",
    },
    "charpalette": {
        "name": "Char Palette",
        "icon": "fa-solid fa-font",
        "description": "Unicode character palette with search & copy",
    },
    "costconverter": {
        "name": "Cost Converter",
        "icon": "fa-solid fa-money-bill-transfer",
        "description": "Currency exchange rate converter",
    },
    "projectanalysis": {
        "name": "Project Analysis",
        "icon": "fa-solid fa-file-pdf",
        "description": "PDF project analyzer with export",
    },
    "pdfunlocker": {
        "name": "PDF Unlocker",
        "icon": "fa-solid fa-lock-open",
        "description": "Remove restrictions from PDF files",
    },
    "attendance": {
        "name": "Attendance",
        "icon": "fa-solid fa-clock",
        "description": "Login/Logout time tracker with reports",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════

def get_db():
    """Get a database connection."""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
        )
        return conn
    except mysql.connector.Error as e:
        print(f"Database connection error: {e}")
        return None


def init_db():
    """Create the database and tables if they don't exist."""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}`")
        cursor.execute(f"USE `{DB_CONFIG['database']}`")

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(100) NOT NULL,
                email VARCHAR(150) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role ENUM('admin', 'user') DEFAULT 'user',
                is_approved TINYINT(1) DEFAULT 0,
                is_active TINYINT(1) DEFAULT 1,
                mail_enabled TINYINT(1) DEFAULT 1,
                allowed_tools JSON DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # OTP table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS otp_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(150) NOT NULL,
                otp_code VARCHAR(6) NOT NULL,
                purpose ENUM('register', 'reset_password') DEFAULT 'register',
                is_used TINYINT(1) DEFAULT 0,
                expires_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Reminders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                project_name VARCHAR(255) NOT NULL,
                reminder_datetime DATETIME NOT NULL,
                created_by INT NOT NULL,
                is_sent TINYINT(1) DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_project_time (project_name, reminder_datetime)
            )
        """)

        # Reminder email log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminder_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                reminder_id INT NOT NULL,
                sent_to VARCHAR(150) NOT NULL,
                status ENUM('sent', 'failed') DEFAULT 'sent',
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
            )
        """)

        # Night shift employees table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ns_employees (
                id INT AUTO_INCREMENT PRIMARY KEY,
                emp_id VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                dept VARCHAR(60) DEFAULT '',
                status ENUM('active', 'resigned') DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Night shift attendance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ns_attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                emp_id VARCHAR(20) NOT NULL,
                att_date DATE NOT NULL,
                present TINYINT(1) DEFAULT 1,
                UNIQUE KEY unique_emp_date (emp_id, att_date)
            )
        """)

        # User attendance logs (login/logout tracker)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                login_date DATE NOT NULL,
                login_time DATETIME NOT NULL,
                logout_time DATETIME DEFAULT NULL,
                hours_spent DECIMAL(5,2) DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Attendance change requests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                request_date DATE NOT NULL,
                requested_login DATETIME NOT NULL,
                requested_logout DATETIME NOT NULL,
                reason VARCHAR(500) DEFAULT '',
                status ENUM('pending', 'approved', 'declined') DEFAULT 'pending',
                admin_note VARCHAR(255) DEFAULT '',
                reviewed_by INT DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Insert default admin if not exists
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if not cursor.fetchone():
            admin_hash = generate_password_hash("admin123")
            all_tools = json.dumps(list(AVAILABLE_TOOLS.keys()))
            cursor.execute(
                """INSERT INTO users (full_name, email, password_hash, role, is_approved, allowed_tools)
                   VALUES (%s, %s, %s, 'admin', 1, %s)""",
                ("Administrator", "admin@system.local", admin_hash, all_tools),
            )

        # Insert default night shift employees if none exist
        cursor.execute("SELECT COUNT(*) FROM ns_employees")
        if cursor.fetchone()[0] == 0:
            defaults = [
                ('E001', 'Ashwath', '', 'active'),
                ('E002', 'Bharathi', '', 'active'),
                ('E003', 'Dharani', '', 'active'),
                ('E004', 'Kanchana', '', 'active'),
                ('E005', 'Karthikeyan', '', 'active'),
                ('E006', 'Nethra', '', 'active'),
                ('E007', 'Sanjay', '', 'active'),
                ('E008', 'SRK', '', 'active'),
            ]
            cursor.executemany(
                "INSERT INTO ns_employees (emp_id, name, dept, status) VALUES (%s, %s, %s, %s)",
                defaults,
            )

        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database initialized successfully.")
    except mysql.connector.Error as e:
        print(f"❌ Database initialization error: {e}")


# ═══════════════════════════════════════════════════════════════════════
# EMAIL HELPERS
# ═══════════════════════════════════════════════════════════════════════

def send_email(to_email, subject, body_html):
    """Send an email using Gmail SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("⚠️  Gmail credentials not configured.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = GMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())

        print(f"📧 Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Email send failed: {e}")
        return False


def send_otp_email(to_email, otp_code):
    subject = "REYDM – Your Verification Code"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#1a1a2e;text-align:center;">Verification Code</h2>
        <p style="color:#555;text-align:center;">Use this code to complete your registration:</p>
        <div style="text-align:center;margin:24px 0;">
            <span style="font-size:32px;font-weight:700;letter-spacing:8px;
                         color:#e94560;background:#fef2f2;padding:12px 24px;
                         border-radius:8px;">{otp_code}</span>
        </div>
        <p style="color:#888;text-align:center;font-size:13px;">
            This code expires in <strong>10 minutes</strong>.
        </p>
    </div>
    """
    return send_email(to_email, subject, body)


def send_approval_notification(to_email, full_name):
    subject = "REYDM – New User Awaiting Approval"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#1a1a2e;">New Registration Request</h2>
        <p>A new user has registered and is waiting for admin approval:</p>
        <table style="width:100%;margin:16px 0;">
            <tr><td style="color:#888;">Name:</td><td><strong>{full_name}</strong></td></tr>
            <tr><td style="color:#888;">Email:</td><td><strong>{to_email}</strong></td></tr>
        </table>
    </div>
    """
    conn = get_db()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email FROM users WHERE role='admin' AND is_approved=1")
        admins = cursor.fetchall()
        cursor.close()
        conn.close()
        for admin in admins:
            send_email(admin["email"], subject, body)


def send_user_approved_email(to_email, full_name):
    subject = "REYDM – Account Approved!"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#16a34a;text-align:center;">Welcome, {full_name}!</h2>
        <p style="text-align:center;color:#555;">
            Your account has been approved. You can now log in to REYDM.
        </p>
    </div>
    """
    return send_email(to_email, subject, body)


def send_reminder_email(to_email, project_name, reminder_time):
    subject = f"⏰ Reminder: {project_name}"
    formatted_time = reminder_time.strftime("%B %d, %Y at %I:%M %p")
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#e94560;text-align:center;">Project Reminder</h2>
        <div style="background:#fef2f2;padding:20px;border-radius:8px;margin:16px 0;">
            <h3 style="margin:0 0 8px;color:#1a1a2e;">{project_name}</h3>
            <p style="margin:0;color:#666;">Scheduled: {formatted_time}</p>
        </div>
    </div>
    """
    return send_email(to_email, subject, body)


# ═══════════════════════════════════════════════════════════════════════
# AUTH DECORATORS & HELPERS
# ═══════════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


def tool_required(tool_key):
    """Decorator: ensures the user has access to the given tool via allowed_tools."""
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))
            allowed = session.get("allowed_tools", [])
            if tool_key not in allowed:
                flash("You don't have access to this tool.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return wrapper


def get_user_tools():
    """Return list of tool keys the current user can access (from allowed_tools)."""
    return session.get("allowed_tools", [])


@app.context_processor
def inject_tools():
    """Make tools info available in all templates."""
    user_tools = []
    if "user_id" in session:
        for key in get_user_tools():
            if key in AVAILABLE_TOOLS:
                user_tools.append({"key": key, **AVAILABLE_TOOLS[key]})
    return dict(
        user_tools=user_tools,
        all_tools=AVAILABLE_TOOLS,
        get_user_tools=get_user_tools,
    )


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – AUTH
# ═══════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        if not conn:
            flash("Database connection error.", "danger")
            return render_template("login.html")

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if not user["is_approved"]:
            flash("Your account is awaiting admin approval.", "warning")
            return render_template("login.html")

        if not user["is_active"]:
            flash("Your account has been deactivated.", "danger")
            return render_template("login.html")

        session.permanent = True
        session["user_id"] = user["id"]
        session["full_name"] = user["full_name"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        # Parse allowed_tools from JSON
        tools = user.get("allowed_tools")
        if tools:
            if isinstance(tools, str):
                try:
                    tools = json.loads(tools)
                except Exception:
                    tools = []
            session["allowed_tools"] = tools if isinstance(tools, list) else []
        else:
            session["allowed_tools"] = []

        flash(f"Welcome back, {user['full_name']}!", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        errors = []
        if not full_name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html")

        conn = get_db()
        if not conn:
            flash("Database connection error.", "danger")
            return render_template("register.html")

        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("Email is already registered.", "danger")
            cursor.close()
            conn.close()
            return render_template("register.html")

        otp_code = "".join(random.choices(string.digits, k=6))
        expires_at = datetime.now() + timedelta(minutes=10)

        cursor.execute(
            """INSERT INTO otp_tokens (email, otp_code, purpose, expires_at)
               VALUES (%s, %s, 'register', %s)""",
            (email, otp_code, expires_at),
        )
        conn.commit()
        cursor.close()
        conn.close()

        threading.Thread(target=send_otp_email, args=(email, otp_code)).start()

        session["reg_data"] = {
            "full_name": full_name,
            "email": email,
            "password": password,
        }

        flash("A verification code has been sent to your email.", "info")
        return redirect(url_for("verify_otp"))

    return render_template("register.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    reg_data = session.get("reg_data")
    if not reg_data:
        flash("Please register first.", "warning")
        return redirect(url_for("register"))

    if request.method == "POST":
        otp_input = request.form.get("otp", "").strip()
        email = reg_data["email"]

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """SELECT * FROM otp_tokens
               WHERE email = %s AND otp_code = %s AND purpose = 'register'
                     AND is_used = 0 AND expires_at > NOW()
               ORDER BY id DESC LIMIT 1""",
            (email, otp_input),
        )
        token = cursor.fetchone()

        if not token:
            flash("Invalid or expired OTP.", "danger")
            cursor.close()
            conn.close()
            return render_template("verify_otp.html", email=email)

        cursor.execute("UPDATE otp_tokens SET is_used = 1 WHERE id = %s", (token["id"],))

        pw_hash = generate_password_hash(reg_data["password"])
        try:
            cursor.execute(
                """INSERT INTO users (full_name, email, password_hash, role, is_approved, allowed_tools)
                   VALUES (%s, %s, %s, 'user', 0, '[]')""",
                (reg_data["full_name"], email, pw_hash),
            )
            conn.commit()
        except mysql.connector.IntegrityError:
            flash("Email already registered.", "danger")
            cursor.close()
            conn.close()
            return redirect(url_for("register"))

        cursor.close()
        conn.close()

        threading.Thread(
            target=send_approval_notification,
            args=(email, reg_data["full_name"]),
        ).start()

        session.pop("reg_data", None)
        flash("Registration successful! Pending admin approval.", "success")
        return redirect(url_for("login"))

    return render_template("verify_otp.html", email=reg_data["email"])


@app.route("/resend-otp", methods=["POST"])
def resend_otp():
    reg_data = session.get("reg_data")
    if not reg_data:
        return jsonify({"success": False, "message": "Session expired."}), 400

    email = reg_data["email"]
    otp_code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=10)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO otp_tokens (email, otp_code, purpose, expires_at)
           VALUES (%s, %s, 'register', %s)""",
        (email, otp_code, expires_at),
    )
    conn.commit()
    cursor.close()
    conn.close()

    threading.Thread(target=send_otp_email, args=(email, otp_code)).start()
    return jsonify({"success": True, "message": "A new OTP has been sent."})


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    tools = get_user_tools()

    pending_count = 0
    total_users = 0
    upcoming_count = 0
    reminders = []

    if session["role"] == "admin":
        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_approved = 0")
        pending_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM users")
        total_users = cursor.fetchone()["cnt"]

    if "reminder" in tools:
        if session["role"] == "admin":
            cursor.execute("""
                SELECT r.*, u.full_name AS creator_name
                FROM reminders r JOIN users u ON r.created_by = u.id
                ORDER BY r.reminder_datetime DESC
            """)
        else:
            cursor.execute("""
                SELECT r.*, u.full_name AS creator_name
                FROM reminders r JOIN users u ON r.created_by = u.id
                ORDER BY r.reminder_datetime DESC
            """)
        reminders = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS cnt FROM reminders WHERE is_sent = 0 AND reminder_datetime > NOW()")
        upcoming_count = cursor.fetchone()["cnt"]

    cursor.close()
    conn.close()
    return render_template(
        "dashboard.html",
        reminders=reminders,
        pending_count=pending_count,
        total_users=total_users,
        upcoming_count=upcoming_count,
    )


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – REMINDERS
# ═══════════════════════════════════════════════════════════════════════

@app.route("/reminders/add", methods=["GET", "POST"])
@login_required
@tool_required("reminder")
def add_reminder():
    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        reminder_date = request.form.get("reminder_date", "")
        reminder_time = request.form.get("reminder_time", "")

        if not project_name or not reminder_date or not reminder_time:
            flash("All fields are required.", "danger")
            return render_template("add_reminder.html")

        reminder_datetime_str = f"{reminder_date} {reminder_time}"
        try:
            reminder_dt = datetime.strptime(reminder_datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            flash("Invalid date/time format.", "danger")
            return render_template("add_reminder.html")

        if reminder_dt <= datetime.now():
            flash("Reminder must be in the future.", "danger")
            return render_template("add_reminder.html")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id FROM reminders WHERE project_name = %s AND reminder_datetime = %s",
            (project_name, reminder_dt),
        )
        if cursor.fetchone():
            flash("Duplicate reminder exists.", "warning")
            cursor.close()
            conn.close()
            return render_template("add_reminder.html")

        cursor.execute(
            """INSERT INTO reminders (project_name, reminder_datetime, created_by)
               VALUES (%s, %s, %s)""",
            (project_name, reminder_dt, session["user_id"]),
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash("Reminder created successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_reminder.html")


@app.route("/reminders/delete/<int:reminder_id>", methods=["POST"])
@login_required
@tool_required("reminder")
def delete_reminder(reminder_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
    reminder = cursor.fetchone()

    if not reminder:
        flash("Reminder not found.", "danger")
    elif session["role"] != "admin" and reminder["created_by"] != session["user_id"]:
        flash("You can only delete your own reminders.", "danger")
    else:
        cursor.execute("DELETE FROM reminders WHERE id = %s", (reminder_id,))
        conn.commit()
        flash("Reminder deleted.", "success")

    cursor.close()
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/reminders/edit/<int:reminder_id>", methods=["GET", "POST"])
@login_required
@tool_required("reminder")
def edit_reminder(reminder_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
    reminder = cursor.fetchone()

    if not reminder:
        flash("Reminder not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for("dashboard"))

    if session["role"] != "admin" and reminder["created_by"] != session["user_id"]:
        flash("You can only edit your own reminders.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        reminder_date = request.form.get("reminder_date", "")
        reminder_time = request.form.get("reminder_time", "")

        reminder_datetime_str = f"{reminder_date} {reminder_time}"
        try:
            reminder_dt = datetime.strptime(reminder_datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            flash("Invalid date/time format.", "danger")
            return render_template("edit_reminder.html", reminder=reminder)

        cursor.execute(
            "SELECT id FROM reminders WHERE project_name = %s AND reminder_datetime = %s AND id != %s",
            (project_name, reminder_dt, reminder_id),
        )
        if cursor.fetchone():
            flash("Duplicate reminder exists.", "warning")
            return render_template("edit_reminder.html", reminder=reminder)

        cursor.execute(
            "UPDATE reminders SET project_name = %s, reminder_datetime = %s WHERE id = %s",
            (project_name, reminder_dt, reminder_id),
        )
        conn.commit()
        flash("Reminder updated.", "success")
        cursor.close()
        conn.close()
        return redirect(url_for("dashboard"))

    cursor.close()
    conn.close()
    return render_template("edit_reminder.html", reminder=reminder)


@app.route("/reminders/trigger/<int:reminder_id>", methods=["POST"])
@login_required
def trigger_reminder(reminder_id):
    conn = get_db()
    if not conn:
        return jsonify({"success": False, "message": "Database error."}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
    reminder = cursor.fetchone()

    if not reminder:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Not found."}), 404

    if reminder["is_sent"]:
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Already sent."})

    cursor.execute(
        "SELECT email FROM users WHERE is_approved = 1 AND is_active = 1 AND mail_enabled = 1"
    )
    users = cursor.fetchall()
    sent_count = 0

    for user in users:
        success = send_reminder_email(
            user["email"], reminder["project_name"], reminder["reminder_datetime"],
        )
        cursor.execute(
            "INSERT INTO reminder_logs (reminder_id, sent_to, status) VALUES (%s, %s, %s)",
            (reminder["id"], user["email"], "sent" if success else "failed"),
        )
        if success:
            sent_count += 1

    cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = %s", (reminder_id,))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"Sent to {sent_count} user(s).",
        "sent_count": sent_count,
        "total_users": len(users),
    })


@app.route("/api/reminders")
@login_required
def api_reminders():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.*, u.full_name AS creator_name
        FROM reminders r JOIN users u ON r.created_by = u.id
        ORDER BY r.reminder_datetime ASC
    """)
    reminders = cursor.fetchall()
    cursor.close()
    conn.close()

    result = []
    for r in reminders:
        result.append({
            "id": r["id"],
            "project_name": r["project_name"],
            "reminder_datetime": r["reminder_datetime"].strftime("%Y-%m-%d %H:%M"),
            "creator_name": r["creator_name"],
            "is_sent": r["is_sent"],
            "created_by": r["created_by"],
        })
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – NIGHT SHIFT ATTENDANCE
# ═══════════════════════════════════════════════════════════════════════

@app.route("/nightshift")
@login_required
@tool_required("nightshift")
def nightshift():
    return render_template("nightshift.html")


@app.route("/api/ns/employees")
@login_required
@tool_required("nightshift")
def api_ns_employees():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ns_employees ORDER BY emp_id ASC")
    emps = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(emps)


@app.route("/api/ns/employees", methods=["POST"])
@login_required
@tool_required("nightshift")
def api_ns_add_employee():
    data = request.get_json()
    emp_id = data.get("emp_id", "").strip()
    name = data.get("name", "").strip()
    dept = data.get("dept", "").strip()
    status = data.get("status", "active")

    if not emp_id or not name:
        return jsonify({"success": False, "message": "ID and Name required."}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ns_employees (emp_id, name, dept, status) VALUES (%s, %s, %s, %s)",
            (emp_id, name, dept, status),
        )
        conn.commit()
    except mysql.connector.IntegrityError:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Employee ID already exists."}), 400

    cursor.close()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/ns/employees/<emp_id>", methods=["PUT"])
@login_required
@tool_required("nightshift")
def api_ns_update_employee(emp_id):
    data = request.get_json()
    new_id = data.get("emp_id", "").strip()
    name = data.get("name", "").strip()
    dept = data.get("dept", "").strip()
    status = data.get("status", "active")

    conn = get_db()
    cursor = conn.cursor()

    if new_id != emp_id:
        # Update attendance records with new ID
        cursor.execute("UPDATE ns_attendance SET emp_id = %s WHERE emp_id = %s", (new_id, emp_id))

    cursor.execute(
        "UPDATE ns_employees SET emp_id = %s, name = %s, dept = %s, status = %s WHERE emp_id = %s",
        (new_id, name, dept, status, emp_id),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/ns/employees/<emp_id>", methods=["DELETE"])
@login_required
@tool_required("nightshift")
def api_ns_delete_employee(emp_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ns_attendance WHERE emp_id = %s", (emp_id,))
    cursor.execute("DELETE FROM ns_employees WHERE emp_id = %s", (emp_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/ns/employees/bulk", methods=["POST"])
@login_required
@tool_required("nightshift")
def api_ns_bulk_add():
    data = request.get_json()
    employees = data.get("employees", [])
    added = 0
    skipped = 0
    conn = get_db()
    cursor = conn.cursor()
    for emp in employees:
        try:
            cursor.execute(
                "INSERT INTO ns_employees (emp_id, name, dept, status) VALUES (%s, %s, %s, %s)",
                (emp["emp_id"], emp["name"], emp.get("dept", ""), emp.get("status", "active")),
            )
            added += 1
        except mysql.connector.IntegrityError:
            skipped += 1
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "added": added, "skipped": skipped})


@app.route("/api/ns/attendance/<int:year>/<int:month>")
@login_required
@tool_required("nightshift")
def api_ns_attendance(year, month):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT emp_id, DAY(att_date) AS day_num
           FROM ns_attendance
           WHERE YEAR(att_date) = %s AND MONTH(att_date) = %s AND present = 1""",
        (year, month),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Return as dict: { "E001": [1, 5, 7, ...], ... }
    result = {}
    for r in rows:
        eid = r["emp_id"]
        if eid not in result:
            result[eid] = []
        result[eid].append(r["day_num"])
    return jsonify(result)


@app.route("/api/ns/attendance/toggle", methods=["POST"])
@login_required
@tool_required("nightshift")
def api_ns_toggle_attendance():
    data = request.get_json()
    emp_id = data["emp_id"]
    year = data["year"]
    month = data["month"]
    day = data["day"]
    att_date = f"{year}-{month:02d}-{day:02d}"

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id FROM ns_attendance WHERE emp_id = %s AND att_date = %s",
        (emp_id, att_date),
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute("DELETE FROM ns_attendance WHERE id = %s", (existing["id"],))
        present = False
    else:
        cursor.execute(
            "INSERT INTO ns_attendance (emp_id, att_date) VALUES (%s, %s)",
            (emp_id, att_date),
        )
        present = True

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "present": present})


@app.route("/api/ns/attendance/year/<int:year>")
@login_required
@tool_required("nightshift")
def api_ns_year_attendance(year):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT emp_id, MONTH(att_date) AS month_num, COUNT(*) AS total
           FROM ns_attendance
           WHERE YEAR(att_date) = %s AND present = 1
           GROUP BY emp_id, MONTH(att_date)""",
        (year,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    result = {}
    for r in rows:
        eid = r["emp_id"]
        if eid not in result:
            result[eid] = {}
        result[eid][r["month_num"]] = r["total"]
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – CHARACTER PALETTE
# ═══════════════════════════════════════════════════════════════════════

@app.route("/charpalette")
@login_required
@tool_required("charpalette")
def charpalette():
    return render_template("charpalette.html")


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – COST CONVERTER
# ═══════════════════════════════════════════════════════════════════════

@app.route("/costconverter")
@login_required
@tool_required("costconverter")
def costconverter():
    return render_template("costconverter.html")


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – PROJECT ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

@app.route("/projectanalysis")
@login_required
@tool_required("projectanalysis")
def projectanalysis():
    return render_template("projectanalysis.html")


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – PDF UNLOCKER
# ═══════════════════════════════════════════════════════════════════════

@app.route("/pdfunlocker")
@login_required
@tool_required("pdfunlocker")
def pdfunlocker():
    return render_template("pdfunlocker.html")


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – ATTENDANCE (Login/Logout Tracker)
# ═══════════════════════════════════════════════════════════════════════

@app.route("/attendance")
@login_required
@tool_required("attendance")
def attendance():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Get today's active session for this user
    today = datetime.now().date()
    cursor.execute(
        """SELECT * FROM attendance_logs
           WHERE user_id = %s AND logout_time IS NULL
           ORDER BY login_time DESC LIMIT 1""",
        (session["user_id"],),
    )
    active_session = cursor.fetchone()

    # Get recent logs (last 30 days)
    cursor.execute(
        """SELECT * FROM attendance_logs
           WHERE user_id = %s AND login_time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
           ORDER BY login_time DESC""",
        (session["user_id"],),
    )
    recent_logs = cursor.fetchall()

    # Get pending requests count
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM attendance_requests WHERE user_id = %s AND status = 'pending'",
        (session["user_id"],),
    )
    pending_requests = cursor.fetchone()["cnt"]

    # Get user's requests
    cursor.execute(
        """SELECT * FROM attendance_requests
           WHERE user_id = %s ORDER BY created_at DESC LIMIT 20""",
        (session["user_id"],),
    )
    my_requests = cursor.fetchall()

    # Chart data: last 7 days hours
    cursor.execute(
        """SELECT login_date, SUM(hours_spent) AS total_hours
           FROM attendance_logs
           WHERE user_id = %s AND login_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
             AND hours_spent IS NOT NULL
           GROUP BY login_date ORDER BY login_date ASC""",
        (session["user_id"],),
    )
    chart_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "attendance.html",
        active_session=active_session,
        recent_logs=recent_logs,
        pending_requests=pending_requests,
        my_requests=my_requests,
        chart_data=chart_data,
    )


@app.route("/attendance/login", methods=["POST"])
@login_required
@tool_required("attendance")
def attendance_login():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # Check if already logged in (no logout yet)
    cursor.execute(
        "SELECT id FROM attendance_logs WHERE user_id = %s AND logout_time IS NULL",
        (session["user_id"],),
    )
    if cursor.fetchone():
        flash("You are already logged in. Please logout first.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for("attendance"))

    now = datetime.now()
    cursor.execute(
        """INSERT INTO attendance_logs (user_id, login_date, login_time)
           VALUES (%s, %s, %s)""",
        (session["user_id"], now.date(), now),
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash(f"Logged in at {now.strftime('%I:%M %p')}", "success")
    return redirect(url_for("attendance"))


@app.route("/attendance/logout", methods=["POST"])
@login_required
@tool_required("attendance")
def attendance_logout():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        """SELECT * FROM attendance_logs
           WHERE user_id = %s AND logout_time IS NULL
           ORDER BY login_time DESC LIMIT 1""",
        (session["user_id"],),
    )
    active = cursor.fetchone()

    if not active:
        flash("No active login session found.", "warning")
        cursor.close()
        conn.close()
        return redirect(url_for("attendance"))

    now = datetime.now()
    login_time = active["login_time"]
    # Use the login_date (not today) so cross-midnight works
    login_date = active["login_date"]

    diff = (now - login_time).total_seconds() / 3600.0
    hours_spent = round(diff, 2)

    cursor.execute(
        """UPDATE attendance_logs SET logout_time = %s, hours_spent = %s
           WHERE id = %s""",
        (now, hours_spent, active["id"]),
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash(f"Logged out. Hours spent: {hours_spent} hrs", "success")
    return redirect(url_for("attendance"))


@app.route("/attendance/request", methods=["POST"])
@login_required
@tool_required("attendance")
def attendance_request():
    """User submits a request to manually add/change attendance."""
    req_date = request.form.get("request_date", "")
    req_login = request.form.get("request_login", "")
    req_logout = request.form.get("request_logout", "")
    reason = request.form.get("reason", "").strip()

    if not req_date or not req_login or not req_logout:
        flash("All fields are required.", "danger")
        return redirect(url_for("attendance"))

    try:
        login_dt = datetime.strptime(f"{req_date} {req_login}", "%Y-%m-%d %H:%M")
        logout_dt = datetime.strptime(f"{req_date} {req_logout}", "%Y-%m-%d %H:%M")
        # Handle cross-midnight: if logout is before login, add a day
        if logout_dt <= login_dt:
            logout_dt += timedelta(days=1)
    except ValueError:
        flash("Invalid date/time format.", "danger")
        return redirect(url_for("attendance"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO attendance_requests
           (user_id, request_date, requested_login, requested_logout, reason)
           VALUES (%s, %s, %s, %s, %s)""",
        (session["user_id"], req_date, login_dt, logout_dt, reason),
    )
    conn.commit()
    cursor.close()
    conn.close()

    flash("Attendance request submitted for admin approval.", "success")
    return redirect(url_for("attendance"))


@app.route("/admin/attendance-requests")
@admin_required
def admin_attendance_requests():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT ar.*, u.full_name, u.email
           FROM attendance_requests ar
           JOIN users u ON ar.user_id = u.id
           ORDER BY
             CASE ar.status WHEN 'pending' THEN 0 ELSE 1 END,
             ar.created_at DESC
           LIMIT 50"""
    )
    requests_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_attendance_requests.html", requests=requests_list)


@app.route("/admin/attendance-requests/<int:req_id>/<action>", methods=["POST"])
@admin_required
def handle_attendance_request(req_id, action):
    if action not in ("approve", "decline"):
        flash("Invalid action.", "danger")
        return redirect(url_for("admin_attendance_requests"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM attendance_requests WHERE id = %s", (req_id,))
    req = cursor.fetchone()

    if not req:
        flash("Request not found.", "danger")
        cursor.close()
        conn.close()
        return redirect(url_for("admin_attendance_requests"))

    if action == "approve":
        # Create the attendance log entry
        login_dt = req["requested_login"]
        logout_dt = req["requested_logout"]
        diff = (logout_dt - login_dt).total_seconds() / 3600.0
        hours_spent = round(diff, 2)

        cursor.execute(
            """INSERT INTO attendance_logs (user_id, login_date, login_time, logout_time, hours_spent)
               VALUES (%s, %s, %s, %s, %s)""",
            (req["user_id"], req["request_date"], login_dt, logout_dt, hours_spent),
        )
        cursor.execute(
            "UPDATE attendance_requests SET status = 'approved', reviewed_by = %s WHERE id = %s",
            (session["user_id"], req_id),
        )
        flash("Request approved and attendance logged.", "success")
    else:
        cursor.execute(
            "UPDATE attendance_requests SET status = 'declined', reviewed_by = %s WHERE id = %s",
            (session["user_id"], req_id),
        )
        flash("Request declined.", "info")

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("admin_attendance_requests"))


@app.route("/api/attendance/chart")
@login_required
def api_attendance_chart():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT login_date, SUM(hours_spent) AS total_hours
           FROM attendance_logs
           WHERE user_id = %s AND login_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
             AND hours_spent IS NOT NULL
           GROUP BY login_date ORDER BY login_date ASC""",
        (session["user_id"],),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    result = [{"date": r["login_date"].strftime("%Y-%m-%d"), "hours": float(r["total_hours"])} for r in rows]
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – ADMIN: USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════

@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    # Parse allowed_tools for each user
    for u in users:
        tools = u.get("allowed_tools")
        if tools:
            if isinstance(tools, str):
                try:
                    u["allowed_tools"] = json.loads(tools)
                except Exception:
                    u["allowed_tools"] = []
        else:
            u["allowed_tools"] = []

    return render_template("admin_users.html", users=users)


@app.route("/admin/users/approve/<int:user_id>", methods=["POST"])
@admin_required
def approve_user(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user:
        cursor.execute("UPDATE users SET is_approved = 1 WHERE id = %s", (user_id,))
        conn.commit()
        threading.Thread(
            target=send_user_approved_email,
            args=(user["email"], user["full_name"]),
        ).start()
        flash(f"User {user['full_name']} approved.", "success")
    cursor.close()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/reject/<int:user_id>", methods=["POST"])
@admin_required
def reject_user(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user and user["role"] != "admin":
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        flash(f"User {user['full_name']} rejected.", "info")
    cursor.close()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/toggle-active/<int:user_id>", methods=["POST"])
@admin_required
def toggle_user_active(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user and user["id"] != session["user_id"]:
        new_status = 0 if user["is_active"] else 1
        cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        status_text = "activated" if new_status else "deactivated"
        flash(f"User {user['full_name']} {status_text}.", "success")
    cursor.close()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/toggle-mail/<int:user_id>", methods=["POST"])
@admin_required
def toggle_mail(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user:
        new_status = 0 if user["mail_enabled"] else 1
        cursor.execute("UPDATE users SET mail_enabled = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        status_text = "enabled" if new_status else "disabled"
        flash(f"Email {status_text} for {user['full_name']}.", "success")
    cursor.close()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/change-role/<int:user_id>", methods=["POST"])
@admin_required
def change_role(user_id):
    new_role = request.form.get("role", "user")
    if new_role not in ("admin", "user"):
        flash("Invalid role.", "danger")
        return redirect(url_for("admin_users"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    if user and user["id"] != session["user_id"]:
        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
        conn.commit()
        flash(f"Role for {user['full_name']} changed to {new_role}.", "success")
    cursor.close()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/reset-password/<int:user_id>", methods=["POST"])
@admin_required
def reset_password(user_id):
    new_password = request.form.get("new_password", "")
    if len(new_password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("admin_users"))

    conn = get_db()
    cursor = conn.cursor()
    pw_hash = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (pw_hash, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Password reset successfully.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/update-tools/<int:user_id>", methods=["POST"])
@admin_required
def update_user_tools(user_id):
    """Admin assigns tools to a user."""
    selected_tools = request.form.getlist("tools")
    # Filter to valid tools only
    valid_tools = [t for t in selected_tools if t in AVAILABLE_TOOLS]
    tools_json = json.dumps(valid_tools)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET allowed_tools = %s WHERE id = %s", (tools_json, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash(f"Tools updated for user.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/toggle-tool/<int:user_id>/<tool_key>", methods=["POST"])
@admin_required
def toggle_tool(user_id, tool_key):
    """Toggle a single tool on/off for a user."""
    if tool_key not in AVAILABLE_TOOLS:
        flash("Invalid tool.", "danger")
        return redirect(url_for("admin_users"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT allowed_tools FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        flash("User not found.", "danger")
        return redirect(url_for("admin_users"))

    tools = row.get("allowed_tools")
    if tools:
        if isinstance(tools, str):
            try:
                tools = json.loads(tools)
            except Exception:
                tools = []
    else:
        tools = []

    if not isinstance(tools, list):
        tools = []

    # Toggle: add if missing, remove if present
    if tool_key in tools:
        tools.remove(tool_key)
        action = "disabled"
    else:
        tools.append(tool_key)
        action = "enabled"

    tools_json = json.dumps(tools)
    cursor.execute("UPDATE users SET allowed_tools = %s WHERE id = %s", (tools_json, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    tool_name = AVAILABLE_TOOLS[tool_key]["name"]
    flash(f"{tool_name} {action} for user.", "success")
    return redirect(url_for("admin_users"))


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – USER PROFILE
# ═══════════════════════════════════════════════════════════════════════

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()

        if not check_password_hash(user["password_hash"], current_password):
            flash("Current password is incorrect.", "danger")
        elif len(new_password) < 6:
            flash("New password must be at least 6 characters.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            pw_hash = generate_password_hash(new_password)
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s",
                (pw_hash, session["user_id"]),
            )
            conn.commit()
            flash("Password updated successfully.", "success")

        cursor.close()
        conn.close()

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("profile.html", user=user)


# ═══════════════════════════════════════════════════════════════════════
# REMINDER SCHEDULER (Background Thread)
# ═══════════════════════════════════════════════════════════════════════

def reminder_scheduler():
    while True:
        try:
            conn = get_db()
            if conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT * FROM reminders
                    WHERE is_sent = 0
                      AND reminder_datetime <= DATE_ADD(NOW(), INTERVAL 60 SECOND)
                      AND reminder_datetime >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                """)
                due_reminders = cursor.fetchall()

                for reminder in due_reminders:
                    cursor.execute(
                        "SELECT email FROM users WHERE is_approved = 1 AND is_active = 1 AND mail_enabled = 1"
                    )
                    users = cursor.fetchall()

                    for user in users:
                        success = send_reminder_email(
                            user["email"], reminder["project_name"], reminder["reminder_datetime"],
                        )
                        cursor.execute(
                            "INSERT INTO reminder_logs (reminder_id, sent_to, status) VALUES (%s, %s, %s)",
                            (reminder["id"], user["email"], "sent" if success else "failed"),
                        )

                    cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = %s", (reminder["id"],))
                    conn.commit()

                cursor.close()
                conn.close()
        except Exception as e:
            print(f"Scheduler error: {e}")

        time.sleep(30)


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()

    scheduler_thread = threading.Thread(target=reminder_scheduler, daemon=True)
    scheduler_thread.start()

    run_host = os.environ.get("APP_HOST", "0.0.0.0")
    run_port = int(os.environ.get("APP_PORT", 5000))
    run_debug = os.environ.get("APP_DEBUG", "true").lower() in ("true", "1", "yes")

    print(f"")
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║           🚀 REYDM Server                       ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║  Local:   http://127.0.0.1:{run_port}               ║")
    print(f"║  Network: http://<YOUR_IP>:{run_port}              ║")
    print(f"║  Debug:   {run_debug}                                ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print(f"")

    app.run(debug=run_debug, host=run_host, port=run_port)