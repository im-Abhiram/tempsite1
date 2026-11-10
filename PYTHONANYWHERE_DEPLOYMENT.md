# Thamarayyath Employee Portal — PythonAnywhere Deployment Guide

This guide provides exact step-by-step instructions for deploying the **Thamarayyath Employee Portal** on the PythonAnywhere account for username: **`thamara`**.

- **GitHub Repository**: [`https://github.com/im-Abhiram/tempsite1.git`](https://github.com/im-Abhiram/tempsite1.git)
- **PythonAnywhere Account Username**: `thamara`
- **Live Portal URL**: `https://thamara.pythonanywhere.com`

---

## Architecture Overview on PythonAnywhere

| Component | Path on PythonAnywhere | Purpose |
| :--- | :--- | :--- |
| **Project Root** | `/home/thamara/tempsite1` | Django source code, templates, and apps |
| **Virtual Environment** | `/home/thamara/.virtualenvs/portal-env` | Isolated Python 3.10 / 3.11 environment |
| **WSGI File** | `/var/www/thamara_pythonanywhere_com_wsgi.py` | PythonAnywhere WSGI server entry point |
| **SQLite Database** | `/home/thamara/tempsite1/db.sqlite3` | Persistent local database in home directory |
| **Static Files (Served)**| `/home/thamara/tempsite1/staticfiles` | Production assets (Bootstrap, Chart.js, CSS) |
| **Public Media** | `/home/thamara/tempsite1/media/employee_photos` | Employee profile pictures |
| **Private Vault** | `/home/thamara/tempsite1/media/employee_documents` | Confidential documents (served via Django views) |
| **Logs** | `/home/thamara/tempsite1/logs/portal.log` | Rotating security and audit logs |

---

## Step 1: Clone the GitHub Repository on PythonAnywhere

1. Log in to your PythonAnywhere account at [https://www.pythonanywhere.com/](https://www.pythonanywhere.com/) with username **`thamara`**.
2. Open a **Bash Console** from the **Consoles** tab.
3. Clone your repository directly into `/home/thamara/tempsite1`:

```bash
git clone https://github.com/im-Abhiram/tempsite1.git /home/thamara/tempsite1
cd /home/thamara/tempsite1
```

---

## Step 2: Create and Activate Virtual Environment

In your active PythonAnywhere **Bash Console**, create a Python 3.10 virtual environment named `portal-env` and install the project dependencies:

```bash
# 1. Create the virtual environment
mkvirtualenv --python=/usr/bin/python3.10 portal-env

# 2. Navigate to your project directory
cd /home/thamara/tempsite1

# 3. Upgrade pip and install all required packages
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on dependencies:** All packages in `requirements.txt` (`Django`, `openpyxl`, `reportlab`, `pillow`, `python-dotenv`, `dj-database-url`, `asgiref`, `sqlparse`, `tzdata`) install cleanly from pre-compiled Linux wheels and do not require external compilers or paid network access.

---

## Step 3: Configure the Production `.env` File

Inside `/home/thamara/tempsite1/`, create your production `.env` file:

```bash
nano .env
```

Paste the following production configuration:

```ini
# Application Security
DJANGO_SECRET_KEY=k298v_thamarayyath_secure_key_9201948194829104810294810
DJANGO_DEBUG=False

# Allowed Hosts
DJANGO_ALLOWED_HOSTS=thamara.pythonanywhere.com,127.0.0.1,localhost

# CSRF Trusted Origins (Must match the HTTPS protocol of PythonAnywhere)
DJANGO_CSRF_TRUSTED_ORIGINS=https://thamara.pythonanywhere.com

# Database (Persistent local SQLite file in your home directory)
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

> **Tip:** You can generate a custom random secret key anytime in Python:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(50))"
> ```

Save and exit `nano` by pressing `Ctrl + O`, `Enter`, then `Ctrl + X`.

---

## Step 4: Run Migrations and Collect Static Files

In your Bash Console (with `portal-env` active):

```bash
cd /home/thamara/tempsite1

# 1. Apply database migrations to create persistent SQLite tables
python manage.py migrate

# 2. Collect all static assets (Bootstrap, Chart.js, CSS, JS) into staticfiles/
python manage.py collectstatic --noinput

# 3. Create your initial Superadmin account
python manage.py createsuperuser
```

When prompted:
- **Username**: `admin` (or your preferred superadmin username)
- **Email**: `admin@thamarayyath.com`
- **Password**: Enter a secure password (minimum 10 characters)

---

## Step 5: Configure the PythonAnywhere "Web" Tab

Navigate to the **Web** tab in PythonAnywhere:

1. Click **Add a new web app**.
2. Select **Manual configuration (including virtualenvs)**.
3. Select **Python 3.10**.
4. Once the web app is created, configure each section on the Web tab page:

### Code Section
- **Source code:** `/home/thamara/tempsite1`
- **Working directory:** `/home/thamara/tempsite1`

### Virtualenv Section
- **Virtualenv path:** `/home/thamara/.virtualenvs/portal-env`
  *(PythonAnywhere will show a green checkmark confirming `portal-env` is detected)*

### Static Files Section
Add the following two URL-to-Directory mappings:

| URL | Directory Path |
| :--- | :--- |
| `/static/` | `/home/thamara/tempsite1/staticfiles` |
| `/media/employee_photos/` | `/home/thamara/tempsite1/media/employee_photos` |

> **Security Note:** Do **NOT** map `/media/employee_documents/` or `/media/payroll_documents/` in the Web tab!
> These directories store private employee Aadhaar cards, contracts, and salary files. They are served exclusively through authenticated Django views (`DocumentServeView`) after verifying user permissions.

### Security / HTTPS Section
- Set **Force HTTPS** to **Enabled**.

---

## Step 6: Configure the WSGI File

1. On the **Web** tab, click on the **WSGI configuration file** link:
   `/var/www/thamara_pythonanywhere_com_wsgi.py`
2. Erase any existing placeholder content.
3. Paste the following configuration:

```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 1. Add project directory to sys.path
username = "thamara"
project_home = f"/home/{username}/tempsite1"

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

4. Click the green **Save** button in the upper-right corner.

---

## Step 7: Reload and Launch the Portal

1. Return to the PythonAnywhere **Web** tab.
2. Click the green button: **Reload thamara.pythonanywhere.com**.
3. Visit your live portal in the browser:
   [**https://thamara.pythonanywhere.com**](https://thamara.pythonanywhere.com)

---

## Post-Deployment Verification Checklist

Log in as Superadmin at `https://thamara.pythonanywhere.com/accounts/login/` and verify:

- [ ] **Role Management**:
  - Visit `/accounts/users/create/`.
  - Create one **Accountant** user and one **Owner** user.
- [ ] **Employee Profiles**:
  - Log in as the Accountant user.
  - Create an employee with designation, shift, salary rate, and bank details.
  - Upload a profile picture and a test PDF document.
- [ ] **Attendance & Corrections**:
  - Open `/attendance/` to mark attendance punches.
  - Test an attendance correction and verify mandatory reason recording.
- [ ] **Multi-Period Payroll**:
  - Run payroll at `/payroll/generate/` for any cycle (Weekly, Biweekly, Three-Weekly, Monthly).
  - Verify calculations, bonuses, deductions, and click **Finalize**.
- [ ] **Owner Read-Only Enforcement**:
  - Log in as the Owner user.
  - Verify access to high-level dashboards and attendance trends.
  - Confirm employee editing, punch logging, payroll generation, and bank account numbers are completely blocked or hidden.
- [ ] **Reports & Sanitized CSV Export**:
  - Download attendance and payroll reports from `/reports/` and check `SAFE_STR` formula protection.
- [ ] **Live SQLite Backup**:
  - Log in as Superadmin and visit `/core/backup/`.
  - Check storage metrics and click **Download SQLite Database Backup (.sqlite3)**.

---

## Operational & Maintenance Tips for `thamara.pythonanywhere.com`

### 1. Free Account 3-Month Renewal
PythonAnywhere free web apps expire every 3 months. When you receive PythonAnywhere's email reminder, simply log in to your dashboard and click the **Run until 3 months from today** button on the Web tab.

### 2. Disk Space Monitoring (512 MB Limit)
Your portal includes an integrated disk monitor at `/core/backup/`. Employee document uploads are capped at 10 MB per file, and system logs (`logs/portal.log`) automatically rotate at 5 MB each.

### 3. Server Logs
If you encounter any unexpected error, check the live logs on the Web tab:
- **Error log**: `/var/log/thamara.pythonanywhere.com.error.log`
- **Server log**: `/var/log/thamara.pythonanywhere.com.server.log`

## How to Safely Update the Portal on PythonAnywhere (Without Losing Any Data)

When you make updates to the code on your computer and push them to GitHub, follow this guide to update your live PythonAnywhere site.

### Why Your Data is 100% Safe:
1. **Database (`db.sqlite3`) is untracked by Git**: Your SQLite database is explicitly excluded via `.gitignore`. Running `git pull` will **never** overwrite, delete, or reset your existing employee records, attendance punches, or user accounts.
2. **Uploaded Files (`media/`) are untracked by Git**: All employee photos and vault documents are stored locally in `media/` and are never touched by Git.
3. **Environment Settings (`.env`) are untracked by Git**: Your production secret key and passwords remain untouched.
4. **Django Migrations Preserve Data**: Running `python manage.py migrate` only adds new tables or columns (such as the new `is_paid` wage status columns) to your existing database. It does not drop existing records.

---

### Step-by-Step Safe Update Procedure:

Open a **Bash Console** on PythonAnywhere and run the following steps:

#### Step 1: Create a Safety Snapshot of Your Database
Before pulling updates or applying database migrations, make a quick local backup:
```bash
cd /home/thamara/tempsite1
cp db.sqlite3 db.sqlite3.bak_$(date +%Y%m%d_%H%M%S)
```
*(This creates an instant timestamped copy like `db.sqlite3.bak_20261109_163000` in your folder. If you ever need to restore, just copy it back).*

> **Tip:** You can also download a copy of your `.sqlite3` file anytime directly from your browser by logging into the portal as Superadmin and visiting `/core/backup/`.

#### Step 2: Activate Your Virtual Environment
```bash
workon portal-env
cd /home/thamara/tempsite1
```

#### Step 3: Pull Latest Code from GitHub
```bash
git pull origin main
```

> **Troubleshooting Git Conflicts:**
> If Git says *"error: Your local changes to the following files would be overwritten by merge"*, someone edited code files directly on PythonAnywhere. To safely discard those edits and pull clean GitHub code (without touching your database or media):
> ```bash
> git stash
> git pull origin main
> ```

#### Step 4: Update Any New Python Packages
```bash
pip install -r requirements.txt
```

#### Step 5: Apply Database Migrations
```bash
python manage.py migrate
```
This safely applies newly added schema migrations (such as wage disbursement tracking fields) while keeping all existing employees, shifts, attendance punches, and salary data completely intact.

#### Step 6: Collect New Static Files (CSS, JS, Icons)
```bash
python manage.py collectstatic --noinput
```

#### Step 7: Reload the Web App
Go to the **Web** tab in PythonAnywhere and click the green button:
**Reload thamara.pythonanywhere.com**

*(Or reload directly from the Bash console by running)*:
```bash
touch /var/www/thamara_pythonanywhere_com_wsgi.py
```

---

### Quick 1-Step Fast Update Command
Once you are familiar with the process, you can copy-paste this single line into your PythonAnywhere Bash Console to run the entire safe update automatically:

```bash
cd /home/thamara/tempsite1 && workon portal-env && cp db.sqlite3 db.sqlite3.bak_$(date +%Y%m%d_%H%M%S) && git pull origin main && pip install -r requirements.txt && python manage.py migrate && python manage.py collectstatic --noinput && touch /var/www/thamara_pythonanywhere_com_wsgi.py
```
This single command safely creates a backup, pulls latest code, updates packages, migrates the database, collects static files, and reloads your live website!
