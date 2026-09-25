import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent


def _get_secret(name, default=''):
    """读取敏感配置：优先环境变量，其次本地配置文件 config/local_secrets.py
    （该文件包含生产环境真实密钥/凭据，已在 .gitignore 中排除，不会进入公开仓库）"""
    val = os.environ.get(name)
    if val:
        return val
    try:
        from config.local_secrets import SECRETS as _local_secrets
        return _local_secrets.get(name, default)
    except Exception:
        return default


SECRET_KEY = _get_secret(
    'DJANGO_SECRET_KEY',
    'django-insecure-dev-only-key-please-set-django-secret-key-in-production',
)
DEBUG = False
ALLOWED_HOSTS = ['CYXadmin.pythonanywhere.com', 'localhost', '127.0.0.1']
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'chat',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'chat.middleware.IPBlacklistMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 4}},
]
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# ============ 上传文件（图片 / 附件）配置 ============
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
# 单个附件大小上限（512MB，PythonAnywhere 实际请求体上限约 100MB）
MAX_UPLOAD_SIZE = 512 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/chat/'
LOGOUT_REDIRECT_URL = '/login/'

# ============ 邮件（邮箱验证）配置 ============
# 邮箱验证依赖 SMTP。配置优先级：环境变量 > config/local_secrets.py（不进公开仓库）。
#   - CHAT_EMAIL_HOST（如 smtp.qq.com）
#   - CHAT_EMAIL_PORT（如 465）
#   - CHAT_EMAIL_USER（发信邮箱）
#   - CHAT_EMAIL_PASSWORD（SMTP 授权码，不是邮箱登录密码）
# 出于安全考虑，代码中不内置任何真实凭据；未配置时邮件发送功能自动停用。
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = _get_secret('CHAT_EMAIL_HOST', 'smtp.qq.com')
EMAIL_PORT = int(_get_secret('CHAT_EMAIL_PORT', '465'))
EMAIL_USE_SSL = True
EMAIL_HOST_USER = _get_secret('CHAT_EMAIL_USER')
EMAIL_HOST_PASSWORD = _get_secret('CHAT_EMAIL_PASSWORD')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or 'no-reply@localhost'

# 站点地址（用于构造邮件中的验证链接）
BASE_URL = 'https://CYXadmin.pythonanywhere.com'

# Security headers
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
# Session / Cookie security
# 说明：CSRF/SESSION cookie 不设 Secure 标志，是为了兼容手机端以 http 直连访问的请求，
# 否则 secure cookie 在 http 请求下不会发送，导致“CSRF cookie not set” 403 阻断。
# PythonAnywhere 强制 https 时，https 下 cookie 仍正常工作，安全性不受影响。
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 86400

# ============ 邮箱验证开关（临时停用，代码保留）============
# 当前 = False：关闭“强制邮箱验证”，新用户注册后直接可用，不再要求收验证码；
#               原验证码逻辑（email_verify_code / verify_code_view / send_verification_email）全部保留未删。
# 2026-09-17 后请改回 True 恢复强制邮箱验证（停用15天，自 2026-09-02 起算）。
EMAIL_VERIFICATION_REQUIRED = False
