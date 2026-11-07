# Thamarayyath Employee Portal — PythonAnywhere Deployment Guide

This guide provides step-by-step instructions for deploying the **Thamarayyath Employee Portal** on a **PythonAnywhere Free (Beginner) Account**.

The portal has been engineered specifically for PythonAnywhere's free hosting tier:
- **Zero external service dependencies:** No external PostgreSQL, Supabase, Redis, Celery, AWS S3, or background workers required.
- **Embedded SQLite:** Fully persistent database in your application home directory with atomic transaction guarantees and live online backup (`sqlite3.backup`).
- **High-Efficiency Memory & Storage:** Optimized for PythonAnywhere's 512 MB disk quota with real-time storage tracking and safe private document storage.
- **Role-Based Access Control:** Three strict roles (`SUPERADMIN`, `ACCOUNTANT`, `OWNER`) enforced at the Django backend level.
- **Localization:** Asia/Kolkata timezone and Indian Rupee (₹) currency formatting.

---

## Architecture Overview on PythonAnywhere

| Component | Path on PythonAnywhere | Purpose |
| :--- | :--- | :--- |
| **Project Root** | `/home/<username>/thamarayyath` | Django source code, templates, and apps |
| **Virtual Environment** | `/home/<username>/.virtualenvs/portal-env` | Isolated Python 3.10 / 3.11 environment |
| **WSGI File** | `/var/www/<username>_pythonanywhere_com_wsgi.py` | Web server entry point |
| **SQLite Database** | `/home/<username>/thamarayyath/db.sqlite3` | Persistent local database |
| **Static Files (Served)**| `/home/<username>/thamarayyath/staticfiles` | Production assets (Bootstrap, Chart.js, CSS) |
| **Public Media** | `/home/<username>/thamarayyath/media/employee_photos` | Employee profile pictures |
| **Private Vault** | `/home/<username>/thamarayyath/media/employee_documents` | Confidential documents (served via Django views) |
| **Logs** | `/home/<username>/thamarayyath/logs/portal.log` | Rotating security and audit logs |

---

## Step 1: Create Your PythonAnywhere Account

