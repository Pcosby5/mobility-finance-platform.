# Development decisions

## Step 1: local foundation

- Django and DRF form one modular backend. We will create apps only as their
  functionality arrives.
- PostgreSQL is required; no SQLite fallback hides database-specific behaviour.
- The custom user extends `AbstractUser` and is configured before the first
  migration. Django continues to own password hashing, users and permissions.
- Username is the initial login identifier. Email-login requirements should be
  decided before authentication endpoints and customer data are introduced.
- The role field describes platform responsibilities. `is_staff`, `is_superuser`
  and Django permissions govern admin-site access independently. A superuser
  created by Django is not automatically assigned the platform ADMIN role.
- Role choices are also a database check constraint. API authorization and
  prevention of client-assigned roles arrive with the authentication endpoints.
- DRF defaults to JWT-authenticated access. Liveness and the authentication entry
  points are public. Django admin retains its normal session authentication.
- Environment variables override the root `.env`. Secret key and database URL
  are required. Deployment configuration and hardening will be completed in the
  deployment phase; current settings are not a finished deployment recipe.

## Dependencies

Django provides models, migrations, authentication and admin. DRF provides the API
foundation. Psycopg connects to PostgreSQL. django-environ parses settings and the
database URL. Ruff formats and checks Python. Django's built-in test runner avoids
adding a second test framework. Requirements pin the installed dependency set;
updates should be deliberate and verified.

## Step 2: authentication

Registration, JWT login/refresh/logout and the current-user endpoint are implemented.
Simple JWT handles signing, token validation, rotation and database-backed
blacklisting. PyJWT is its token-encoding dependency. Public registration explicitly
creates a CUSTOMER and rejects privilege fields. Serializer creation uses Django's
user manager and password validators. A database uniqueness race returns a
validation error rather than exposing an integrity exception.

Five-minute access tokens bound the time an issued access token remains usable
after logout. Logout revokes one refresh token using possession of that token;
it works even after access expires. Rotation invalidates the previous refresh
token for subsequent requests; clients must not refresh concurrently. Immediate
access-token revocation and session-family tracking are not implemented.

User roles are read from the database rather than embedded as authoritative JWT
claims. The current-user endpoint exposes an explicit, read-only field list.
Inactive/deleted accounts cannot refresh. A small serializer override maps the
deleted-user lookup in Simple JWT 5.5 to an authentication error.

Basic per-IP throttling uses Django's local cache for development. Shared rate
limits, independent JWT signing-key management and token cleanup scheduling belong
in deployment hardening. Email verification and password recovery are not yet
implemented; email is contact information, while username is the login identity.

## UUID identifier convention

All application-owned domain models use server-generated UUIDv4 primary keys.
User IDs, API responses, schema formats and JWT user identifiers now follow this
convention. Django and third-party internal models retain their own primary keys;
their foreign keys to users are UUIDs. UUIDs provide opaque identifiers, while
authorization still requires permission and ownership checks.

The existing user table is converted by an atomic, forward-only PostgreSQL
migration. A temporary integer-to-UUID mapping updates all foreign keys and admin
log object references. The migration preserves existing accounts and relationships;
it invalidates old sessions and the new JWT claim requires a fresh login. A migration
test exercises an existing account with groups, permissions, admin logs and tokens.
Fresh-database migrations are also exercised by the test suite.

## Step 3: customer profiles

CustomerProfile has its own UUID and a unique, protected link to a customer User.
Create is explicit rather than a registration signal: profile inputs are supplied
after account creation. Customers act on their own profile; operations/admins can
manage all profiles. Queryset filtering prevents enumeration of other customers,
and an object permission reinforces ownership. User reassignment is prohibited.

Serializer validation covers phone format, nonnegative decimal amounts, employment
choices and immutable fields. Database constraints protect amounts, choices and
the one-profile-per-account invariant; a post-validation duplicate race returns a
validation error. No new dependencies were needed.

Financial values are self-reported demo inputs in a declared currency. Outstanding
debt and monthly debt payments are separate because only the latter can be compared
directly to monthly income for a debt-to-income ratio. Repayment history will be
derived from financial records later. Future credit assessments must snapshot the
inputs and rules version so subsequent profile edits do not change past decisions.

## Step 4: demo credit scoring

`credit/rules.py` holds a frozen, versioned policy; `credit/scoring.py` evaluates
plain inputs without database or provider dependencies. The service locks the
customer row briefly and saves the outcome, input snapshot and full rules snapshot
in one transaction. It does not mutate the customer profile. Each POST is a new
assessment; retries may create multiple assessment records, without financial effects.

