# Settings initialization
# Import from development by default (change to production in deployment)
import os

environment = os.environ.get('DJANGO_ENV', 'development')

if environment == 'production':
    from .production import *
else:
    from .development import *