1. Go to [https://www.pythonanywhere.com/](https://www.pythonanywhere.com/) and register a free **Beginner Account**.
2. Note your **username** (e.g., `thamarayyath`). Your live URL will be:
   `https://<your-username>.pythonanywhere.com`

---

## Step 2: Upload Project Files to PythonAnywhere

You can upload the project using either **Git** (recommended) or as a **Zip File**.

### Option A: Via Git (Recommended)

1. Open a **Bash Console** from your PythonAnywhere Dashboard (**Consoles** tab).
2. Clone your repository into your home directory:
   ```bash
   git clone https://github.com/<your-repo>/thamarayyath.git /home/<your-username>/thamarayyath
   cd /home/<your-username>/thamarayyath
   ```

### Option B: Via Zip File Upload

1. On your local machine, zip the project files (excluding `.venv`, `__pycache__`, and `.git`).
2. On PythonAnywhere, navigate to the **Files** tab.
3. In `/home/<your-username>/`, use the **Upload a file** button to upload your `.zip` archive.
4. Open a **Bash Console** and unzip:
   ```bash
   mkdir -p /home/<your-username>/thamarayyath
   unzip /home/<your-username>/<your-archive>.zip -d /home/<your-username>/thamarayyath
   cd /home/<your-username>/thamarayyath
   ```

---

## Step 3: Create and Activate Virtual Environment

In your PythonAnywhere **Bash Console**, run:

```bash
# Create an isolated Python 3.10 virtual environment
mkvirtualenv --python=/usr/bin/python3.10 portal-env

# Alternatively, if virtualenvwrapper is not configured:
# python3.10 -m venv /home/<your-username>/.virtualenvs/portal-env
# source /home/<your-username>/.virtualenvs/portal-env/bin/activate

# Verify you are in the project folder and venv is active
cd /home/<your-username>/thamarayyath
which python
```

Install all project dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on dependencies:** All packages in `requirements.txt` (`Django`, `openpyxl`, `reportlab`, `pillow`, `python-dotenv`, `dj-database-url`, `asgiref`, `sqlparse`, `tzdata`) install from pre-built wheels and require zero external C compilers or restricted network calls.

---

## Step 4: Configure the Production `.env` File

Inside `/home/<your-username>/thamarayyath/`, create your production `.env` file:

```bash
nano .env
```

Paste the following configuration, replacing `<your-username>` with your actual PythonAnywhere username:

```ini
# Application Security
DJANGO_SECRET_KEY=generate-a-strong-random-key-here-min-50-characters
DJANGO_DEBUG=False

# Allowed Hosts (PythonAnywhere domain and local loopback)
DJANGO_ALLOWED_HOSTS=<your-username>.pythonanywhere.com,127.0.0.1,localhost

# CSRF Trusted Origins (Must match the HTTPS protocol of PythonAnywhere)
DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-username>.pythonanywhere.com

# Database (Persistent local SQLite file)
DATABASE_URL=sqlite:///db.sqlite3

# Localization
TIME_ZONE=Asia/Kolkata
LANGUAGE_CODE=en-us

# Security Controls
SESSION_COOKIE_AGE=3600
SESSION_EXPIRE_AT_BROWSER_CLOSE=True
SECURE_BROWSER_XSS_FILTER=True
SECURE_CONTENT_TYPE_NOSNIFF=True
X_FRAME_OPTIONS=DENY
```

> **Tip:** You can generate a cryptographically strong secret key directly in Python:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(50))"
> ```

Save and exit `nano` by pressing `Ctrl + O`, `Enter`, and then `Ctrl + X`.

---

## Step 5: Run Database Migrations and Collect Static Files

In the active Bash Console (with `portal-env` activated):

```bash
cd /home/<your-username>/thamarayyath

# 1. Apply all database migrations
python manage.py migrate

# 2. Collect all static files into staticfiles/
python manage.py collectstatic --noinput

# 3. Create initial Superadmin user
python manage.py createsuperuser
```

Enter your username, email, and a secure password (minimum 10 characters).

---

## Step 6: Configure the PythonAnywhere "Web" Tab

Navigate to the **Web** tab in PythonAnywhere:

1. Click **Add a new web app**.
2. Select **Manual configuration (including virtualenvs)**.
3. Choose **Python 3.10**.
4. Once created, configure the sections on the Web tab page:

### Code Section
- **Source code:** `/home/<your-username>/thamarayyath`
- **Working directory:** `/home/<your-username>/thamarayyath`

### Virtualenv Section
- **Virtualenv path:** `/home/<your-username>/.virtualenvs/portal-env`
  *(PythonAnywhere will show a checkmark confirming the virtualenv was detected)*

### Static Files Section
Add the following URL-to-Directory mappings:

| URL | Directory Path |
| :--- | :--- |
| `/static/` | `/home/<your-username>/thamarayyath/staticfiles` |
| `/media/employee_photos/` | `/home/<your-username>/thamarayyath/media/employee_photos` |

> **Security Note:** Do **NOT** map `/media/employee_documents/` or `/media/payroll_documents/` in the Web tab!
> These directories contain sensitive Aadhaar cards, bank details, and contracts. They are intentionally served through Django views (`DocumentServeView`) after verifying user permissions, preventing unauthenticated access.

### Security / HTTPS Section
- Find **Force HTTPS** and set it to **Enabled**.

---

## Step 7: Configure the WSGI File

1. On the **Web** tab, click the link under **WSGI configuration file** (e.g., `/var/www/<your-username>_pythonanywhere_com_wsgi.py`).
2. Clear any default placeholder content.
3. Paste the following configuration:

```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 1. Add your project directory to sys.path
username = "<your-username>"  # <-- REPLACE with your actual PythonAnywhere username
project_home = f"/home/{username}/thamarayyath"

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. Load environment variables from .env
env_file = Path(project_home) / ".env"
if env_file.exists():
    load_dotenv(env_file)

