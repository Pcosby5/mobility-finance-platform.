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
documentation, versioned demo credit assessments, and vehicle/device inventory.
Loans, payments and MQTT/telemetry ingestion are still planned.

```text
backend/
  manage.py
  config/       # Settings, routing, ASGI/WSGI, liveness
  users/        # Custom user, admin, migrations, tests
  customers/    # UUID customer profiles, permissions, validation, tests
  credit/       # Versioned rules, scoring, saved assessments, tests
  vehicles/     # Vehicle/device inventory, assignment, permissions, tests
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

## Demo credit assessments

In Swagger's **Credit** section, use your customer **profile UUID** and execute
`POST /api/v1/customers/{customer_id}/credit-assessments/` with `{}`. Inputs come
from the saved profile; callers cannot submit a score or override financial inputs.
Each request creates a new assessment with a UUID, score, risk band, decision,
factors, ratios, and input/rules snapshots. There are no real lending decisions.

- `GET /api/v1/customers/{customer_id}/credit-assessments/` lists paginated history.
- `GET /api/v1/credit-assessments/{id}/` retrieves a saved assessment.
- Customers can assess/read only their own profile. ADMIN and OPERATIONS can
  assess/read all profiles. Results have no update or delete API.

The `demo-v1` policy in `backend/credit/rules.py` starts at 300 points:

| Factor | Points |
| --- | --- |
| Positive monthly income | +100 |
| Monthly debt payments / income | ≤20%: +200; ≤40%: +125; ≤60%: +50; above: +0 |
| Outstanding debt / monthly income | ≤1: +100; ≤3: +50; above: +0 |
| Employed or self-employed | +75 |
| Current employment duration | ≥24 months: +75; ≥6 months: +40; otherwise +0 |

Score bands: **700–850 LOW / APPROVED**, **550–699 MEDIUM / REVIEW**,
**300–549 HIGH / REJECTED**, subject to these decision overrides:

- Zero income yields 300/HIGH/REJECTED, with unavailable ratios rather than division by zero.
- Monthly debt payments above 60% of income force HIGH/REJECTED regardless of score.
- Outstanding debt with no reported monthly payment prevents automatic demo approval
  and adds a review explanation. Its score-based risk band is retained.

Employment duration contributes only for current employment/self-employment.
Ratios are compared before rounding and displayed to four decimal places. All
amounts use the profile currency; no exchange-rate conversion or currency-specific
income threshold is used. Repayment and transaction histories are explicitly
unavailable, contribute no points and are not invented.

The sample profile earns `300 + 100 + 200 + 100 + 75 + 75 = 850`.
This is an illustrative points model, not a calibrated credit score. It does not
consider a proposed loan payment, living expenses, verified income or credit-bureau
data. APPROVED does not activate a loan. Save a new version whenever rules change;
existing assessments retain their recorded rules and inputs.

To test snapshot behaviour, assess your profile, PATCH its monthly income to `0`,
then assess again. The new assessment should be rejected while the first stays
unchanged. Restore the profile's demo inputs afterwards if desired.

## Vehicles and devices

Swagger now includes **Vehicles** and **Devices**. Both use UUID primary keys.

| Method | Endpoint | Access |
| --- | --- | --- |
| GET | `/api/v1/vehicles/` | Customers: assigned vehicles; operations/admin: all |
| POST | `/api/v1/vehicles/` | Operations/admin only |
| GET | `/api/v1/vehicles/{id}/` | Assigned customer or operations/admin |
| PATCH | `/api/v1/vehicles/{id}/` | Operations/admin only |
| GET, POST | `/api/v1/devices/` | Operations/admin only |
| GET, PATCH | `/api/v1/devices/{id}/` | Operations/admin only |

Use a separate operations account to test creation. Log in to Django admin with
a superuser, add a user and set its **Platform → Role** to **Operations**. Keep
`demo_customer` as CUSTOMER. An operations API account does not need `is_staff`.
Then log in to Swagger with the operations account and replace its Authorize token.

Create a vehicle, setting `customer` to the **customer profile UUID**, not the
user account UUID. Omit it for an unassigned vehicle:

```json
{
  "registration_number": "DEMO-001",
  "vin": "1HGCM82633A004352",
  "make": "Honda",
  "model_name": "Accord",
  "year": 2003,
  "status": "ACTIVE"
}
```

PATCH `{"customer":"YOUR_CUSTOMER_PROFILE_UUID"}` to assign a vehicle, or
`{"customer":null}` to unassign it. Create a device with a unique, stable label:

```json
{
  "device_id": "GPS-001",
  "enabled": true
}
```

PATCH the device with `{"vehicle":"YOUR_VEHICLE_UUID"}` to link it. Each vehicle
can have one device; multiple unassigned devices are allowed. Detach a device with
`{"vehicle":null}` before replacing it. `{"enabled":false}` marks it disabled but
does not detach it. `device_id` is immutable and is a case-sensitive routing label,
not an authentication credential. MQTT will enforce enabled state in a later phase.

Switch Swagger authorization back to the customer account: it should see only
assigned vehicles, including a read-only device summary. Vehicle writes and device
management return 403; another customer's vehicle returns 404. Reassignment removes
the previous customer's access. Delete and PUT are not exposed.

Registration and VIN are trimmed, uppercased and unique. VIN validation checks
format (17 characters, excluding I/O/Q), not manufacturer records or ownership.
Supported model years are 1900 through next year.

Vehicle `status` describes lifecycle: ACTIVE, MAINTENANCE or RETIRED. Connectivity
(UNKNOWN/ONLINE/OFFLINE) and movement (UNKNOWN/MOVING/PARKED) are separate read-only
fields. Both start UNKNOWN, with null GPS coordinates and telemetry timestamp.
No simulator or MQTT consumer runs yet. Later telemetry ingestion will update these
fields; REST clients cannot forge them through inventory endpoints.

This milestone permits operations/admin reassignment. Loan-linked reassignment
rules and historical telemetry ownership will be addressed when those modules arrive.

See [development decisions](docs/development.md) for architecture and next steps.
