# Mobility Finance & Vehicle Telematics Platform

A production-shaped Django backend that connects **credit decisions → vehicle
finance → payments → live GPS telemetry** in one modular monolith. Built as a
portfolio demonstration of senior backend + FinTech + IoT engineering:
JWT authentication, a versioned rules-based credit engine, a
provider-abstracted payment layer with idempotent webhooks, an MQTT telemetry
pipeline with a separate consumer process, geofencing and alerting — Dockerized,
CI-checked, and deployable to Render from a Blueprint.

> **Scope and honesty statement**
> - **Paystack is TEST mode only** (`sk_test_` / `pk_test_` keys). No real money moves.
> - **MTN MoMo is a local simulator**, not a real MTN integration.
> - **Credit scoring is a demonstration rules engine**, not a calibrated or regulated model.
> - **MQTT runs on a local Mosquitto broker** for this version; AWS IoT Core is the
>   documented production evolution, not an implemented integration.
> - **No real financial transactions are processed anywhere in this project.**

---

## Contents

1. [Why this project exists](#why-this-project-exists)
2. [Architecture](#architecture)
3. [Technology stack](#technology-stack)
4. [Features](#features)
5. [Local setup](#local-setup)
6. [Docker setup](#docker-setup)
7. [Environment variables](#environment-variables)
8. [API documentation](#api-documentation)
9. [Payment flow](#payment-flow)
10. [Webhook architecture](#webhook-architecture)
11. [MQTT architecture](#mqtt-architecture)
12. [GPS simulator](#gps-simulator)
13. [Credit scoring architecture](#credit-scoring-architecture)
14. [Render deployment](#render-deployment)
15. [Testing](#testing)
16. [Production architecture](#production-architecture)
17. [Limitations](#limitations)
18. [Future improvements](#future-improvements)

Engineering decisions and milestone history live in
[docs/development.md](docs/development.md).

---

## Why this project exists

Asset-financing businesses lend against vehicles and need to watch the asset.
That single sentence spans four disciplines: underwriting (credit scoring),
originations (loans), collections (payments and webhooks), and risk monitoring
(telematics, geofences, alerts). Most tutorials cover one of these in
isolation; this project integrates all of them behind one coherent REST API,
with the correctness details that matter in finance — database constraints,
row locking, idempotent settlement, audit trails — rather than the happy-path
version.

---

## Architecture

A **modular Django monolith**: one deployable backend, one database, apps
split by responsibility. No microservices — service boundaries exist in the
code (provider interfaces, transport-agnostic ingest, pure calculation
modules) so individual pieces can be extracted later if they ever need to.

```text
                    ┌──────────────────────────────────────────────┐
 GPS device /       │              Mosquitto broker                │
 simulator          │   vehicles/{vehicle_id}/telemetry  (QoS 1)   │
───────────────────▶└───────────────────────┬──────────────────────┘
                                            │ wildcard subscribe
                                            ▼
                            ┌────────────────────────────────────┐
                            │ run_mqtt_consumer (own process)    │
                            │ validate → resolve device →        │
                            │ persist + vehicle state + alerts   │
                            └────────────────┬───────────────────┘
                                             │
┌────────┐   REST / JWT   ┌──────────────────▼───────────────────┐
│ Client ├───────────────▶│ Django + DRF under gunicorn          │
│(Swagger)│◀──────────────┤ users · customers · credit · loans   │
└────────┘                │ payments · vehicles · telemetry      │
      │                                   │                      │
      │ POST /api/v1/webhooks/paystack/   │                      │
      │ (HMAC-SHA512 verified)            ▼                      ▼
      │                  ┌─────────────────────────┐   ┌────────────────┐
      └─────────────────▶│ webhook handler          │   │ PostgreSQL 16  │
                         │ re-verify w/ provider    ├──▶│ (source of     │
                         │ idempotent settlement    │   │  truth)        │
                         └────────────┬─────────────┘   └────────────────┘
                                      │ REST (TEST mode only)
                                      ▼
                         ┌─────────────────────────┐
                         │ Paystack TEST API  /    │
                         │ Mock MoMo simulator     │
                         └─────────────────────────┘
```

```text
backend/
  config/       Settings, routing, ASGI/WSGI, health, OpenAPI
  users/        Custom user, roles (ADMIN/CUSTOMER/OPERATIONS), JWT auth
  customers/    Customer profiles (self-reported financials)
  credit/       Versioned rules engine + saved, snapshot assessment records
  loans/        Origination, schedules, activation, balances, guards
  payments/     Provider abstraction, ledger, webhooks, idempotency, audit
  vehicles/     Vehicle + device inventory, geofence fields
  telemetry/    MQTT consumer, ingest pipeline, telemetry history,
                geofence + alert evaluation, offline detection
gps-simulator/  Standalone MQTT publisher (own Dockerfile, no DB access)
mosquitto/      Local + container broker configs
requirements/   Pinned runtime and dev dependencies
docs/           Development decisions, milestone by milestone
```

---

## Technology stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.12+ | |
| Framework | Django 5.2 + Django REST Framework | Batteries-included ORM, migrations, admin, and the framework I know best — business logic stays plain Python, testable without HTTP |
| Database | PostgreSQL 16 | Partial unique constraints, CHECK constraints and `SELECT ... FOR UPDATE` are load-bearing here (idempotency, one-open-loan-per-vehicle, settlement) — SQLite would fake them |
| Auth | Simple JWT (rotation + blacklist) | Short-lived access tokens, refresh rotation, server-side revocation |
| Payments | Paystack REST (TEST) via `requests` | Thin provider class; no vendor SDK lock-in |
| Messaging | paho-mqtt 2.1 over Mosquitto | Standard IoT transport; consumer is a separate process |
| API docs | drf-spectacular + sidecar | Schema generated from serializers, validated in CI |
| Serving | gunicorn + whitenoise | Production WSGI; static without a second server |
| Infra | Docker Compose, GitHub Actions, Render | One command locally; push-to-deploy in the cloud |

Every dependency is pinned in `requirements/base.txt`.

---

## Features

**Identity & access** — registration, JWT login/refresh/logout with rotation and
blacklisting, three platform roles (ADMIN / CUSTOMER / OPERATIONS), per-IP
throttling on auth routes, object-level permissions and queryset scoping on
every customer-owned resource.

**Customer profiles** — self-reported demo financials (income, existing debt,
monthly debt obligations, employment), one profile per account, immutable
ownership, UUID public identifiers.

**Credit scoring** — versioned rules engine producing score, risk band, decision
and human-readable factors, with full input + rules snapshots saved per
assessment so past decisions never change when inputs or rules change.

**Loans** — origination against an approved credit assessment and a vehicle,
flat simple-interest schedules with exact decimal rounding, activation with
re-checked eligibility, DB-enforced one-open-loan-per-vehicle, balance/status
pairing constraints, and vehicle guards (no reassignment/VIN change/retirement
while an open loan exists).

**Payments** — provider-agnostic initialization and verification, append-only
payment ledger, signature-verified Paystack webhooks, idempotent settlement,
webhook audit trail, and a mock MoMo simulator that exercises the real pipeline.

**Vehicles & devices** — inventory with unique registration/VIN, one-device-per-
vehicle assignment, connectivity and movement state derived only from telemetry.

**Telemetry** — MQTT ingestion through a dedicated consumer, idempotent storage,
read-only history API with time-range filtering, denormalized vehicle state.

**Geofencing & alerts** — radius-based geofences on vehicles, geofence-exit /
speeding / low-battery alerts evaluated inside the ingest transaction with
auto-resolve, time-based offline detection, manual resolution API.

**Platform** — OpenAPI schema generated and validated, health endpoint,
Dockerized full stack, CI on every push, one-file Render Blueprint.

---

## Local setup

Requires Python 3.12+ and a PostgreSQL 16 server. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/dev.txt
cp .env.example .env
python -c 'import secrets; print(secrets.token_urlsafe(64))'   # → DJANGO_SECRET_KEY
```

Set `DJANGO_SECRET_KEY` and `DATABASE_URL` in `.env`
(e.g. `postgresql://user:password@127.0.0.1:5432/mobility_finance` — URL-encode
special characters in the password). Grant the role `CREATEDB` so tests can
create a temporary database; tests run against PostgreSQL, not SQLite.

Then from `backend/`:

```bash
python manage.py migrate
python manage.py createsuperuser          # optional; no seeded credentials
DEBUG=True python manage.py runserver 127.0.0.1:8000
```

Check `http://127.0.0.1:8000/api/health/` → `{"status": "ok"}`, then open
Swagger. Notes: shell environment variables override `.env`; `DEBUG` defaults
to false (secure cookies + HTTPS redirects), hence the explicit `DEBUG=True`
for local HTTP.

---

## Docker setup

Prefer the native setup above? It still works — Compose is optional. From the
repository root:

```bash
cp .env.example .env            # then set DJANGO_SECRET_KEY (required)
docker compose up --build       # add --profile demo to include the simulator
```

| Service | Address | Notes |
| --- | --- | --- |
| API / Swagger | http://localhost:8000/api/docs/ | `migrate` + `collectstatic` run automatically |
| Health | http://localhost:8000/api/health/ | container healthcheck target |
| Mosquitto | localhost:1883 | anonymous, demo only |
| PostgreSQL | localhost:5433 | host port 5433 avoids clashing with a native install; containers use `db:5432` |

One backend image serves two roles: the web service runs
`migrate → collectstatic → gunicorn`, the `consumer` service runs
`python manage.py run_mqtt_consumer`. Environment comes from the root `.env`
(via a shared Compose anchor so web and consumer cannot drift); secrets are
never baked into images. The consumer reconnects with bounded backoff, so
broker startup order needs no orchestration.

Drive a vehicle through the stack:

```bash
docker compose --profile demo up --build
docker compose logs -f consumer      # watch telemetry being stored
```

Reset with `docker compose down` (`-v` also removes data).

---

## Environment variables

`.env.example` documents every variable with placeholders only; `.env` is
git-ignored and never committed.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required. Django signing key. |
| `DEBUG` | Defaults to false. Set `DEBUG=True` for local HTTP. |
| `ALLOWED_HOSTS` | Comma-separated hosts (production sets this in Render). |
| `DATABASE_URL` | PostgreSQL connection string. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Compose database seeding only. |
| `PAYSTACK_SECRET_KEY` | **TEST** secret key (`sk_test_…`). |
| `PAYSTACK_PUBLIC_KEY` | **TEST** public key (`pk_test_…`). |
| `MOCK_MOMO_WEBHOOK_SECRET` | Signs the local MoMo simulator's callbacks. |
| `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` | Mosquitto address for consumer and simulator. |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | Optional broker credentials. |

---

## API documentation

Interactive Swagger UI: **`/api/docs/`** — generated schema: `/api/schema/`
(validate with `python manage.py spectacular --validate --fail-on-warn`).
Swagger assets are served locally by `drf-spectacular-sidecar`; no CDN needed.
Docs are public; every data route requires JWT. Click **Authorize** and paste
the access token (without `Bearer` — Swagger adds it).

All application models use UUIDv4 primary keys exposed as UUID strings;
detail routes use Django's `<uuid:pk>` converter.

### Authentication — `/api/v1/auth/`

| Method | Route | Behaviour |
| --- | --- | --- |
| POST | `register/` | Creates a CUSTOMER account; role/staff fields rejected. |
| POST | `login/` | Returns `access` (5 min) + `refresh` (1 day, rotates on use). |
| POST | `refresh/` | Rotation; old refresh token becomes unusable. |
| POST | `logout/` | Revokes the supplied refresh token (blacklist). |
| GET | `me/` | Current user's profile. |

### Customers — `/api/v1/customers/`

| Method | Route | Access |
| --- | --- | --- |
| GET | `/` | Customers: own profile. ADMIN/OPERATIONS: all. |
| POST | `/` | One profile per account; admins supply `user`. |
| GET / PATCH | `/{id}/` | Ownership immutable; delete/PUT not exposed. |

### Credit — `/api/v1/customers/{customer_id}/credit-assessments/` and `/api/v1/credit-assessments/{id}/`

POST assesses the profile (inputs come from saved data; callers cannot submit
a score), GET lists paginated history / retrieves one saved assessment.
Read-only results; customers see only their own.

### Loans — `/api/v1/loans/`

| Method | Route | Behaviour |
| --- | --- | --- |
| GET / POST | `/` | List (scoped) / originate against assessment + vehicle. |
| GET | `/{id}/` | Loan detail. |
| GET | `/{id}/installments/` | Read-only repayment schedule. |
| POST | `/{id}/activate/` | Re-checks eligibility/affordability, sets balance to total repayable. |
| POST | `/{id}/cancel/` | Cancels a PENDING loan. |

### Payments — `/api/v1/...`

| Method | Route | Behaviour |
| --- | --- | --- |
| POST | `payments/initialize/` | Start a payment for a loan (`PAYSTACK` or `MOCK_MOMO`). |
| GET | `payments/{reference}/verify/` | Pull latest provider state; settles if terminal. |
| GET | `payments/` | Payment ledger (scoped). |
| GET | `payments/webhook-events/` | Audit trail of every webhook delivery. |
| POST | `webhooks/paystack/` | Public; HMAC-SHA512 signature-verified. |
| POST | `webhooks/momo/simulate/` | Dev trigger; staff **session** auth only (JWT deliberately refused). |

### Vehicles & devices — `/api/v1/...`

| Method | Route | Access |
| --- | --- | --- |
| GET | `vehicles/` | Customers: assigned vehicles; operations/admin: all. |
| POST / PATCH | `vehicles/…` | Operations/admin only. |
| GET / POST / PATCH | `devices/…` | Operations/admin only; one device per vehicle. |
| GET | `vehicles/{id}/telemetry/` | Paginated history; `start`/`end` ISO filters; `ordering`. |

### Alerts — `/api/v1/alerts/`

GET with `vehicle`, `type`, `resolved` filters (customers scoped to their
vehicles); `POST /alerts/{id}/resolve/` for operations/admin.

### Platform

`GET /api/health/` — public liveness (HTTP app, not DB readiness).

---

## Payment flow

The system depends on a small `PaymentProvider` interface — `create_payment`,
`verify_payment`, `verify_webhook_signature` — never on Paystack directly.
`get_provider(name)` is the only factory, so adding a provider touches one
file. Paystack amounts are handled in subunits (pesewas/kobo) per their API.

```text
Django                    initialize transaction (TEST mode)
  │  POST /api/v1/payments/initialize/
  │    → Payment row created PENDING (append-only ledger)
  │    → provider returns checkout_url
  ▼
Test checkout page ──customer pays with test card──▶ Paystack
  │
  ▼
Paystack webhook ──POST /api/v1/webhooks/paystack/──▶ Django
  │  1. verify HMAC-SHA512 signature        (reject → 401 + audited)
  │  2. find payment by reference           (unknown → audited, no action)
  │  3. RE-VERIFY with GET /transaction/verify   (payload never trusted)
  │  4. cross-check amount + currency       (mismatch → FAILED, no credit)
  │  5. conditional update WHERE status='PENDING'  (idempotent winner)
  │  6. lock loan row → update balance/status → commit
  ▼
Loan balance reduced (or loan COMPLETED at full repayment)
```

Verification (`GET /api/v1/payments/{reference}/verify/`) runs the same
settlement path, so a missed webhook self-heals on the next verification.

---

## Webhook architecture

Webhooks are unauthenticated by design (providers cannot hold JWTs) and are
protected by **signature verification** instead: Paystack signs with
HMAC-SHA512 over the raw request body using the secret key; the handler
compares with `hmac.compare_digest` (constant-time) and rejects anything else
with 401. Payloads are never trusted for the outcome — they only *point at* a
transaction; step 3 above re-verifies with the provider's API before any
balance moves, so a forged or replayed payload cannot create money.

**Idempotency** — duplicate deliveries are guaranteed, not exceptional
(QoS/retries on the provider side). Three layers prevent double effects:

1. **Conditional terminal transitions**: settlement updates
   `Payment … WHERE status = 'PENDING'`; under concurrent redelivery exactly
   one request wins the row, the loser observes "already processed".
2. **Loan row lock**: status + outstanding balance change atomically in one
   transaction — no partial updates, ever.
3. **Audit trail**: every delivery (processed, duplicate, rejected, unknown)
   is recorded in `WebhookEvent` and browsable at
   `GET /api/v1/payments/webhook-events/`.

Dedicated tests cover duplicate webhook delivery and assert that the second
delivery produces **no** financial side effect.

---

## MQTT architecture

Topics: `vehicles/{vehicle_id}/telemetry` (QoS 1), published by devices or the
simulator. The consumer **is a separate long-lived process**
(`python manage.py run_mqtt_consumer`) — HTTP workers never touch the broker,
so a broker outage cannot affect API latency and a web redeploy cannot drop
the subscription. The consumer subscribes with a wildcard, reconnects with
bounded backoff, and shuts down cleanly on SIGTERM/Ctrl+C.

The ingest pipeline (`telemetry/services.py`) is transport-agnostic — the
broker adapter is thin, and a future AWS IoT Core rule or REST ingestion
endpoint could call the same functions:

- `parse_payload` — one place for validation: ranges, types, clock-skew rejection.
- `resolve_vehicle` — the payload's `vehicle_id` is **never trusted**; the
  registered Device mapping is authoritative, so a misconfigured device cannot
  write into another vehicle's history.
- `ingest_telemetry` — record insert + denormalized vehicle state
  (position, ONLINE, MOVING/PARKED at 1 km/h) in one transaction under a row
  lock, with alert evaluation inside the same transaction.

**Idempotency at the database**: a unique `(device_id, recorded_at)`
constraint collapses QoS 1 redeliveries and consumer restarts into one stored
record — the transport layer cannot be trusted to deduplicate.

History is exposed read-only at `GET /api/v1/vehicles/{id}/telemetry/` with
pagination, `start`/`end` ISO range filters and `ordering`; invalid filters
fail loudly (400) rather than silently returning everything.

---

## GPS simulator

`gps-simulator/simulator.py` is a standalone script with its own requirements
(just paho-mqtt) and **zero database access** — the backend is the only writer.
It random-walks a virtual vehicle (heading drift, speed noise, brief stops,
battery drain) and publishes spec-shaped payloads until stopped:

```bash
.venv/bin/python gps-simulator/simulator.py \
  --device-id GPS-001 --vehicle-id <vehicle-uuid> --interval 2.0
# or: docker compose --profile demo up simulator
```

All configuration comes from flags or environment variables: `MQTT_BROKER_HOST`,
`MQTT_BROKER_PORT`, `GPS_DEVICE_ID`, `GPS_VEHICLE_ID`, `GPS_START_LAT/LON`
(default Accra), `GPS_INTERVAL_SECONDS`, `GPS_SPEED_KPH`.

The full demo loop: vehicle moving → MQTT message → consumer → database →
`GET /api/v1/vehicles/{id}/` shows updated position and `ONLINE`, history
accumulates at `/telemetry/`, alerts appear at `/api/v1/alerts/` when the walk
crosses a geofence or battery threshold.

---

## Credit scoring architecture

Two deliberately separate pieces:

- `credit/rules.py` — a **frozen, versioned policy** (`demo-v1`). Changing
  rules means saving a new version; existing assessments keep their recorded
  rules.
- `credit/scoring.py` — evaluates plain inputs with no database or provider
  dependencies, so scoring is unit-testable in isolation.

`demo-v1` starts at 300 points:

| Factor | Points |
| --- | --- |
| Positive monthly income | +100 |
| Debt payments / income | ≤20%: +200 · ≤40%: +125 · ≤60%: +50 · above: +0 |
| Outstanding debt / monthly income | ≤1: +100 · ≤3: +50 · above: +0 |
| Employed or self-employed | +75 |
| Employment duration (current) | ≥24 mo: +75 · ≥6 mo: +40 |

Bands: **700–850 LOW/APPROVED · 550–699 MEDIUM/REVIEW · 300–549 HIGH/REJECTED**,
with explicit overrides: zero income rejects outright (no division by zero);
debt payments above 60% of income force rejection regardless of score;
outstanding debt with no reported monthly obligation prevents auto-approval and
adds a review reason. Ratios are dimensionless, so currencies never compare
across amounts; comparisons use exact decimals before display rounding.

The service locks the customer row briefly and saves score, decision, factors,
**input snapshot** and **rules snapshot** in one transaction — edit the profile
afterwards and past assessments stay byte-identical (a tested guarantee).
Each POST creates a new assessment; results are read-only through the API.

This is an illustrative points model, not a calibrated credit score: no bureau
data, verified income, or loan-affordability input. APPROVED does not activate
a loan — origination re-checks eligibility separately.

---

## Render deployment

The repository ships a [Render Blueprint](render.yaml): connect the repo at
dashboard.render.com → **New → Blueprint Instance** → Render creates:

| Service | Type | Start command |
| --- | --- | --- |
| `mobility-finance-db` | PostgreSQL 16 (free) | managed by Render |
| `mobility-finance-api` | web | gunicorn on `$PORT`, health-checked at `/api/health/` |
| `mobility-finance-consumer` | worker | `python manage.py run_mqtt_consumer` |

`build.sh` (install → migrate → collectstatic) runs with `set -euo pipefail`
so a broken release never replaces a working one, and owns migrations
exclusively — the worker's build skips them so concurrent deploys cannot race
DDL. Settings trust Render's TLS-terminating proxy
(`SECURE_PROXY_SSL_HEADER`), which is what makes `SECURE_SSL_REDIRECT` safe
behind the proxy. Secrets are dashboard-only: Paystack keys are declared
`sync: false` (Render prompts on first deploy); runtime secrets are
`generateValue`. `autoDeploy: true` redeploys on every push.

After the first deploy:

1. Verify `https://<service>.onrender.com/api/health/`.
2. Web service **Shell** → `cd backend && python manage.py createsuperuser`.
3. Set `MQTT_BROKER_HOST` for the worker (a public test broker for the demo —
   Render does not host brokers; AWS IoT Core is the production path below).

### Deploying the frontend (Vercel) and wiring callback + webhook

Deploying the React frontend to a public URL is what completes the Paystack
callback loop, and the deployed backend is what receives the webhook — no
ngrok or tunnel needed once both are live.

1. **Deploy the frontend to Vercel** — import the repo, set the **root
   directory** to `frontend/`. Vercel auto-detects Vite; `vercel.json` already
   provides the SPA rewrite. Set one environment variable before deploying:
   `VITE_API_BASE_URL=https://<api-service>.onrender.com` (Vite inlines it at
   build time — changing it later requires a redeploy).
2. **Point the backend at the frontend** (Render dashboard → api service →
   Environment):
   - `PUBLIC_SITE_BASE_URL=https://<your-app>.vercel.app` — this becomes the
     `callback_url` Paystack embeds in each checkout session, so after the
     success screen the payer is redirected to
     `https://<your-app>.vercel.app/payments?reference=<ref>`, where the app
     auto-verifies and shows the result.
   - `CORS_ALLOWED_ORIGINS=https://<your-app>.vercel.app` — the browser needs
     explicit cross-origin approval to call the API (JWT uses the
     Authorization header, so no cookies are involved).
   Redeploy or restart the service after changing env vars.
3. **Point Paystack at the backend webhook** (Paystack dashboard → Settings →
   API Keys & Webhooks, TEST mode): set the webhook URL to
   `https://<api-service>.onrender.com/api/v1/webhooks/paystack/`. Paystack
   then pushes `charge.success` events, the handler verifies the HMAC
   signature and re-verifies with the API before settling — the verify
   endpoint remains the self-healing fallback either way.

Order matters on first setup: deploy the backend first (you need its URL for
step 1), then the frontend, then finish steps 2–3 with both URLs known.

Free-tier services sleep after inactivity (slow first request) and the free
worker restarts periodically, which the consumer handles by design. Note that
Paystack's webhook cannot wake a sleeping free-tier service — for demo
webhook testing, keep the service warm (a periodic ping) or rely on the
verify path, which settles on demand.

---

## Testing

From `backend/`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run    # no uncommitted model changes
python manage.py test --parallel                     # full suite (~150 tests)
python manage.py spectacular --validate --fail-on-warn
```

From the repository root: `ruff check backend gps-simulator` and
`ruff format --check backend`.

Coverage of the areas that matter: JWT lifecycle (rotation, revocation,
expiry, privilege escalation), credit cutoff boundaries and snapshot
immutability, interest/rounding and month-end clamping, eligibility and
affordability rejections, **duplicate webhook delivery with no double
application**, Paystack signature rejection, MoMo simulation, loan balance
updates under full and partial repayment, telemetry idempotent ingestion,
device-mismatch rejection, geofence detection, alert lifecycle, offline
semantics, and API scoping (a customer's 404 on another customer's data).

CI (`.github/workflows/ci.yml`) runs the same gates on every push/PR against
a **real PostgreSQL 16 service container** — the same engine as development
and production, so partial unique constraints, CHECK constraints and row
locking behave in CI exactly as locally.

---

## Production architecture

The portfolio version runs on one cheap Render web service, one worker, and
Mosquitto. The documented production evolution:

**Payments** — same provider interface; production adds a queue (Celery +
Redis) between webhook receipt and settlement so provider outages during
re-verification retry safely, plus dead-letter handling and reconciliation
jobs comparing the ledger against provider settlement reports.

**Telemetry / IoT** — the local chain is:

```text
GPS simulator → Mosquitto (local) → run_mqtt_consumer → PostgreSQL
```

Production replaces the broker, not the pipeline:

```text
GPS device → AWS IoT Core (MQTT, per-device certs) → IoT Rule
           → backend ingest (same services.py) → PostgreSQL
```

AWS IoT Core adds what a demo broker lacks: mutual-TLS device identity,
fine-grained topic authorization (a device may publish only its own topic),
fleet-scale managed MQTT, and rules routing. The consumer's transport-agnostic
services are the migration seam. High-volume history would move to a
time-series store (TimescaleDB) with PostgreSQL keeping recent data.

**Scaling** — the monolith scales horizontally behind a load balancer
(stateless views); Postgres gets a read replica for history queries; Celery
beat owns scheduled work (offline checks, token cleanup) instead of cron;
S3/static CDN in front of whitenoise; Sentry + structured logging.

---

## Limitations

- **No real financial transactions.** Paystack TEST mode only; MoMo is a local
  simulator; the credit engine is illustrative, not a regulated decisioning model.
- **Email is contact information** — not verified, not unique, no password
  recovery yet; username is the login identity.
- **In-memory rate limiting** — per-process only, not distributed protection.
- **Telemetry retention is unlimited** — a demo database, not a retention policy.
- **MQTT broker is anonymous and local/containerized** — device `device_id` is
  a routing label, not a credential; broker auth/TLS is out of demo scope.
- **Free-tier realities** — sleeping services, periodic worker restarts.
- **No frontend** — the API is the product; Swagger is the client.
- **Deletion APIs intentionally absent** — financial history is PROTECTed.

## Future improvements

- Celery + Redis: webhook settlement retries, scheduled offline checks,
  token cleanup, notification fan-out.
- Payment reconciliation job and provider settlement reports.
- Per-device MQTT credentials + broker TLS; AWS IoT Core integration.
- TimescaleDB-backed telemetry history with downsampling and retention.
- Email verification, password reset, and audit logging of staff actions.
- Simple Vue/React dashboard over the existing API (loosely coupled by design).
- Amortizing (reducing-balance) interest as a second versioned calculation.

---

See [docs/development.md](docs/development.md) for the decision log behind
every milestone, including the reasoning for each dependency, constraint, and
trade-off above.
