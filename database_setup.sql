-- ═══════════════════════════════════════════════════════════════
-- REYDM – Database Setup Script (Updated with Chat + Pin + Delete)
-- The app.py init_db() function handles all this automatically.
-- This SQL file is provided for reference or manual setup.
-- ═══════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS `reydm_db`;
USE `reydm_db`;

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
);

CREATE TABLE IF NOT EXISTS otp_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(150) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    purpose ENUM('register', 'reset_password') DEFAULT 'register',
    is_used TINYINT(1) DEFAULT 0,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TABLE IF NOT EXISTS reminder_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reminder_id INT NOT NULL,
    sent_to VARCHAR(150) NOT NULL,
    status ENUM('sent', 'failed') DEFAULT 'sent',
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ns_employees (
    id INT AUTO_INCREMENT PRIMARY KEY,
    emp_id VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    dept VARCHAR(60) DEFAULT '',
    status ENUM('active', 'resigned') DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ns_attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    emp_id VARCHAR(20) NOT NULL,
    att_date DATE NOT NULL,
    present TINYINT(1) DEFAULT 1,
    UNIQUE KEY unique_emp_date (emp_id, att_date)
);

CREATE TABLE IF NOT EXISTS attendance_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    login_date DATE NOT NULL,
    login_time DATETIME NOT NULL,
    logout_time DATETIME DEFAULT NULL,
    hours_spent DECIMAL(5,2) DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

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
);

-- ═══════════════════════════════════════════════════════════════
-- CHAT TABLES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS chat_conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conv_type ENUM('private', 'group') DEFAULT 'private',
    group_name VARCHAR(150) DEFAULT NULL,
    created_by INT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_participants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    user_id INT NOT NULL,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_conv_user (conversation_id, user_id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    sender_id INT NOT NULL,
    message_text TEXT DEFAULT NULL,
    message_type ENUM('text', 'file', 'image', 'system') DEFAULT 'text',
    file_name VARCHAR(500) DEFAULT NULL,
    file_url VARCHAR(2000) DEFAULT NULL,
    file_size VARCHAR(50) DEFAULT NULL,
    is_deleted TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_read_receipts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    user_id INT NOT NULL,
    last_read_message_id INT DEFAULT 0,
    read_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_conv_user_read (conversation_id, user_id)
);

-- Pinned messages with expiry duration
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
);

-- Per-user message deletions (delete for me only)
CREATE TABLE IF NOT EXISTS chat_deleted_for_me (
    id INT AUTO_INCREMENT PRIMARY KEY,
    message_id INT NOT NULL,
    user_id INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_msg_user_del (message_id, user_id)
);

-- ═══════════════════════════════════════════════════════════════
-- ADMIN SETTINGS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS admin_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT DEFAULT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT IGNORE INTO admin_settings (setting_key, setting_value)
VALUES ('onedrive_folder_link', '');