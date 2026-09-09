# Mobility Finance & Vehicle Telematics Platform

A Django backend portfolio project connecting demo credit decisions, vehicle
finance, test payments, and simulated GPS telemetry. We are building and verifying
the backend incrementally, locally first.

Paystack will use test mode only. MTN MoMo will be simulated. Credit scoring will
be a demonstration rules engine. No real financial transactions are processed.
MQTT will initially use local Mosquitto; AWS IoT Core is a future architecture
discussion, not an implemented integration.

## Current milestone

Implemented: Django project, PostgreSQL configuration, custom user with customer,
operations and admin roles, Django admin, a public liveness endpoint, initial
migration, and foundation tests. Registration, JWT, customer APIs, payments, and
IoT features are still planned.

```text
backend/
  manage.py
  config/       # Settings, routing, ASGI/WSGI, liveness
  users/        # Custom user, admin, migrations, tests
requirements/   # Pinned runtime and development dependencies
docs/           # Decisions and development milestones
```

## Local setup

Requires Python 3.12+ and PostgreSQL 16. Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/dev.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Set `DJANGO_SECRET_KEY` in `.env` to the generated value. Set `DATABASE_URL` to
your local PostgreSQL connection. `.env` is ignored by Git; `.env.example` contains
only placeholders. Skip copying `.env` if your local configuration already exists.

For an existing PostgreSQL installation, create a dedicated development role and
database, and grant that role `CREATEDB` for Django's temporary test database.
Use PostgreSQL for tests as well as development.

The project uses an existing PostgreSQL server with a dedicated
`mobility_finance` database. DBeaver is a database client: use its working host,
port and credentials to configure Django. In DBeaver's SQL editor, create the
database once if it does not already exist:

```sql
CREATE DATABASE mobility_finance;
```

Set `DATABASE_URL` using the role that owns the database:

```dotenv
DATABASE_URL=postgresql://YOUR_USER:YOUR_ENCODED_PASSWORD@YOUR_HOST:5432/mobility_finance
```

URL-encode special characters in the password, such as `@` as `%40`. DBeaver's
separate password field uses the original password. If Django runs in WSL and
PostgreSQL runs elsewhere, use an address reachable from WSL. The example host
and port must be replaced with your actual connection settings.

An earlier setup used a separate cluster under `.local/postgres/` on port 5433.
That cluster is not required when connecting to an existing server. Local data
and logs are ignored by Git.

Start the API from `backend/`:

```bash
cd backend
python manage.py migrate
python manage.py createsuperuser
DEBUG=True python manage.py runserver 127.0.0.1:8000
```

Open `http://127.0.0.1:8000/api/health/` for `{"status": "ok"}` or `/admin/`
for Django admin. Liveness checks the HTTP application, not database readiness.
The `createsuperuser` command is optional; no default admin credentials are seeded.

Existing shell environment variables override `.env`. `DEBUG` defaults to false,
which enables HTTPS redirects and secure cookies. The explicit `DEBUG=True` above
allows local HTTP even when the shell already defines `DEBUG=False`.

## Verification

With the virtual environment activated, run Django checks **from `backend/`** so
the default test discovery finds the apps:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 2
```

Run linting from the repository root:

```bash
ruff check backend
ruff format --check backend
python -m pip check
```

Tests cover customer defaults, password hashing, the database role constraint,
operations users being denied admin access, and public liveness. Test requests use
HTTPS to work with the secure settings defaults.

See [development decisions](docs/development.md) for architecture and next steps.
