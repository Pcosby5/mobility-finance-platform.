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
migration, registration, JWT login/refresh/logout, a current-user API and
authentication tests, customer profiles with ownership permissions, and Swagger/OpenAPI
documentation. Credit, loans, payments and IoT features are still planned.

```text
backend/
  manage.py
  config/       # Settings, routing, ASGI/WSGI, liveness
  users/        # Custom user, admin, migrations, tests
  customers/    # UUID customer profiles, permissions, validation, tests
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
admin access, public liveness, registration validation, privilege escalation,
token expiry/rotation/revocation, inactive/deleted users and request throttling.
Test requests use HTTPS to work with the secure settings defaults.

## Authentication API

### Test in Swagger

Start the local server from `backend/` with `DEBUG=True python manage.py runserver`.
Open **http://127.0.0.1:8000/api/docs/**. The OpenAPI schema is at `/api/schema/`.

1. Expand `POST /api/v1/auth/register/`, click **Try it out**, enter a demo user,
   then **Execute**. A successful registration returns 201.
2. Execute `POST /api/v1/auth/login/` with that username and password.
3. Copy the returned **access** token. Click **Authorize** at the top and paste
   only the token, without `Bearer`. Swagger adds that prefix automatically.
4. Execute `GET /api/v1/auth/me/` to see your profile.
5. Test `refresh/` by submitting the refresh token in the JSON body. Save the new
   pair and update **Authorize** with the new access token.
6. Test `logout/` with the latest refresh token. Reusing it at `refresh/` should
   return 401. Use Swagger's **Authorize → Logout** to clear the UI's access token.

Swagger does not automatically log you in or replace its token after a refresh.
Its Authorize dialog's Logout button only clears the token from the UI; the API
logout endpoint revokes the refresh token on the server. Access tokens expire in
five minutes. Reloading the page clears Swagger authorization.

Swagger UI assets are served locally through `drf-spectacular-sidecar`; no CDN
connection is required. Docs are public for the demo; protected API routes still
require JWT. `drf-spectacular` generates the schema from the DRF endpoints.

Validate the schema from `backend/`:

```bash
python manage.py spectacular --validate --fail-on-warn --file /tmp/mobility-openapi.yaml
```

### Endpoint reference

Application models use UUIDv4 primary keys. Registration and `/me/` return `id`
as a UUID string, and Swagger describes it as `type: string, format: uuid`.
JWTs identify the user with the `user_uuid` claim. UUIDs do not replace ownership
checks or permissions.

Upgrading from the initial integer-ID foundation runs migration `users.0002_user_uuid`.
It preserves accounts, password hashes and related records, and clears old Django
sessions. Existing JWTs require a fresh login. This PostgreSQL data migration is
atomic and forward-only; take a database backup before applying it. It locks the
user table and referencing tables during conversion, so run it during a maintenance
window if the database is in use.

All routes below are under `/api/v1/auth/`. Login uses a username; email is contact
information and is not verified or unique in this milestone.

| Method | Route | Request / result |
| --- | --- | --- |
| POST | `register/` | Username, email, password; optional first/last name. Creates a CUSTOMER (201). |
| POST | `login/` | Username and password; returns `access` and `refresh` (200). |
| POST | `refresh/` | `refresh`; returns a new access/refresh pair (200). |
| POST | `logout/` | `refresh`; revokes that refresh token and returns `{}` (200). |
| GET | `me/` | Bearer access token; returns the current user's profile (200). |

For example, with the local server running, register a demo account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_customer","email":"demo@example.com","password":"Demo-only!CorrectHorse7492"}'
```

Log in with the same username and password:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_customer","password":"Demo-only!CorrectHorse7492"}'
```

Use the returned access token to fetch your profile:

```bash
curl http://127.0.0.1:8000/api/v1/auth/me/ \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

Send `{"refresh":"YOUR_REFRESH_TOKEN"}` as JSON to `refresh/` or `logout/`.
Those endpoints use possession of the refresh token and do not require a live
access token. After refreshing, replace both stored tokens. Invalid, expired or
blacklisted tokens return 401; missing fields return 400. Logging out twice with
the same token returns 401 on the second request.

Access tokens last five minutes; refresh tokens last one day and rotate on use.
Logout revokes the supplied refresh token only. Previously issued access tokens
remain usable until expiry; clients should discard both tokens on logout. Other
login sessions remain active. Deactivated accounts are rejected on access and
refresh. Password changes do not revoke existing tokens in this milestone.

Registration rejects role/staff fields and applies Django's password validators.
API authentication uses JWT; Django admin continues to use session authentication.
Auth POST routes share a basic per-IP limit of 20 requests/minute. The current
in-memory cache makes this a per-process development limit, not distributed
brute-force protection. Clients should serialize refresh requests: concurrent
rotation is not guaranteed to be single-use by the library's blacklist workflow.

Periodically remove expired token records (from `backend/`):

```bash
python manage.py flushexpiredtokens
```

Schedule this daily when deploying. Rotation and revocation use Simple JWT's
[documented blacklist app](https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html).

## Customer profiles

Log in and authorize in Swagger, then open the **Customers** section.

| Method | Endpoint | Behaviour |
| --- | --- | --- |
| GET | `/api/v1/customers/` | Paginated profiles visible to your account |
| POST | `/api/v1/customers/` | Create one profile per customer account |
| GET | `/api/v1/customers/{id}/` | Read a profile by its UUID |
| PATCH | `/api/v1/customers/{id}/` | Update selected fields; ownership is immutable |

While logged in as `demo_customer`, execute POST with the Swagger example:

```json
{
  "full_name": "Demo Customer",
  "phone": "+233201234567",
  "employment_status": "EMPLOYED",
  "employment_duration_months": 24,
  "currency": "GHS",
  "monthly_income": "6500.00",
  "existing_debt": "2000.00",
  "monthly_debt_repayment": "250.00"
}
```

The response returns a new **profile UUID** in `id` and your **account UUID** in
`user`. Use the profile UUID for customer detail routes. These are different IDs.
For PATCH, send only fields to change, for example `{"monthly_income":"7000.00"}`.

- CUSTOMER accounts create, list, read and update only their own profile. Omit
  `user` when creating your own profile. Access to another profile returns 404.
- ADMIN and OPERATIONS roles can list, read and update all profiles. On creation
  they must supply `user` with an existing active CUSTOMER account UUID.
- A second profile for the same account returns 400. Unknown/read-only fields are
  rejected, and profile ownership cannot be changed. Delete and PUT are not exposed.
- Email comes from the user account and is read-only here. `full_name` is the
  customer's declared profile name; it does not change the account's name fields.
- Amounts are decimal strings in the selected currency (GHS, NGN or USD). These
  are self-reported demo inputs, not verified financial data. No currency conversion
  is performed. If changing the currency, resubmit amounts in the new currency.
- `existing_debt` is a total outstanding balance. `monthly_debt_repayment` is a
  monthly obligation; it is the relevant input for future debt-to-income calculations.
  Zero income is accepted and must be handled explicitly by the future scoring engine.
- Repayment history will come from loan/payment records; customers cannot submit it
  through this profile endpoint.

Platform roles are separate from Django staff access. A Django superuser with role
CUSTOMER has customer-level API scope; assign the platform role ADMIN or OPERATIONS
through the existing user admin when testing those workflows.

See [development decisions](docs/development.md) for architecture and next steps.
