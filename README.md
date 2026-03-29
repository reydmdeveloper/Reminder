# 🔔 Project Reminder – Full Stack Web Application

A complete project reminder system built with **Flask**, **MySQL**, **HTML/CSS/JS**, and **Gmail SMTP** for email notifications.

---

## ✨ Features

### Authentication & Authorization
- **User Registration** with email OTP verification (via Gmail)
- **Admin Approval** – new registrations require admin approval before login
- **Login/Logout** with session management
- **Role-based Access** – Admin and User roles

### Admin Panel
- **User Management** – approve/reject registrations, activate/deactivate users
- **Role Management** – promote users to admin or demote
- **Password Reset** – admin can reset any user's password
- **Dashboard Stats** – total reminders, users, pending approvals

### Reminder System
- **Create Reminders** with project name + date/time
- **Duplicate Prevention** – same project name + time cannot be set twice
- **Auto Email Notification** – sends reminder email to ALL approved users at the scheduled time
- **Live Countdown** – real-time countdown timers on the dashboard
- **Edit/Delete** – users can modify their own reminders; admins can manage all

### Email System (Gmail SMTP)
- OTP verification emails during registration
- Admin notification when new user registers
- User notification when account is approved
- Project reminder emails sent to all users at scheduled time

---

## 📂 Project Structure

```
project_reminder/
├── app.py                  # Main Flask application (all routes & logic)
├── requirements.txt        # Python dependencies
├── database_setup.sql      # MySQL schema (auto-created by app)
├── .env.example            # Environment variable template
├── static/
│   ├── css/
│   │   └── style.css       # Complete stylesheet
│   └── js/
│       └── app.js          # Client-side JavaScript
└── templates/
    ├── base.html            # Root template
    ├── auth_base.html       # Auth pages layout
    ├── app_base.html        # Dashboard layout with sidebar
    ├── login.html           # Login page
    ├── register.html        # Registration page
    ├── verify_otp.html      # OTP verification page
    ├── dashboard.html       # Main dashboard
    ├── add_reminder.html    # Create new reminder
    ├── edit_reminder.html   # Edit existing reminder
    ├── admin_users.html     # Admin user management
    └── profile.html         # User profile & password change
```

---

## 🚀 Setup Instructions

### Prerequisites
- **Python 3.8+**
- **MySQL 5.7+** (or MariaDB)
- **Gmail Account** with App Password enabled

### Step 1: Clone / Extract the Project

```bash
cd project_reminder
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure MySQL

Make sure MySQL is running, then update credentials in `app.py` or set environment variables:

```bash
export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=your_mysql_password
export DB_NAME=project_reminder_db
```

### Step 4: Configure Gmail SMTP

1. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
2. Sign in and select **"Mail"** as the app
3. Generate and copy the 16-character app password
4. Set environment variables:

```bash
export GMAIL_USER=your_email@gmail.com
export GMAIL_APP_PASSWORD=abcdefghijklmnop
```

### Step 5: Run the Application

```bash
python app.py
```

The app will:
1. Automatically create the database and tables
2. Create a default admin account
3. Start the background reminder scheduler
4. Launch on `http://localhost:5000`

### Step 6: Login as Admin

```
Email:    admin@system.local
Password: admin123
```

⚠️ **Change the admin password immediately after first login!**

---

## 🔧 How It Works

### Registration Flow
1. User fills registration form → OTP sent to their email
2. User enters 6-digit OTP → account created (pending approval)
3. Admin receives notification email about new registration
4. Admin approves/rejects from User Management panel
5. User receives approval email → can now login

### Reminder Flow
1. Any logged-in user creates a reminder (project name + date/time)
2. Duplicate check prevents same project + time combination
3. Background scheduler runs every 30 seconds
4. When reminder time arrives → email sent to ALL approved active users
5. Reminder marked as "Sent" on the dashboard

### Background Scheduler
- Runs in a daemon thread alongside Flask
- Checks every 30 seconds for due reminders
- Sends emails to all approved & active users
- Logs all email send attempts in `reminder_logs` table

---

## 📋 Database Schema

| Table | Purpose |
|-------|---------|
| `users` | User accounts (name, email, password, role, approval status) |
| `otp_tokens` | Email verification codes with expiry |
| `reminders` | Project reminders with datetime and sent status |
| `reminder_logs` | Log of all reminder emails sent |

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `change-this...` | Flask session secret key |
| `DB_HOST` | `localhost` | MySQL host |
| `DB_USER` | `root` | MySQL username |
| `DB_PASSWORD` | *(empty)* | MySQL password |
| `DB_NAME` | `project_reminder_db` | Database name |
| `GMAIL_USER` | *(empty)* | Gmail address for sending emails |
| `GMAIL_APP_PASSWORD` | *(empty)* | Gmail App Password (16 chars) |

---

## 🛡️ Security Notes

- Passwords are hashed with Werkzeug's `scrypt` hasher
- Sessions expire after 2 hours
- OTP codes expire after 10 minutes
- Admin approval required before any user can access the system
- Role-based access control on all routes

---

## 📝 License

This project is provided as-is for educational and personal use.
