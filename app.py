"""
Project Reminder Application
Flask + MySQL + Email Notifications
"""

import os
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
from mysql.connector import pooling

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
    "database": os.environ.get("DB_NAME", "project_reminder_db"),
    "pool_name": "reminder_pool",
    "pool_size": 5,
}

# ─── Email Configuration ─────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "reydmdeveloper@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "txebwrbrwtvuqttc")


# ═══════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════

def get_db():
    """Get a database connection from the pool."""
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # OTP table for registration verification
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

        # Insert default admin if not exists
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        if not cursor.fetchone():
            admin_hash = generate_password_hash("admin123")
            cursor.execute(
                """INSERT INTO users (full_name, email, password_hash, role, is_approved)
                   VALUES (%s, %s, %s, 'admin', 1)""",
                ("Administrator", "admin@system.local", admin_hash),
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
    """Send an email using Gmail SMTP with App Password."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("⚠️  Gmail credentials not configured. Email not sent.")
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
    """Send OTP verification email."""
    subject = "Project Reminder – Your Verification Code"
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
            This code expires in <strong>10 minutes</strong>. Do not share it with anyone.
        </p>
    </div>
    """
    return send_email(to_email, subject, body)


def send_approval_notification(to_email, full_name):
    """Notify admin about new registration request."""
    subject = "Project Reminder – New User Awaiting Approval"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#1a1a2e;">New Registration Request</h2>
        <p>A new user has registered and is waiting for admin approval:</p>
        <table style="width:100%;margin:16px 0;">
            <tr><td style="color:#888;">Name:</td><td><strong>{full_name}</strong></td></tr>
            <tr><td style="color:#888;">Email:</td><td><strong>{to_email}</strong></td></tr>
        </table>
        <p style="color:#888;font-size:13px;">
            Log in to the admin panel to approve or reject this request.
        </p>
    </div>
    """
    # Send to all admins
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
    """Notify user that their account has been approved."""
    subject = "Project Reminder – Account Approved!"
    body = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;
                border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#16a34a;text-align:center;">Welcome, {full_name}!</h2>
        <p style="text-align:center;color:#555;">
            Your account has been approved by an administrator.
            You can now log in and start using Project Reminder.
        </p>
    </div>
    """
    return send_email(to_email, subject, body)


def send_reminder_email(to_email, project_name, reminder_time):
    """Send project reminder email."""
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
        <p style="color:#888;text-align:center;font-size:13px;">
            This is an automated reminder from Project Reminder App.
        </p>
    </div>
    """
    return send_email(to_email, subject, body)


# ═══════════════════════════════════════════════════════════════════════
# AUTH DECORATORS
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

        # Generate OTP
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

        # Send OTP email in background
        threading.Thread(target=send_otp_email, args=(email, otp_code)).start()

        # Store registration data in session temporarily
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
            flash("Invalid or expired OTP. Please try again.", "danger")
            cursor.close()
            conn.close()
            return render_template("verify_otp.html", email=email)

        # Mark OTP as used
        cursor.execute("UPDATE otp_tokens SET is_used = 1 WHERE id = %s", (token["id"],))

        # Create the user account
        pw_hash = generate_password_hash(reg_data["password"])
        try:
            cursor.execute(
                """INSERT INTO users (full_name, email, password_hash, role, is_approved)
                   VALUES (%s, %s, %s, 'user', 0)""",
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

        # Notify admin
        threading.Thread(
            target=send_approval_notification,
            args=(email, reg_data["full_name"]),
        ).start()

        session.pop("reg_data", None)
        flash(
            "Registration successful! Your account is pending admin approval.",
            "success",
        )
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

    if session["role"] == "admin":
        cursor.execute("""
            SELECT r.*, u.full_name AS creator_name
            FROM reminders r JOIN users u ON r.created_by = u.id
            ORDER BY r.reminder_datetime DESC
        """)
        reminders = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_approved = 0")
        pending_count = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM users")
        total_users = cursor.fetchone()["cnt"]

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
    else:
        cursor.execute("""
            SELECT r.*, u.full_name AS creator_name
            FROM reminders r JOIN users u ON r.created_by = u.id
            ORDER BY r.reminder_datetime DESC
        """)
        reminders = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template("dashboard.html", reminders=reminders)


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – REMINDERS
# ═══════════════════════════════════════════════════════════════════════

@app.route("/reminders/add", methods=["GET", "POST"])
@login_required
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
            flash("Reminder date/time must be in the future.", "danger")
            return render_template("add_reminder.html")

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        # Check for duplicate
        cursor.execute(
            """SELECT id FROM reminders
               WHERE project_name = %s AND reminder_datetime = %s""",
            (project_name, reminder_dt),
        )
        if cursor.fetchone():
            flash("A reminder with this project name and time already exists.", "warning")
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

        # Check duplicate (excluding current)
        cursor.execute(
            """SELECT id FROM reminders
               WHERE project_name = %s AND reminder_datetime = %s AND id != %s""",
            (project_name, reminder_dt, reminder_id),
        )
        if cursor.fetchone():
            flash("A duplicate reminder already exists.", "warning")
            return render_template("edit_reminder.html", reminder=reminder)

        cursor.execute(
            """UPDATE reminders SET project_name = %s, reminder_datetime = %s
               WHERE id = %s""",
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
        # Notify user
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
        flash(f"User {user['full_name']} rejected and removed.", "info")
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
        flash(f"Email notifications {status_text} for {user['full_name']}.", "success")
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
    """Background thread that checks for due reminders every 30 seconds."""
    while True:
        try:
            conn = get_db()
            if conn:
                cursor = conn.cursor(dictionary=True)
                # Find reminders due within the next 60 seconds that haven't been sent
                cursor.execute("""
                    SELECT * FROM reminders
                    WHERE is_sent = 0
                      AND reminder_datetime <= DATE_ADD(NOW(), INTERVAL 60 SECOND)
                      AND reminder_datetime >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                """)
                due_reminders = cursor.fetchall()

                for reminder in due_reminders:
                    # Get all approved active users with mail enabled
                    cursor.execute(
                        "SELECT email FROM users WHERE is_approved = 1 AND is_active = 1 AND mail_enabled = 1"
                    )
                    users = cursor.fetchall()

                    for user in users:
                        success = send_reminder_email(
                            user["email"],
                            reminder["project_name"],
                            reminder["reminder_datetime"],
                        )
                        cursor.execute(
                            """INSERT INTO reminder_logs (reminder_id, sent_to, status)
                               VALUES (%s, %s, %s)""",
                            (reminder["id"], user["email"], "sent" if success else "failed"),
                        )

                    cursor.execute(
                        "UPDATE reminders SET is_sent = 1 WHERE id = %s",
                        (reminder["id"],),
                    )
                    conn.commit()
                    print(f"✅ Reminder sent: {reminder['project_name']}")

                cursor.close()
                conn.close()
        except Exception as e:
            print(f"Scheduler error: {e}")

        time.sleep(30)


# ═══════════════════════════════════════════════════════════════════════
# API ENDPOINTS (for AJAX)
# ═══════════════════════════════════════════════════════════════════════

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


@app.route("/reminders/trigger/<int:reminder_id>", methods=["POST"])
@login_required
def trigger_reminder(reminder_id):
    """Triggered by frontend when countdown reaches zero – sends email to all users."""
    conn = get_db()
    if not conn:
        return jsonify({"success": False, "message": "Database error."}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM reminders WHERE id = %s", (reminder_id,))
    reminder = cursor.fetchone()

    if not reminder:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "Reminder not found."}), 404

    if reminder["is_sent"]:
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Already sent."})

    # Get all approved active users with mail enabled
    cursor.execute(
        "SELECT email FROM users WHERE is_approved = 1 AND is_active = 1 AND mail_enabled = 1"
    )
    users = cursor.fetchall()
    sent_count = 0

    for user in users:
        success = send_reminder_email(
            user["email"],
            reminder["project_name"],
            reminder["reminder_datetime"],
        )
        cursor.execute(
            """INSERT INTO reminder_logs (reminder_id, sent_to, status)
               VALUES (%s, %s, %s)""",
            (reminder["id"], user["email"], "sent" if success else "failed"),
        )
        if success:
            sent_count += 1

    # Mark as sent
    cursor.execute("UPDATE reminders SET is_sent = 1 WHERE id = %s", (reminder_id,))
    conn.commit()
    cursor.close()
    conn.close()

    print(f"⚡ Live trigger: '{reminder['project_name']}' → {sent_count}/{len(users)} emails sent")
    return jsonify({
        "success": True,
        "message": f"Reminder sent to {sent_count} user(s).",
        "sent_count": sent_count,
        "total_users": len(users),
    })


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()

    # Start background scheduler
    scheduler_thread = threading.Thread(target=reminder_scheduler, daemon=True)
    scheduler_thread.start()

    # ─── Server Configuration ─────────────────────────────────────
    # host="0.0.0.0" makes the server accessible via:
    #   - http://localhost:5000
    #   - http://127.0.0.1:5000
    #   - http://<YOUR_IP>:5000  (e.g. http://192.168.1.100:5000)
    #
    # Set via environment variables:
    #   export APP_HOST=0.0.0.0
    #   export APP_PORT=5000
    #   export APP_DEBUG=true
    # ──────────────────────────────────────────────────────────────

    run_host = os.environ.get("APP_HOST", "0.0.0.0")
    run_port = int(os.environ.get("APP_PORT", 5000))
    run_debug = os.environ.get("APP_DEBUG", "true").lower() in ("true", "1", "yes")

    print(f"")
    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║         🔔 Project Reminder Server              ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║  Local:   http://127.0.0.1:{run_port}               ║")
    print(f"║  Network: http://<YOUR_IP>:{run_port}              ║")
    print(f"║  Debug:   {run_debug}                                ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print(f"")

    app.run(debug=run_debug, host=run_host, port=run_port)