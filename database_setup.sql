-- ═══════════════════════════════════════════════════════════════
-- PROJECT REMINDER – Database Setup Script
-- Run this if you want to manually create the database & tables
-- ═══════════════════════════════════════════════════════════════

CREATE DATABASE IF NOT EXISTS `project_reminder_db`;
USE `project_reminder_db`;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'user') DEFAULT 'user',
    is_approved TINYINT(1) DEFAULT 0,
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- OTP tokens for email verification
CREATE TABLE IF NOT EXISTS otp_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(150) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    purpose ENUM('register', 'reset_password') DEFAULT 'register',
    is_used TINYINT(1) DEFAULT 0,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Reminders table
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

-- Reminder email log
CREATE TABLE IF NOT EXISTS reminder_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    reminder_id INT NOT NULL,
    sent_to VARCHAR(150) NOT NULL,
    status ENUM('sent', 'failed') DEFAULT 'sent',
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
);

-- Default admin user (password: admin123)
-- The password hash below is for 'admin123' — change it after first login!
INSERT INTO users (full_name, email, password_hash, role, is_approved)
VALUES ('Administrator', 'admin@system.local',
        'scrypt:32768:8:1$placeholder$hash', 'admin', 1)
ON DUPLICATE KEY UPDATE id=id;

-- NOTE: The app.py init_db() function handles all this automatically.
-- This SQL file is provided for reference or manual setup only.