# 3. Set the Django settings module
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

# 4. Initialize Django WSGI application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

4. Click **Save** (top right).

---

## Step 8: Reload and Verify the Web Application

1. Return to the **Web** tab.
2. Click the big green button: **Reload <your-username>.pythonanywhere.com**.
3. Open your portal in a new tab:
   `https://<your-username>.pythonanywhere.com`

---

## Post-Deployment Verification Checklist

Verify all core modules using your Superadmin credentials:

- [ ] **Login & Authentication:**
  - Login at `https://<your-username>.pythonanywhere.com/accounts/login/`.
  - Verify redirection to the Superadmin Dashboard.
- [ ] **Role Management:**
  - Navigate to **User Management** (`/accounts/users/create/`).
  - Create one **Accountant** account (e.g. `accountant1`) and one **Owner** account (e.g. `owner1`).
- [ ] **Employee Management:**
  - Log in as the Accountant.
  - Create a test employee profile with salary details and bank information.
  - Upload a profile photo and an employee document.
- [ ] **Attendance Tracking:**
  - Open **Attendance Dashboard** (`/attendance/`).
  - Mark daily attendance and perform a sample attendance correction with a mandatory reason.
- [ ] **Payroll Generation:**
  - Navigate to **Payroll** (`/payroll/generate/`).
  - Run payroll for any cycle (Weekly, Biweekly, Three-Weekly, Monthly).
  - Review calculations, verify Indian Rupee (₹) formatting, and click **Finalize**.
- [ ] **Owner Read-Only View:**
  - Log in as the Owner user.
  - Verify Owner can view dashboards, reports, and attendance trends.
  - Verify Owner cannot see action buttons (Create Employee, Edit, Mark Attendance, Generate Payroll).
  - Verify Owner cannot view restricted bank account numbers or download vault documents.
- [ ] **Reporting & Exporting:**
  - Navigate to **Reports Hub** (`/reports/`).
  - Export CSV reports (Employee Roster, Attendance Summary, Payroll Summary) and verify formula injection protection (`SAFE_STR`).
- [ ] **Backups & Storage:**
  - Log in as Superadmin and visit `/core/backup/`.
  - Verify real-time storage metrics (Database size, Media storage, Log file size).
  - Click **Download SQLite Database Backup (.sqlite3)** and verify successful download without application locking.

---

## Maintenance and Operational Tips for PythonAnywhere Free Tier

### 1. PythonAnywhere Free Account "Keep-Alive" Requirement
PythonAnywhere free web apps expire every **3 months** unless extended.
- You will receive an email reminder from PythonAnywhere.
- Log in to your PythonAnywhere dashboard and click the **Run until 3 months from today** button on the Web tab to keep the app active.

### 2. Disk Quota Management (512 MB Limit)
The free tier allocates 512 MB of total disk space.
- Monitor your storage directly from the portal's **Storage & Backups Dashboard** (`/core/backup/`).
- Employee document uploads are capped at 10 MB per file, and images are validated to keep disk usage compact.
- The portal uses rotating log files (`logs/portal.log`) capped at 5 MB each with up to 10 backups.

### 3. Viewing Server Logs for Troubleshooting
If you encounter a `500 Internal Server Error`:
1. Go to the **Web** tab.
2. In the **Log files** section, click on the **Error log**:
   `/var/log/<your-username>.pythonanywhere.com.error.log`
3. Scroll to the bottom of the log to see the Python traceback.

### 4. Updating Code in the Future
To push updates from Git:
```bash
cd /home/<your-username>/thamarayyath
git pull
python manage.py migrate
python manage.py collectstatic --noinput
```
Then click **Reload** on the PythonAnywhere **Web** tab.