Scoring uses dimensionless ratios to avoid comparing nominal amounts across
currencies. The debt-to-income input is monthly repayment, not total outstanding
debt. Thresholds use exact decimal comparisons, while display ratios are rounded.
Zero income has an explicit rejection path. Missing monthly debt payments trigger
review where the score alone would have approved. Missing repayment/transaction
history is disclosed and not scored. No new dependencies were added.

Saved results are read-only through the API. Ownership filters protect both
customer history and direct assessment retrieval. Tests cover cutoff boundaries,
zero income, high debt payments, missing history, reproducibility, unchanged old
snapshots after profile edits, permissions and database constraints.

## Step 5: vehicle and device inventory

Vehicle and Device use UUIDv4 primary keys. A vehicle optionally belongs to a
customer profile, and a device optionally belongs to one vehicle. Database unique
constraints protect registration, VIN, device identifier and one-device-per-vehicle
assignment. Serializer save transactions turn uniqueness races into validation
errors. Identifiers are normalized before uniqueness validation.

Operations/admins manage inventory. Customers have read-only access to assigned
vehicles and a small device summary; device management endpoints are restricted.
Queryset filtering and permissions protect list/detail access. Client-controlled
telemetry fields and unknown/read-only fields are rejected. No deletion API exists.

Vehicle lifecycle, connectivity and movement are distinct. Telemetry starts unknown
rather than implying a device is connected. Coordinates have paired-null and range
constraints. The immutable device identifier provides a future MQTT routing identity;
broker credentials and ingestion validation are not part of this milestone.

No new dependencies were needed. Tests cover UUID schemas, customer scope, management
permissions, assignment/detachment, uniqueness races, input/database validation and
read-only telemetry. When loans and telemetry arrive, enforce restrictions on
reassignment and preserve historical ownership before exposing their data.

## Step 6: loans and repayment schedules

A loan links a customer profile, an approved credit assessment and a vehicle; UUID
primary keys follow the project convention. Origination and lifecycle actions run
inside `transaction.atomic` and lock rows in a fixed order (customer → vehicle →
loan) so concurrent activations cannot double-spend affordability or assign one
vehicle to two open loans. A partial unique constraint allows only one open loan
per vehicle, and check constraints pin principal, rate, duration, currency and
the balance/status pairing to the database, not just the serializers.

`loans/calculations.py` is a pure module: flat simple interest, ROUND_HALF_UP,
with rounding residuals absorbed by the final installment so the schedule always
sums to the total repayable. Due dates clamp to month ends. `loans/policy.py`
holds the versioned demo limits (assessment age, combined debt-to-income,
repayment window, rate and duration caps) so no magic numbers reach the services.

Eligibility rechecks the profile against the assessment's saved input snapshot at
creation *and* again at activation, so a loan cannot be activated on stale
financials. Affordability counts existing open loans' monthly repayments against
the reported income in the customer's currency; currency mismatches require
review. Installments are bulk-created from the calculation and exposed read-only
via `/api/v1/loans/{id}/installments/`.

Vehicle reassignment, VIN changes and retirement are blocked while an open loan
references the vehicle; the vehicle update path takes the same row lock as loan
origination so the guard cannot race. Deletion does not exist; PROTECT foreign
keys preserve financial history.

No new dependencies were needed. Tests cover interest and rounding boundaries,
month-end clamping, eligibility and affordability rejections, assessment staleness
and snapshot drift, activation rechecks, cancel semantics, per-vehicle and
financial database constraints, ownership scoping and management permissions.

## Step 7: payments, webhooks and idempotency

Payments go through a small provider interface (`create_payment`,
`verify_payment`, `verify_webhook_signature`). `PaystackProvider` talks to the
Paystack REST API in TEST mode over `requests` (the only new dependency);
`MockMomoProvider` is a local simulator with no network calls. Neither leaks
into services or views: `get_provider(name)` is the only factory, and adding a
future provider touches only `providers.py`.

`Payment` rows are an append-only ledger: initialization creates PENDING, and
only verified provider outcomes can move them to a terminal state. Webhook
payloads point at a transaction but are never trusted for the outcome - the
handler re-verifies with the provider before any money moves. Settlement runs
in one transaction under a loan row lock, and terminal transitions use
conditional updates (`WHERE status = 'PENDING'`) so concurrent redeliveries
have a single winner; a duplicate observes "already processed" and is audited
in `WebhookEvent` without any financial side effect. Amount and currency are
cross-checked against the provider's verified record before a balance moves.

