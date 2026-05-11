"""
Production settings for PCR Datenbank project (Render.com Version).
"""

import os
import dj_database_url
from .base import * # noqa

# Grab the secret key from Render's environment variables
SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-key-do-not-use-in-production')

# Security: Turn off debug mode so users don't see raw code errors
DEBUG = False

# Allow any URL to access the site (Render will handle the actual routing)
ALLOWED_HOSTS = ['*']

# ---------------------------------------------------------
# CLOUD DATABASE SETTINGS (Render)
# ---------------------------------------------------------
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600
    )
}

# ---------------------------------------------------------
# CLOUD STATIC FILES (Whitenoise)
# ---------------------------------------------------------
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ---------------------------------------------------------
# BASIC SECURITY HEADERS
# ---------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# ---------------------------------------------------------
# CLOUD LOGGING (Sends errors to the Render Dashboard)
# ---------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}