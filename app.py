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
import uuid
import re as re_module
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import mysql.connector

# ─── App Configuration ───────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-random-secret-key")
app.permanent_session_lifetime = timedelta(hours=2)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 50MB max upload

# ─── Upload Configuration ────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'chat_files')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    "chat": {
        "name": "Chat",
        "icon": "fa-solid fa-comments",
        "description": "Team chat with file sharing via OneDrive",
    },
    "pettycash_cbe": {
        "name": "Petty Cash (CBE)",
        "icon": "fa-solid fa-money-bill-wave",
        "description": "Coimbatore office petty cash tracker",
    },
    "pettycash_dgl": {
        "name": "Petty Cash (DGL)",
        "icon": "fa-solid fa-money-bills",
        "description": "Dindigul office petty cash tracker",
    },
    "leavemanager": {
        "name": "Leave Manager",
        "icon": "fa-solid fa-calendar-check",
        "description": "Employee leave tracker with monthly dashboard",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════

def get_db():
    """Get a database connection with IST timezone."""
    try:
        conn = mysql.connector.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
        )
        # Set session timezone to IST so NOW() and CURRENT_TIMESTAMP return local time
        cursor = conn.cursor()
        cursor.execute("SET time_zone = '+05:30'")
        cursor.close()
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
        cursor.execute("SET time_zone = '+05:30'")

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
                last_active DATETIME DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Add columns for existing databases that were created before this update
        for alter_sql in [
            "ALTER TABLE users ADD COLUMN last_active DATETIME DEFAULT NULL",
            "ALTER TABLE chat_messages ADD COLUMN reply_to_id INT DEFAULT NULL",
        ]:
            try:
                cursor.execute(alter_sql)
            except mysql.connector.Error:
                pass  # Column already exists

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


        # ─── CHAT TABLES ─────────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                conv_type ENUM('private', 'group') DEFAULT 'private',
                group_name VARCHAR(150) DEFAULT NULL,
                group_description VARCHAR(500) DEFAULT NULL,
                created_by INT DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Chat message reactions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_reactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message_id INT NOT NULL,
                user_id INT NOT NULL,
                emoji VARCHAR(10) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_msg_user_emoji (message_id, user_id, emoji)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_participants (
                id INT AUTO_INCREMENT PRIMARY KEY,
                conversation_id INT NOT NULL,
                user_id INT NOT NULL,
                joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_conv_user (conversation_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                conversation_id INT NOT NULL,
                sender_id INT NOT NULL,
                message_text TEXT DEFAULT NULL,
                message_type ENUM('text', 'file', 'image', 'system') DEFAULT 'text',
                file_name VARCHAR(500) DEFAULT NULL,
                file_url VARCHAR(2000) DEFAULT NULL,
                file_size VARCHAR(50) DEFAULT NULL,
                reply_to_id INT DEFAULT NULL,
                is_deleted TINYINT(1) DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_read_receipts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                conversation_id INT NOT NULL,
                user_id INT NOT NULL,
                last_read_message_id INT DEFAULT 0,
                read_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_conv_user_read (conversation_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_pinned_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                conversation_id INT NOT NULL,
                message_id INT NOT NULL,
                pinned_by INT NOT NULL,
                pin_duration ENUM('1h', '24h', '7d', '30d', 'forever') DEFAULT 'forever',
                expires_at DATETIME DEFAULT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                FOREIGN KEY (pinned_by) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_conv_msg_pin (conversation_id, message_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_deleted_for_me (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message_id INT NOT NULL,
                user_id INT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE KEY unique_msg_user_del (message_id, user_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                setting_key VARCHAR(100) UNIQUE NOT NULL,
                setting_value TEXT DEFAULT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
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

        # Insert default OneDrive folder link setting
        cursor.execute("SELECT id FROM admin_settings WHERE setting_key = 'onedrive_folder_link' LIMIT 1")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO admin_settings (setting_key, setting_value) VALUES (%s, %s)", ("onedrive_folder_link", ""))

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




def send_chat_notification_email(to_email, sender_name, message_preview):
    subject = f"REYDM Chat: New message from {sender_name}"
    body = f"""<div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#1f6feb;text-align:center;">New Chat Message</h2>
        <div style="background:#f0f6ff;padding:20px;border-radius:8px;margin:16px 0;">
        <p style="margin:0 0 8px;color:#888;font-size:13px;">From: <strong>{sender_name}</strong></p>
        <p style="margin:0;color:#333;">{message_preview[:200]}</p></div></div>"""
    return send_email(to_email, subject, body)

def send_mention_email(to_email, sender_name, conv_name, message_preview):
    subject = f"REYDM: {sender_name} mentioned you"
    body = f"""<div style="font-family:sans-serif;max-width:480px;margin:auto;padding:30px;border:1px solid #e0e0e0;border-radius:12px;">
        <h2 style="color:#d29922;text-align:center;">You were mentioned!</h2>
        <div style="background:#fef9ee;padding:20px;border-radius:8px;margin:16px 0;">
        <p style="margin:0 0 8px;color:#888;font-size:13px;"><strong>{sender_name}</strong> mentioned you in <strong>{conv_name}</strong></p>
        <p style="margin:0;color:#333;">{message_preview[:200]}</p></div></div>"""
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



def get_admin_setting(key, default=""):
    conn = get_db()
    if not conn: return default
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT setting_value FROM admin_settings WHERE setting_key = %s", (key,))
    row = cursor.fetchone()
    cursor.close(); conn.close()
    return row["setting_value"] if row and row["setting_value"] else default

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

        # Set online status
        conn2 = get_db()
        if conn2:
            c2 = conn2.cursor()
            c2.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (user["id"],))
            conn2.commit(); c2.close(); conn2.close()
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
# ROUTES – CHAT
# ═══════════════════════════════════════════════════════════════════════

@app.route("/chat")
@login_required
@tool_required("chat")
def chat():
    onedrive_link = get_admin_setting("onedrive_folder_link", "")
    return render_template("chat.html", onedrive_link=onedrive_link)

@app.route("/uploads/chat_files/<filename>")
@login_required
def serve_chat_file(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return render_template_string('<div style="font-family:sans-serif;text-align:center;padding:80px 20px;background:#0d1117;color:#e6edf3;min-height:100vh;"><div style="max-width:400px;margin:auto;"><div style="font-size:72px;opacity:0.3;margin-bottom:20px;">📁</div><h1 style="font-size:28px;color:#f85149;margin-bottom:10px;">File Not Found</h1><p style="color:#8b949e;font-size:14px;margin-bottom:24px;">This file may have been moved to OneDrive.</p><a href="{{ onedrive }}" target="_blank" style="display:inline-block;padding:10px 24px;background:#0078d4;color:white;border-radius:8px;text-decoration:none;font-weight:600;">Open OneDrive Folder</a><br><a href="/chat" style="display:inline-block;margin-top:16px;color:#388bfd;font-size:13px;">← Back to Chat</a></div></div>', onedrive=get_admin_setting('onedrive_folder_link', '#')), 404
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/api/chat/contacts")
@login_required
@tool_required("chat")
def api_chat_contacts():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, full_name, email FROM users WHERE is_approved = 1 AND is_active = 1 AND id != %s ORDER BY full_name ASC", (session["user_id"],))
    contacts = cursor.fetchall(); cursor.close(); conn.close()
    return jsonify(contacts)

@app.route("/api/chat/conversations")
@login_required
@tool_required("chat")
def api_chat_conversations():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT cc.id AS conversation_id, cc.conv_type, cc.group_name, cc.updated_at,
            (SELECT cm.message_text FROM chat_messages cm WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1) AS last_message,
            (SELECT cm.message_type FROM chat_messages cm WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1) AS last_message_type,
            (SELECT cm.file_name FROM chat_messages cm WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1) AS last_file_name,
            (SELECT cm.created_at FROM chat_messages cm WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1) AS last_message_time,
            (SELECT u2.full_name FROM chat_messages cm JOIN users u2 ON cm.sender_id = u2.id WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1) AS last_sender_name,
            COALESCE((SELECT COUNT(*) FROM chat_messages cm2 WHERE cm2.conversation_id = cc.id AND cm2.is_deleted = 0 AND cm2.id > COALESCE((SELECT crr.last_read_message_id FROM chat_read_receipts crr WHERE crr.conversation_id = cc.id AND crr.user_id = %s), 0) AND cm2.sender_id != %s), 0) AS unread_count
        FROM chat_conversations cc JOIN chat_participants cp ON cc.id = cp.conversation_id WHERE cp.user_id = %s
        ORDER BY COALESCE((SELECT cm.created_at FROM chat_messages cm WHERE cm.conversation_id = cc.id AND cm.is_deleted = 0 ORDER BY cm.created_at DESC LIMIT 1), cc.created_at) DESC
    """, (session["user_id"], session["user_id"], session["user_id"]))
    conversations = cursor.fetchall()
    result = []
    for conv in conversations:
        c = dict(conv)
        if c["conv_type"] == "private":
            cursor.execute("SELECT u.id, u.full_name, u.email FROM chat_participants cp JOIN users u ON cp.user_id = u.id WHERE cp.conversation_id = %s AND cp.user_id != %s LIMIT 1", (c["conversation_id"], session["user_id"]))
            ou = cursor.fetchone()
            c["other_user_id"] = ou["id"] if ou else None
            c["other_user_name"] = ou["full_name"] if ou else "Unknown"
            c["other_user_email"] = ou["email"] if ou else ""
        else:
            cursor.execute("SELECT u.id, u.full_name FROM chat_participants cp JOIN users u ON cp.user_id = u.id WHERE cp.conversation_id = %s", (c["conversation_id"],))
            c["participants"] = cursor.fetchall()
        if c.get("last_message_time"): c["last_message_time"] = c["last_message_time"].strftime("%Y-%m-%d %H:%M:%S")
        if c.get("updated_at"): c["updated_at"] = c["updated_at"].strftime("%Y-%m-%d %H:%M:%S")
        result.append(c)
    cursor.close(); conn.close()
    return jsonify(result)

@app.route("/api/chat/conversations", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_create_conversation():
    data = request.get_json(); conv_type = data.get("conv_type", "private"); participants = data.get("participants", []); group_name = data.get("group_name", "")
    if not participants: return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    if conv_type == "private" and len(participants) == 1:
        cursor.execute("SELECT cc.id FROM chat_conversations cc JOIN chat_participants cp1 ON cc.id = cp1.conversation_id AND cp1.user_id = %s JOIN chat_participants cp2 ON cc.id = cp2.conversation_id AND cp2.user_id = %s WHERE cc.conv_type = 'private' LIMIT 1", (session["user_id"], participants[0]))
        existing = cursor.fetchone()
        if existing: cursor.close(); conn.close(); return jsonify({"success": True, "conversation_id": existing["id"], "existing": True})
    cursor.execute("INSERT INTO chat_conversations (conv_type, group_name, created_by) VALUES (%s, %s, %s)", (conv_type, group_name if conv_type == "group" else None, session["user_id"]))
    conv_id = cursor.lastrowid
    cursor.execute("INSERT INTO chat_participants (conversation_id, user_id) VALUES (%s, %s)", (conv_id, session["user_id"]))
    for uid in participants:
        try: cursor.execute("INSERT INTO chat_participants (conversation_id, user_id) VALUES (%s, %s)", (conv_id, uid))
        except mysql.connector.IntegrityError: pass
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True, "conversation_id": conv_id, "existing": False})

def _serialize_msg(m, uid):
    return {"id": m["id"], "sender_id": m["sender_id"], "sender_name": m["sender_name"], "sender_email": m["sender_email"], "message_text": m["message_text"], "message_type": m["message_type"], "file_name": m["file_name"], "file_url": m["file_url"], "file_size": m["file_size"], "created_at": m["created_at"].strftime("%Y-%m-%d %H:%M:%S"), "is_mine": m["sender_id"] == uid, "is_pinned": bool(m.get("pin_id")), "pin_id": m.get("pin_id"), "reactions": {}, "reply_to_id": m.get("reply_to_id"), "reply_sender": m.get("reply_sender"), "reply_text": m.get("reply_text")}

@app.route("/api/chat/messages/<int:cid>")
@login_required
@tool_required("chat")
def api_chat_messages(cid):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify([])
    limit = min(int(request.args.get("limit", 50)), 100); before_id = request.args.get("before_id")
    q = "SELECT cm.*, u.full_name AS sender_name, u.email AS sender_email, cpm.id AS pin_id, ru.full_name AS reply_sender, rm.message_text AS reply_text FROM chat_messages cm JOIN users u ON cm.sender_id = u.id LEFT JOIN chat_pinned_messages cpm ON cpm.message_id = cm.id AND cpm.conversation_id = cm.conversation_id AND (cpm.expires_at IS NULL OR cpm.expires_at > NOW()) LEFT JOIN chat_deleted_for_me cdfm ON cdfm.message_id = cm.id AND cdfm.user_id = %s LEFT JOIN chat_messages rm ON cm.reply_to_id = rm.id LEFT JOIN users ru ON rm.sender_id = ru.id WHERE cm.conversation_id = %s AND cm.is_deleted = 0 AND cdfm.id IS NULL"
    params = [session["user_id"], cid]
    if before_id: q += " AND cm.id < %s"; params.append(int(before_id))
    q += " ORDER BY cm.created_at DESC LIMIT %s"; params.append(limit)
    cursor.execute(q, tuple(params)); messages = cursor.fetchall()
    if messages:
        lid = max(m["id"] for m in messages)
        cursor.execute("INSERT INTO chat_read_receipts (conversation_id, user_id, last_read_message_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE last_read_message_id = GREATEST(last_read_message_id, %s)", (cid, session["user_id"], lid, lid))
        conn.commit()
    result = [_serialize_msg(m, session["user_id"]) for m in reversed(messages)]
    # Batch load reactions
    if result:
        msg_ids = [r["id"] for r in result]
        fmt = ','.join(['%s'] * len(msg_ids))
        cursor.execute(f"SELECT cr.message_id, cr.emoji, cr.user_id, u.full_name FROM chat_reactions cr JOIN users u ON cr.user_id = u.id WHERE cr.message_id IN ({fmt})", tuple(msg_ids))
        for rx in cursor.fetchall():
            for r in result:
                if r["id"] == rx["message_id"]:
                    r["reactions"].setdefault(rx["emoji"], []).append({"user_id": rx["user_id"], "name": rx["full_name"]})
    cursor.close(); conn.close()
    return jsonify(result)

@app.route("/api/chat/messages/<int:cid>", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_send_message(cid):
    data = request.get_json(); msg_text = data.get("message_text", "").strip(); msg_type = data.get("message_type", "text")
    file_name = data.get("file_name"); file_url = data.get("file_url"); file_size = data.get("file_size")
    reply_to_id = data.get("reply_to_id")
    if not msg_text and msg_type == "text": return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify({"success": False}), 403
    cursor.execute("INSERT INTO chat_messages (conversation_id, sender_id, message_text, message_type, file_name, file_url, file_size, reply_to_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (cid, session["user_id"], msg_text, msg_type, file_name, file_url, file_size, reply_to_id))
    mid = cursor.lastrowid
    cursor.execute("UPDATE chat_conversations SET updated_at = NOW() WHERE id = %s", (cid,))
    cursor.execute("INSERT INTO chat_read_receipts (conversation_id, user_id, last_read_message_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE last_read_message_id = GREATEST(last_read_message_id, %s)", (cid, session["user_id"], mid, mid))
    conn.commit()
    cursor.execute("SELECT u.email, u.full_name, u.mail_enabled, u.id FROM chat_participants cp JOIN users u ON cp.user_id = u.id WHERE cp.conversation_id = %s AND cp.user_id != %s AND u.mail_enabled = 1", (cid, session["user_id"]))
    recipients = cursor.fetchall(); sender_name = session.get("full_name", "Someone")
    preview = msg_text if msg_type == "text" else f"Shared a file: {file_name}"
    mentioned_names = re_module.findall(r'@([\w][\w ]*?)(?:\s|$|,|\.)', msg_text or '')
    cursor.execute("SELECT conv_type, group_name FROM chat_conversations WHERE id = %s", (cid,))
    ci = cursor.fetchone(); conv_name = ci["group_name"] if ci and ci["conv_type"] == "group" else "Private Chat"
    for r in recipients:
        is_mentioned = any(r["full_name"].lower().startswith(mn.lower().strip()) for mn in mentioned_names)
        if is_mentioned:
            threading.Thread(target=send_mention_email, args=(r["email"], sender_name, conv_name, preview)).start()
        else:
            threading.Thread(target=send_chat_notification_email, args=(r["email"], sender_name, preview)).start()
    cursor.execute("SELECT cm.*, u.full_name AS sender_name, u.email AS sender_email, NULL AS pin_id FROM chat_messages cm JOIN users u ON cm.sender_id = u.id WHERE cm.id = %s", (mid,))
    new_msg = cursor.fetchone(); cursor.close(); conn.close()
    return jsonify({"success": True, "message": _serialize_msg(new_msg, session["user_id"])})

@app.route("/api/chat/messages/<int:cid>/delete/<int:mid>", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_delete_message(cid, mid):
    data = request.get_json() or {}; delete_for = data.get("delete_for", "me")
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM chat_messages WHERE id = %s AND conversation_id = %s", (mid, cid))
    msg = cursor.fetchone()
    if not msg: cursor.close(); conn.close(); return jsonify({"success": False}), 404
    if delete_for == "everyone":
        if msg["sender_id"] != session["user_id"] and session.get("role") != "admin":
            cursor.close(); conn.close(); return jsonify({"success": False, "message": "Only sender/admin can delete for everyone."}), 403
        cursor.execute("UPDATE chat_messages SET is_deleted = 1, message_text = %s, message_type = 'system', file_name = NULL, file_url = NULL WHERE id = %s", ("🚫 This message was deleted", mid))
        cursor.execute("DELETE FROM chat_pinned_messages WHERE message_id = %s", (mid,))
    else:
        try: cursor.execute("INSERT INTO chat_deleted_for_me (message_id, user_id) VALUES (%s, %s)", (mid, session["user_id"]))
        except mysql.connector.IntegrityError: pass
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/messages/<int:cid>/new")
@login_required
@tool_required("chat")
def api_chat_new_messages(cid):
    after_id = int(request.args.get("after_id", 0))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify([])
    cursor.execute("SELECT cm.*, u.full_name AS sender_name, u.email AS sender_email, cpm.id AS pin_id, ru.full_name AS reply_sender, rm.message_text AS reply_text FROM chat_messages cm JOIN users u ON cm.sender_id = u.id LEFT JOIN chat_pinned_messages cpm ON cpm.message_id = cm.id AND cpm.conversation_id = cm.conversation_id AND (cpm.expires_at IS NULL OR cpm.expires_at > NOW()) LEFT JOIN chat_deleted_for_me cdfm ON cdfm.message_id = cm.id AND cdfm.user_id = %s LEFT JOIN chat_messages rm ON cm.reply_to_id = rm.id LEFT JOIN users ru ON rm.sender_id = ru.id WHERE cm.conversation_id = %s AND cm.is_deleted = 0 AND cdfm.id IS NULL AND cm.id > %s ORDER BY cm.created_at ASC", (session["user_id"], cid, after_id))
    messages = cursor.fetchall()
    if messages:
        lid = max(m["id"] for m in messages)
        cursor.execute("INSERT INTO chat_read_receipts (conversation_id, user_id, last_read_message_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE last_read_message_id = GREATEST(last_read_message_id, %s)", (cid, session["user_id"], lid, lid))
        conn.commit()
    result = [_serialize_msg(m, session["user_id"]) for m in messages]
    cursor.close(); conn.close()
    return jsonify(result)

@app.route("/api/chat/unread-total")
@login_required
def api_chat_unread_total():
    conn = get_db()
    if not conn: return jsonify({"unread": 0})
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COALESCE(SUM(unread), 0) AS total_unread FROM (SELECT (SELECT COUNT(*) FROM chat_messages cm2 WHERE cm2.conversation_id = cc.id AND cm2.is_deleted = 0 AND cm2.id > COALESCE((SELECT crr.last_read_message_id FROM chat_read_receipts crr WHERE crr.conversation_id = cc.id AND crr.user_id = %s), 0) AND cm2.sender_id != %s) AS unread FROM chat_conversations cc JOIN chat_participants cp ON cc.id = cp.conversation_id WHERE cp.user_id = %s) sub", (session["user_id"], session["user_id"], session["user_id"]))
    row = cursor.fetchone(); cursor.close(); conn.close()
    return jsonify({"unread": row["total_unread"] if row else 0})

@app.route("/api/chat/group/create", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_create_group():
    data = request.get_json(); group_name = data.get("group_name", "").strip(); participants = data.get("participants", [])
    if not group_name: return jsonify({"success": False, "message": "Group name required."}), 400
    if len(participants) < 1: return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("INSERT INTO chat_conversations (conv_type, group_name, created_by) VALUES ('group', %s, %s)", (group_name, session["user_id"]))
    conv_id = cursor.lastrowid
    cursor.execute("INSERT INTO chat_participants (conversation_id, user_id) VALUES (%s, %s)", (conv_id, session["user_id"]))
    for uid in participants:
        try: cursor.execute("INSERT INTO chat_participants (conversation_id, user_id) VALUES (%s, %s)", (conv_id, uid))
        except mysql.connector.IntegrityError: pass
    cursor.execute("INSERT INTO chat_messages (conversation_id, sender_id, message_text, message_type) VALUES (%s, %s, %s, 'system')", (conv_id, session["user_id"], f"{session['full_name']} created the group '{group_name}'"))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True, "conversation_id": conv_id})

@app.route("/api/chat/upload", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_upload_file():
    if 'file' not in request.files: return jsonify({"success": False, "message": "No file."}), 400
    f = request.files['file']
    if not f.filename: return jsonify({"success": False}), 400
    original_name = secure_filename(f.filename)
    unique_name = f"{uuid.uuid4().hex[:12]}_{original_name}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_name)
    chunk_size = 8 * 1024 * 1024
    total = 0
    with open(filepath, 'wb') as out:
        while True:
            chunk = f.stream.read(chunk_size)
            if not chunk: break
            out.write(chunk)
            total += len(chunk)
    if total < 1024: size_str = f"{total} B"
    elif total < 1024*1024: size_str = f"{total/1024:.1f} KB"
    elif total < 1024*1024*1024: size_str = f"{total/(1024*1024):.1f} MB"
    else: size_str = f"{total/(1024*1024*1024):.2f} GB"
    # Extract page count for supported file types
    page_count = 0
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else ''
    try:
        if ext == 'pdf':
            import subprocess
            result = subprocess.run(['python3', '-c', f"import fitz; doc=fitz.open('{filepath}'); print(len(doc))"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0: page_count = int(result.stdout.strip())
            else:
                # Fallback: count PDF pages by reading file
                with open(filepath, 'rb') as pf:
                    content = pf.read()
                    page_count = content.count(b'/Type /Page') - content.count(b'/Type /Pages')
                    if page_count <= 0: page_count = content.count(b'/Type/Page') - content.count(b'/Type/Pages')
                    if page_count <= 0: page_count = 0
    except Exception: pass
    local_url = url_for('serve_chat_file', filename=unique_name, _external=False)
    onedrive_link = get_admin_setting("onedrive_folder_link", "")
    return jsonify({"success": True, "file_name": original_name, "file_url": local_url,
                    "local_url": local_url, "file_size": size_str,
                    "page_count": page_count, "file_ext": ext})

@app.route("/api/chat/messages/<int:cid>/pin/<int:mid>", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_pin_message(cid, mid):
    data = request.get_json() or {}; duration = data.get("duration", "forever")
    expires_at = None
    if duration == "1h": expires_at = datetime.now() + timedelta(hours=1)
    elif duration == "24h": expires_at = datetime.now() + timedelta(hours=24)
    elif duration == "7d": expires_at = datetime.now() + timedelta(days=7)
    elif duration == "30d": expires_at = datetime.now() + timedelta(days=30)
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify({"success": False}), 403
    try:
        cursor.execute("INSERT INTO chat_pinned_messages (conversation_id, message_id, pinned_by, pin_duration, expires_at) VALUES (%s, %s, %s, %s, %s)", (cid, mid, session["user_id"], duration, expires_at))
    except mysql.connector.IntegrityError:
        cursor.execute("UPDATE chat_pinned_messages SET pinned_by = %s, pin_duration = %s, expires_at = %s WHERE conversation_id = %s AND message_id = %s", (session["user_id"], duration, expires_at, cid, mid))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/messages/<int:cid>/unpin/<int:mid>", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_unpin_message(cid, mid):
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_pinned_messages WHERE conversation_id = %s AND message_id = %s", (cid, mid))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/messages/<int:cid>/pinned")
@login_required
@tool_required("chat")
def api_chat_pinned_messages(cid):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT cm.id, cm.message_text, cm.message_type, cm.file_name, cm.created_at, u.full_name AS sender_name, cpm.pin_duration, cpm.expires_at, cpm.id AS pin_id, pu.full_name AS pinned_by_name FROM chat_pinned_messages cpm JOIN chat_messages cm ON cpm.message_id = cm.id JOIN users u ON cm.sender_id = u.id JOIN users pu ON cpm.pinned_by = pu.id WHERE cpm.conversation_id = %s AND cm.is_deleted = 0 AND (cpm.expires_at IS NULL OR cpm.expires_at > NOW()) ORDER BY cpm.created_at DESC", (cid,))
    pins = cursor.fetchall(); cursor.close(); conn.close()
    return jsonify([{"message_id": p["id"], "message_text": p["message_text"], "message_type": p["message_type"], "file_name": p["file_name"], "sender_name": p["sender_name"], "pin_duration": p["pin_duration"], "pinned_by_name": p["pinned_by_name"], "pin_id": p["pin_id"], "created_at": p["created_at"].strftime("%Y-%m-%d %H:%M:%S"), "expires_at": p["expires_at"].strftime("%Y-%m-%d %H:%M:%S") if p["expires_at"] else None} for p in pins])

@app.route("/api/chat/onedrive-link")
@login_required
@tool_required("chat")
def api_chat_onedrive_link():
    return jsonify({"link": get_admin_setting("onedrive_folder_link", "")})



# ─── MESSAGE REACTIONS ────────────────────────────────────────────
@app.route("/api/chat/messages/<int:cid>/react/<int:mid>", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_react(cid, mid):
    data = request.get_json() or {}
    emoji = data.get("emoji", "")
    if not emoji: return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO chat_reactions (message_id, user_id, emoji) VALUES (%s, %s, %s)", (mid, session["user_id"], emoji))
    except mysql.connector.IntegrityError:
        cursor.execute("DELETE FROM chat_reactions WHERE message_id = %s AND user_id = %s AND emoji = %s", (mid, session["user_id"], emoji))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/messages/<int:cid>/reactions/<int:mid>")
@login_required
@tool_required("chat")
def api_chat_get_reactions(cid, mid):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT cr.emoji, cr.user_id, u.full_name FROM chat_reactions cr JOIN users u ON cr.user_id = u.id WHERE cr.message_id = %s ORDER BY cr.created_at ASC", (mid,))
    rows = cursor.fetchall(); cursor.close(); conn.close()
    grouped = {}
    for r in rows:
        grouped.setdefault(r["emoji"], []).append({"user_id": r["user_id"], "name": r["full_name"]})
    return jsonify(grouped)

# ─── GROUP MANAGEMENT ─────────────────────────────────────────────
@app.route("/api/chat/group/<int:cid>/info")
@login_required
@tool_required("chat")
def api_chat_group_info(cid):
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify({"success": False}), 403
    cursor.execute("SELECT * FROM chat_conversations WHERE id = %s", (cid,))
    conv = cursor.fetchone()
    cursor.execute("SELECT u.id, u.full_name, u.email FROM chat_participants cp JOIN users u ON cp.user_id = u.id WHERE cp.conversation_id = %s ORDER BY u.full_name", (cid,))
    members = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) AS cnt FROM chat_messages WHERE conversation_id = %s AND is_deleted = 0", (cid,))
    msg_count = cursor.fetchone()["cnt"]
    cursor.close(); conn.close()
    return jsonify({
        "success": True, "conv_type": conv["conv_type"], "group_name": conv.get("group_name"),
        "group_description": conv.get("group_description", ""),
        "created_by": conv["created_by"], "members": members, "message_count": msg_count,
        "created_at": conv["created_at"].strftime("%Y-%m-%d %H:%M:%S") if conv.get("created_at") else None,
    })

@app.route("/api/chat/group/<int:cid>/update", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_group_update(cid):
    data = request.get_json() or {}
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT created_by FROM chat_conversations WHERE id = %s", (cid,))
    conv = cursor.fetchone()
    if not conv: cursor.close(); conn.close(); return jsonify({"success": False}), 404
    if conv["created_by"] != session["user_id"] and session.get("role") != "admin":
        cursor.close(); conn.close()
        return jsonify({"success": False, "message": "Only group admin can edit."}), 403
    updates = []
    params = []
    if "group_name" in data and data["group_name"].strip():
        updates.append("group_name = %s"); params.append(data["group_name"].strip())
    if "group_description" in data:
        updates.append("group_description = %s"); params.append(data["group_description"].strip())
    if updates:
        params.append(cid)
        cursor.execute(f"UPDATE chat_conversations SET {', '.join(updates)} WHERE id = %s", tuple(params))
        if "group_name" in data:
            cursor.execute("INSERT INTO chat_messages (conversation_id, sender_id, message_text, message_type) VALUES (%s, %s, %s, 'system')", (cid, session["user_id"], f"{session['full_name']} renamed the group to '{data['group_name'].strip()}'"))
        conn.commit()
    cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/group/<int:cid>/add-member", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_group_add_member(cid):
    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id: return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT created_by FROM chat_conversations WHERE id = %s", (cid,))
    conv = cursor.fetchone()
    if not conv: cursor.close(); conn.close(); return jsonify({"success": False}), 404
    if conv["created_by"] != session["user_id"] and session.get("role") != "admin":
        cursor.close(); conn.close()
        return jsonify({"success": False, "message": "Only group admin can add members."}), 403
    try:
        cursor.execute("INSERT INTO chat_participants (conversation_id, user_id) VALUES (%s, %s)", (cid, user_id))
        cursor.execute("SELECT full_name FROM users WHERE id = %s", (user_id,))
        added_user = cursor.fetchone()
        name = added_user["full_name"] if added_user else "Someone"
        cursor.execute("INSERT INTO chat_messages (conversation_id, sender_id, message_text, message_type) VALUES (%s, %s, %s, 'system')", (cid, session["user_id"], f"{session['full_name']} added {name} to the group"))
        conn.commit()
    except mysql.connector.IntegrityError:
        cursor.close(); conn.close()
        return jsonify({"success": False, "message": "Already a member."})
    cursor.close(); conn.close()
    return jsonify({"success": True})

@app.route("/api/chat/group/<int:cid>/remove-member", methods=["POST"])
@login_required
@tool_required("chat")
def api_chat_group_remove_member(cid):
    data = request.get_json() or {}
    user_id = data.get("user_id")
    if not user_id: return jsonify({"success": False}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT created_by FROM chat_conversations WHERE id = %s", (cid,))
    conv = cursor.fetchone()
    if not conv: cursor.close(); conn.close(); return jsonify({"success": False}), 404
    if conv["created_by"] != session["user_id"] and session.get("role") != "admin" and user_id != session["user_id"]:
        cursor.close(); conn.close()
        return jsonify({"success": False, "message": "Only group creator or admin can remove members."}), 403
    cursor.execute("SELECT full_name FROM users WHERE id = %s", (user_id,))
    removed_user = cursor.fetchone()
    name = removed_user["full_name"] if removed_user else "Someone"
    cursor.execute("DELETE FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, user_id))
    action = "left the group" if user_id == session["user_id"] else f"removed {name} from the group"
    cursor.execute("INSERT INTO chat_messages (conversation_id, sender_id, message_text, message_type) VALUES (%s, %s, %s, 'system')", (cid, session["user_id"], f"{session['full_name']} {action}"))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({"success": True})

# ─── SEARCH MESSAGES ─────────────────────────────────────────────
@app.route("/api/chat/messages/<int:cid>/search")
@login_required
@tool_required("chat")
def api_chat_search_messages(cid):
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2: return jsonify([])
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM chat_participants WHERE conversation_id = %s AND user_id = %s", (cid, session["user_id"]))
    if not cursor.fetchone(): cursor.close(); conn.close(); return jsonify([])
    cursor.execute("SELECT cm.id, cm.message_text, cm.message_type, cm.file_name, cm.created_at, u.full_name AS sender_name FROM chat_messages cm JOIN users u ON cm.sender_id = u.id WHERE cm.conversation_id = %s AND cm.is_deleted = 0 AND (cm.message_text LIKE %s OR cm.file_name LIKE %s) ORDER BY cm.created_at DESC LIMIT 30", (cid, f"%{q}%", f"%{q}%"))
    results = cursor.fetchall(); cursor.close(); conn.close()
    return jsonify([{"id": r["id"], "message_text": r["message_text"], "message_type": r["message_type"], "file_name": r["file_name"], "sender_name": r["sender_name"], "created_at": r["created_at"].strftime("%Y-%m-%d %H:%M:%S")} for r in results])

# ─── FILE DOWNLOAD WITH HEADERS ──────────────────────────────────
@app.route("/api/chat/download/<filename>")
@login_required
def api_chat_download_file(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return render_template_string('<div style="font-family:sans-serif;text-align:center;padding:80px 20px;background:#0d1117;color:#e6edf3;min-height:100vh;"><div style="max-width:400px;margin:auto;"><div style="font-size:72px;opacity:0.3;margin-bottom:20px;">📁</div><h1 style="font-size:28px;color:#f85149;margin-bottom:10px;">File Not Found</h1><p style="color:#8b949e;font-size:14px;margin-bottom:24px;">This file has been moved to OneDrive or is no longer available on the server.</p><a href="{{ onedrive }}" target="_blank" style="display:inline-block;padding:10px 24px;background:#0078d4;color:white;border-radius:8px;text-decoration:none;font-weight:600;">Open OneDrive Folder</a><br><a href="/chat" style="display:inline-block;margin-top:16px;color:#388bfd;font-size:13px;">← Back to Chat</a></div></div>', onedrive=get_admin_setting('onedrive_folder_link', '#')), 404
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)



# ─── USER ONLINE STATUS ──────────────────────────────────────────
@app.route("/api/chat/heartbeat", methods=["POST"])
@login_required
def api_chat_heartbeat():
    conn = get_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_active = NOW() WHERE id = %s", (session["user_id"],))
        conn.commit(); cursor.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/chat/online-status")
@login_required
def api_chat_online_status():
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, full_name, last_active FROM users WHERE is_approved = 1 AND is_active = 1")
    users = cursor.fetchall(); cursor.close(); conn.close()
    result = []
    from datetime import datetime
    now = datetime.now()
    for u in users:
        is_online = False
        if u.get("last_active"):
            diff = (now - u["last_active"]).total_seconds()
            is_online = diff < 120  # online if active within 2 minutes
        result.append({"id": u["id"], "name": u["full_name"], "is_online": is_online,
                       "last_active": u["last_active"].strftime("%Y-%m-%d %H:%M:%S") if u.get("last_active") else None})
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════
# ROUTES – ADMIN SETTINGS
# ═══════════════════════════════════════════════════════════════════════

@app.route("/admin/settings")
@admin_required
def admin_settings():
    return render_template("admin_settings.html", onedrive_link=get_admin_setting("onedrive_folder_link", ""))

@app.route("/admin/settings/update", methods=["POST"])
@admin_required
def update_admin_settings():
    onedrive_link = request.form.get("onedrive_folder_link", "").strip()
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("INSERT INTO admin_settings (setting_key, setting_value) VALUES ('onedrive_folder_link', %s) ON DUPLICATE KEY UPDATE setting_value = %s", (onedrive_link, onedrive_link))
    conn.commit(); cursor.close(); conn.close()
    flash("Settings updated.", "success"); return redirect(url_for("admin_settings"))


# ═══════════════════════════════════════════════════════════════════════
# PETTY CASH
# ═══════════════════════════════════════════════════════════════════════

@app.route("/petty-cash/coimbatore")
@login_required
@tool_required("pettycash_cbe")
def pettycash_cbe():
    return render_template("petty_cash_coimbatore.html")


@app.route("/petty-cash/dindigul")
@login_required
@tool_required("pettycash_dgl")
def pettycash_dgl():
    return render_template("petty_cash_dindigul.html")


# ═══════════════════════════════════════════════════════════════════════
# LEAVE MANAGER
# ═══════════════════════════════════════════════════════════════════════

@app.route("/leave-manager")
@login_required
@tool_required("leavemanager")
def leavemanager():
    return render_template("RDM_Leave_Manager.html")


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