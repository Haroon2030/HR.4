# Settings initialization
# Import from development by default (change to production in deployment)
import os
import environ

# Read .env file to get DJANGO_ENV
env = environ.Env()
try:
    # Try to read from project root/.env
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        environ.Env.read_env(str(env_path))
except Exception:
    pass  # If .env doesn't exist or can't be read, continue with os.environ

environment = env('DJANGO_ENV', default=os.environ.get('DJANGO_ENV', 'development'))

if environment == 'production':
    from .production import *
else:
    from .development import *