A full-balance settlement completes the loan; a partial one reduces the
outstanding balance. Failed payments are recorded with a reason and leave
balances untouched. Amount mismatches become FAILED payments rather than
silent partial credits.

The MoMo simulator resolves charges through a staff-session-only endpoint that
signs and forwards a callback through the normal webhook pipeline, so the code
under test is the production path. JWT credentials are deliberately not
accepted there, so a leaked access token cannot resolve simulated charges.
Paystack webhook tests cover signature rejection, unknown references and
duplicate delivery; MoMo tests cover success, failure and duplicate callbacks.

## Step 8: MQTT telemetry pipeline

Telemetry is transported by MQTT (paho-mqtt 2.1.0, the only new dependency) and
processed by a dedicated consumer process: ``python manage.py
run_mqtt_consumer``. HTTP workers never touch the broker, so a broker outage
cannot affect API latency and a web redeploy cannot drop the subscription.
Topics follow ``vehicles/{vehicle_id}/telemetry`` with QoS 1; the consumer
subscribes with a wildcard and reconnects with bounded backoff.

``telemetry/services.py`` is transport-agnostic: ``process_message(topic,
body)`` never raises for malformed content (it returns a status for the adapter
to log), while ``ingest_telemetry`` performs resolution and persistence. A
future AWS IoT Core rule or REST ingestion endpoint can call the same service.

Idempotency is enforced by the database, not the transport: a unique
(device_id, recorded_at) constraint collapses QoS 1 redeliveries and consumer
restarts into one stored record. Payloads are validated in one place — ranges,
clock skew, types — and the payload's ``vehicle_id`` is never trusted for
resolution; the registered Device mapping is authoritative, so a misconfigured
device cannot write into another vehicle's history. Topic/device mismatches are
logged for operations.

Vehicle denormalized state (last position, ONLINE, MOVING/PARKED at 1 km/h
threshold) updates in the same transaction as the record insert, under a
vehicle row lock. History is exposed read-only at
``/api/v1/vehicles/{id}/telemetry/`` with pagination, ``start``/``end`` ISO
range filters and ``ordering``; customers are scoped to their vehicles and
invalid filters fail loudly rather than returning unfiltered data.

The GPS simulator is a standalone script (``gps-simulator/simulator.py``, own
requirements) that random-walks a virtual vehicle and publishes spec-shaped
payloads; it holds no database access, keeping the backend the only writer.
Local broker configuration lives in ``mosquitto/mosquitto.conf`` (loopback,
unauthenticated, demo only).

No payment or loan behaviour changed. Tests cover payload parsing boundaries,
idempotent ingestion, device resolution failures, ``process_message`` error
policies and API scoping/filtering.

## Step 9: geofencing and alerts

A vehicle may carry a simple radius-based geofence: nullable center plus radius
in meters, written and cleared as one unit (serializer rule plus an
all-or-nothing database constraint, radius bounds in ``vehicles/policy.py``).
Distance uses the haversine formula in ``telemetry/geo.py`` — over the hundreds
of meters a geofence cares about, the spherical-earth error is far smaller than
the demo's radius slack, so PostGIS is not justified yet.

``Alert`` lives in the telemetry app beside its raise/clear rules and covers
GEOFENCE_EXIT, SPEEDING, LOW_BATTERY and OFFLINE. One open alert per (vehicle,
type) is enforced by a partial unique constraint; ``raise_or_refresh``
creates-or-refreshes inside that guarantee, so concurrent ingest workers cannot
stack duplicate incidents. Condition alerts auto-clear during ingestion when
the condition no longer holds (a returning vehicle, a slowing vehicle, a
charged battery, a vehicle that reports again); humans resolve via the API,
which records the actor — auto-resolve has no actor, so actor presence is an
API rule, not a database constraint.

Evaluation runs inside the ingest transaction, so telemetry, vehicle state and
alerts commit or roll back together. OFFLINE detection intentionally does not:
it is time-based, not message-based, and runs in the
``check_offline_vehicles`` command (cron or container sidecar; Celery beat in
production) over vehicles with an assigned, enabled device and at least one
record — a vehicle that has never reported is untracked, not offline.

Alerts are exposed read-only at ``/api/v1/alerts/`` with vehicle, type and
resolved filters, plus ``POST /api/v1/alerts/{id}/resolve/`` for
operations/admin. Customers are scoped to their own vehicles. Tests cover
haversine distances, the full alert lifecycle, offline refresh semantics,
geofence serializer/coordinate rules and API scoping.

