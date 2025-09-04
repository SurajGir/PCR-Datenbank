"""
Local development settings for PCR Datenbank project.
"""

from .base import *  # noqa

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY should be the same as in base.py

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Database - you can keep using SQLite for local development
# This should already be configured in base.py

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Debug toolbar settings (optional, install with pip if needed)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']

# Disable password validation in development (optional)
# AUTH_PASSWORD_VALIDATORS = []