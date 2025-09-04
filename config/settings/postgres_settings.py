"""
Explicit PostgreSQL settings
"""
from .base import *  # Import all base settings

# Override database settings explicitly
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pcr_database',
        'USER': 'postgres',
        'PASSWORD': 'Mdx1234',
        'HOST': 'localhost',
        'PORT': '5433',
    }
}

# Add a print statement for debugging
import sys
print("USING POSTGRESQL SETTINGS", file=sys.stderr)