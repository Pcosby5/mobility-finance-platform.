from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent

env = environ.Env(DEBUG=(bool, False))
# Real environment variables take precedence over the local development file.
environ.Env.read_env(PROJECT_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "rest_framework_simplejwt.token_blacklist",
    "users.apps.UsersConfig",
    "customers.apps.CustomersConfig",
    "credit.apps.CreditConfig",
    "vehicles.apps.VehiclesConfig",
    "loans.apps.LoansConfig",
    "payments.apps.PaymentsConfig",
    "telemetry.apps.TelemetryConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collectstatic output directly from the web process, so gunicorn
    # does not need a separate static server in the demo containers.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("This project requires PostgreSQL.")

AUTH_USER_MODEL = "users.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{validator}"}
    for validator in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_THROTTLE_RATES": {"auth": "20/min"},
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    # RiskBand and Alert.Severity share the same (value, label) choice set;
    # pin one shared enum component instead of generating two names for it.
    "ENUM_NAME_OVERRIDES": {
        "RiskBandEnum": [
            ("LOW", "Low"),
            ("MEDIUM", "Medium"),
            ("HIGH", "High"),
        ]
    },
    "TITLE": "Mobility Finance API",
    "DESCRIPTION": (
        "Demo mobility finance and vehicle telematics backend. "
        "Register, log in, then paste the access token into Authorize. "
        "No real financial transactions are processed."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_AUTHENTICATION": [],
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {"deepLinking": True, "persistAuthorization": False},
}

SIMPLE_JWT = {
    # A new claim rejects pre-UUID access tokens and requires a fresh login.
    "USER_ID_CLAIM": "user_uuid",
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
}

# Payment providers. Paystack must use its TEST keys; the MoMo secret only
# authenticates the local simulator's callbacks.
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
MOCK_MOMO_WEBHOOK_SECRET = env("MOCK_MOMO_WEBHOOK_SECRET", default="momo-dev-secret")

# MQTT telemetry. The consumer is a separate process (manage.py run_mqtt_consumer);
# HTTP request handling never touches the broker.
MQTT_BROKER_HOST = env("MQTT_BROKER_HOST", default="127.0.0.1")
MQTT_BROKER_PORT = env.int("MQTT_BROKER_PORT", default=1883)
MQTT_USERNAME = env("MQTT_USERNAME", default="")
MQTT_PASSWORD = env("MQTT_PASSWORD", default="")
MQTT_KEEPALIVE_SECONDS = env.int("MQTT_KEEPALIVE_SECONDS", default=30)

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
# Compose (and later Render) override this to a writable, persisted path.
STATIC_ROOT = env("STATIC_ROOT", default=PROJECT_DIR / ".local" / "staticfiles")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
