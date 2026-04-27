"""
Explicit PostgreSQL settings
"""
from .base import *  # Import all base settings

# Override database settings explicitly
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pcr_database',  # Make sure this matches the DB you created
        'USER': 'postgres',      # User for connecting
        'PASSWORD': 'newpassword',  # Make sure this matches the password
        'HOST': 'localhost',     # This should be localhost
        'PORT': '5433',          # Make sure this is correct port
    }
}

# Add a print statement for debugging
import sys
print("USING POSTGRESQL SETTINGS", file=sys.stderr)