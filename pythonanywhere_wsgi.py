"""
PythonAnywhere WSGI Configuration for Thamarayyath Employee Portal
===================================================================
Target path on PythonAnywhere:
/var/www/<your_pythonanywhere_username>_pythonanywhere_com_wsgi.py

Instructions:
1. In PythonAnywhere's "Web" tab, click on your WSGI configuration file link.
2. Replace its entire contents with this code.
3. Replace 'your_username' below with your actual PythonAnywhere username.
4. Save the file and reload the web app.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# 1. Project Path Setup
# -----------------------------------------------------------------------------
# Replace 'your_username' with your PythonAnywhere account username:
PYTHONANYWHERE_USERNAME = "your_username"

# Typical project directory: /home/<username>/thamarayyath
PROJECT_DIR = f"/home/{PYTHONANYWHERE_USERNAME}/thamarayyath"

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# -----------------------------------------------------------------------------
# 2. Environment Variables (.env)
# -----------------------------------------------------------------------------
# Loads DJANGO_SECRET_KEY, DJANGO_DEBUG=False, DJANGO_ALLOWED_HOSTS, etc.
env_file = Path(PROJECT_DIR) / ".env"
if env_file.exists():
    load_dotenv(env_file)

# -----------------------------------------------------------------------------
# 3. Django Settings
# -----------------------------------------------------------------------------
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

# -----------------------------------------------------------------------------
# 4. WSGI Application Handler
# -----------------------------------------------------------------------------
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

