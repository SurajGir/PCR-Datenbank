"""
Settings initialization for PCR Datenbank project.
"""

import os

# Default to development settings
environment = os.environ.get('DJANGO_ENVIRONMENT', 'local')

if environment == 'production':
    from .production import *  # noqa
else:
    from .local import *  # noqa