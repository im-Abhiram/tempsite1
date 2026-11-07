"""
PythonAnywhere WSGI Configuration for Thamarayyath Employee Portal
===================================================================
Target path on PythonAnywhere:
/var/www/thamara_pythonanywhere_com_wsgi.py

Instructions:
1. In PythonAnywhere's "Web" tab, click on your WSGI configuration file link.
2. Replace its entire contents with this code.
3. Save the file and click "Reload thamara.pythonanywhere.com".
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# 1. Project Path Setup
# -----------------------------------------------------------------------------
PYTHONANYWHERE_USERNAME = "thamara"
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
