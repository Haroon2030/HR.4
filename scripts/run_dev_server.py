"""تشغيل خادم التطوير على المنفذ الممرَّر في متغير PORT (الافتراضي 8000).

يُستخدم من .claude/launch.json حتى لا يتعارض المنفذ مع خوادم أخرى.
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')


def main():
    os.chdir(BACKEND)
    sys.path.insert(0, os.getcwd())
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    os.environ.setdefault('DJANGO_ENV', 'development')
    port = os.environ.get('PORT', '8000')
    from django.core.management import execute_from_command_line

    execute_from_command_line(['manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'])


if __name__ == '__main__':
    main()
