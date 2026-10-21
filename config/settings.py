import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'development-only-change-before-deploying')
DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
INSTALLED_APPS = ['planner']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': {'timeout': 20}}}
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True}]
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = True
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache', 'LOCATION': BASE_DIR / '.cache' / 'responses', 'OPTIONS': {'MAX_ENTRIES': 10000}}}
LOCK_DIR = BASE_DIR / '.cache' / 'locks'
PHOTON_URL = os.environ.get('PHOTON_URL', 'https://photon.komoot.io')
OSRM_URL = os.environ.get('OSRM_URL', 'https://routing.openstreetmap.de/routed-car')
PROVIDER_USER_AGENT = os.environ.get('PROVIDER_USER_AGENT', 'USFuelPlanner/1.0 (local assignment demo)')
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