## Step 10: Docker and Compose

The backend image (``backend/Dockerfile``) is production-parity: code is baked
into a slim, non-root image rather than bind-mounted, so what runs locally is
what ships to Render. One image serves both the web role (``migrate`` +
``collectstatic`` + gunicorn) and the consumer role (``run_mqtt_consumer``);
commands come from Compose/Render, keeping the artifact single. The GPS
simulator is a separate tiny image because a device only needs paho-mqtt and a
broker address.

``docker-compose.yml`` brings up PostgreSQL 16, Mosquitto, web, consumer and an
optional ``--profile demo`` simulator. Shared environment comes from a YAML
anchor so web and consumer never drift. The Postgres host port is 5433 to
coexist with a native installation; the container path is always ``db:5432``.
Static files are served by whitenoise (new dependency) because DEBUG=False
disables Django's static serving and the demo containers run gunicorn without
a separate static server; ``STATIC_ROOT`` is environment-overridable.

Docker is unavailable in the current WSL session, so compose files were
validated structurally (YAML parse, anchor/merge, env keys) and the full local
suite still passes; the image build and end-to-end compose run are part of the
user's local verification. Mosquitto's container config uses a 0.0.0.0
listener (loopback-only is unusable between containers) and has no healthcheck
because the image ships no client binaries - the consumer's reconnect handles
broker startup races.

## Step 11: CI and Render deployment

GitHub Actions (``.github/workflows/ci.yml``) runs the same gates as local
verification on every push and pull request: ruff lint/format, Django system
checks, ``makemigrations --check`` (blocks uncommitted model changes), OpenAPI
validation with ``--fail-on-warn``, and the full suite in parallel against a
PostgreSQL 16 service container — the same engine as development and
production, so partial unique constraints, CHECK constraints and
``SELECT ... FOR UPDATE`` behave in CI exactly as locally.

Render is configured as a Blueprint (``render.yaml``) plus ``build.sh``: a free
PostgreSQL instance, a web service (``build.sh`` = install + migrate +
collectstatic, then gunicorn bound to ``$PORT``) and a worker running the MQTT
consumer. Builds fail loudly via ``set -euo pipefail``, so a broken release
never replaces a working one. Secrets are dashboard-only: the Blueprint
declares ``sync: false`` for Paystack keys and ``generateValue`` for runtime
secrets; nothing sensitive lives in the repository.

Deployment decisions worth explaining: the web build owns migrations because
concurrent web/worker deploys must not race DDL — the worker's build only
installs dependencies. ``SECURE_PROXY_SSL_HEADER`` trusts Render's edge proxy
for the forwarded protocol, which is what makes ``SECURE_SSL_REDIRECT`` safe
behind TLS termination; local traffic carries no such header, so behaviour is
unchanged. The free-tier worker expects ``MQTT_BROKER_HOST`` from the
dashboard (a public test broker for the demo; AWS IoT Core is the documented
production evolution) because Render does not run brokers.

## Step 12: portfolio README

The README was restructured from a running dev log into a portfolio front page:
project overview, architecture diagram (payments and MQTT paths), technology
stack with rationale, features, local and Docker setup, environment variables,
the full API surface by module, payment and webhook flow explanations (signature
verification, re-verification, the three idempotency layers), MQTT architecture
(transport-agnostic ingest, DB-level dedupe), the GPS simulator, credit-scoring
architecture, Render deployment, testing, production evolution (queue-backed
webhook settlement, AWS IoT Core, time-series history), limitations and future
improvements. The honesty statement — Paystack TEST mode, simulated MoMo,
demonstration credit engine, local broker — sits at the top where a reviewer
sees it first. Per-milestone reasoning stays in this document; the README links
here as the decision log.

## Remaining phases

1. ~~Loans and repayment schedules using saved credit assessments and vehicles.~~
3. ~~Test payments, provider abstraction, verified/idempotent webhooks and Mock MoMo.~~
4. ~~Mosquitto, a separate MQTT consumer and GPS simulator.~~
5. ~~Telemetry history, geofences, alerts and retention.~~
6. ~~Docker and Compose.~~
7. ~~Consolidated tests and GitHub Actions CI.~~
8. ~~Render deployment.~~
9. ~~Portfolio demonstration, README and production evolution documentation.~~

All planned phases are complete. Tests and documentation accompany every
milestone. No paid cloud resources are needed for the local implementation.
