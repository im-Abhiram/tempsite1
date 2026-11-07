# Thamarayyath Employee Portal — PythonAnywhere Deployment Guide

This guide provides exact step-by-step instructions for deploying the **Thamarayyath Employee Portal** on the PythonAnywhere account for username: **`thamara`**.

- **GitHub Repository**: [`https://github.com/im-Abhiram/tempsite1.git`](https://github.com/im-Abhiram/tempsite1.git)
- **PythonAnywhere Account Username**: `thamara`
- **Live Portal URL**: `https://thamara.pythonanywhere.com`

---

## Architecture Overview on PythonAnywhere

| Component | Path on PythonAnywhere | Purpose |
| :--- | :--- | :--- |
| **Project Root** | `/home/thamara/thamarayyath` | Django source code, templates, and apps |
| **Virtual Environment** | `/home/thamara/.virtualenvs/portal-env` | Isolated Python 3.10 / 3.11 environment |
| **WSGI File** | `/var/www/thamara_pythonanywhere_com_wsgi.py` | PythonAnywhere WSGI server entry point |
| **SQLite Database** | `/home/thamara/thamarayyath/db.sqlite3` | Persistent local database in home directory |
| **Static Files (Served)**| `/home/thamara/thamarayyath/staticfiles` | Production assets (Bootstrap, Chart.js, CSS) |
| **Public Media** | `/home/thamara/thamarayyath/media/employee_photos` | Employee profile pictures |
| **Private Vault** | `/home/thamara/thamarayyath/media/employee_documents` | Confidential documents (served via Django views) |
| **Logs** | `/home/thamara/thamarayyath/logs/portal.log` | Rotating security and audit logs |

---

## Step 1: Clone the GitHub Repository on PythonAnywhere

1. Log in to your PythonAnywhere account at [https://www.pythonanywhere.com/](https://www.pythonanywhere.com/) with username **`thamara`**.
2. Open a **Bash Console** from the **Consoles** tab.
3. Clone your repository directly into `/home/thamara/thamarayyath`:

```bash
git clone https://github.com/im-Abhiram/tempsite1.git /home/thamara/thamarayyath
cd /home/thamara/thamarayyath
```

---

## Step 2: Create and Activate Virtual Environment

In your active PythonAnywhere **Bash Console**, create a Python 3.10 virtual environment named `portal-env` and install the project dependencies:

```bash
# 1. Create the virtual environment
mkvirtualenv --python=/usr/bin/python3.10 portal-env

# 2. Navigate to your project directory
cd /home/thamara/thamarayyath

# 3. Upgrade pip and install all required packages
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note on dependencies:** All packages in `requirements.txt` (`Django`, `openpyxl`, `reportlab`, `pillow`, `python-dotenv`, `dj-database-url`, `asgiref`, `sqlparse`, `tzdata`) install cleanly from pre-compiled Linux wheels and do not require external compilers or paid network access.

---

## Step 3: Configure the Production `.env` File

Inside `/home/thamara/thamarayyath/`, create your production `.env` file:

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
cd /home/thamara/thamarayyath

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
- **Source code:** `/home/thamara/thamarayyath`
- **Working directory:** `/home/thamara/thamarayyath`

### Virtualenv Section
- **Virtualenv path:** `/home/thamara/.virtualenvs/portal-env`
  *(PythonAnywhere will show a green checkmark confirming `portal-env` is detected)*

### Static Files Section
Add the following two URL-to-Directory mappings:

| URL | Directory Path |
| :--- | :--- |
| `/static/` | `/home/thamara/thamarayyath/staticfiles` |
| `/media/employee_photos/` | `/home/thamara/thamarayyath/media/employee_photos` |

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

### 4. Deploying Updates from GitHub
Whenever you make changes and push to GitHub, update PythonAnywhere in your Bash Console:
```bash
cd /home/thamara/thamarayyath
git pull origin main
python manage.py migrate
python manage.py collectstatic --noinput
```
Then click **Reload thamara.pythonanywhere.com** on the Web tab.
