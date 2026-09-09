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

## Next small milestone

Swagger is available at `/api/docs/`, with the schema at `/api/schema/`.
drf-spectacular generates OpenAPI from the serializers; explicit token responses
describe rotation and logout accurately. Its sidecar package serves UI assets
locally. Schema validation is part of verification.

Test customer creation, listing and updates in Swagger, then build the rules-based
credit assessment engine. Basic vehicles/devices follow before vehicle-linked loans.

## Remaining phases

1. Credit assessments with explainable, versioned rules.
2. Basic vehicles/devices, loans and repayment schedules.
3. Test payments, provider abstraction, verified/idempotent webhooks and Mock MoMo.
4. Mosquitto, a separate MQTT consumer and GPS simulator.
5. Telemetry history, geofences, alerts and retention.
6. Docker and Compose.
7. Consolidated tests and GitHub Actions CI.
8. Render deployment.
9. Portfolio demonstration, README and production evolution documentation.

Tests and documentation accompany every milestone. No paid cloud resources are
needed for the local implementation.
