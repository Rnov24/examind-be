# EXAMIND Database (`database/`)

This directory contains database schemas, migration definitions, seed data, and instructions for managing the MySQL database served via XAMPP.

## 🛠️ XAMPP MySQL Setup Guide

1. **Start XAMPP Control Panel**
   - Click **Start** on the **MySQL** module (and Apache if using phpMyAdmin).
   - Ensure MySQL is running on default port `3306`.

2. **Access MySQL / phpMyAdmin**
   - Web GUI: [http://localhost/phpmyadmin](http://localhost/phpmyadmin)
   - CLI:
     ```bash
     mysql -u root -p
     # (Default XAMPP root password is empty — press Enter)
     ```

3. **Initialize the Database**
   - Execute the SQL script in `schema.sql`:
     ```sql
     CREATE DATABASE IF NOT EXISTS examind CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
     ```

4. **Connection String in Backend**
   - Set in `backend/.env`:
     ```env
     DATABASE_URL=mysql+pymysql://root:@localhost:3306/examind
     ```

---

## 📁 Subdirectories

- **`migrations/`**: Alembic / SQL migration scripts for schema evolution.
- **`seeds/`**: Seed scripts and mock data for initial development and testing.
