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
- DRF defaults to authenticated access. Only the liveness endpoint is public.
  Session authentication is sufficient for the foundation; JWT comes next.
- Environment variables override the root `.env`. Secret key and database URL
  are required. Deployment configuration and hardening will be completed in the
  deployment phase; current settings are not a finished deployment recipe.

## Dependencies

Django provides models, migrations, authentication and admin. DRF provides the API
foundation. Psycopg connects to PostgreSQL. django-environ parses settings and the
database URL. Ruff formats and checks Python. Django's built-in test runner avoids
adding a second test framework. Requirements pin the installed dependency set;
updates should be deliberate and verified.

## Next small milestone

Implement registration, JWT login/refresh/logout and a current-user endpoint.
Public registration must always create a CUSTOMER. Test unauthenticated access,
invalid credentials, role escalation attempts and refresh-token invalidation.
Then introduce customer profiles with ownership permissions and OpenAPI docs.

## Remaining phases

1. Complete authentication, customer profiles and API documentation.
2. Basic vehicles/devices, credit assessments, loans and repayment schedules.
3. Test payments, provider abstraction, verified/idempotent webhooks and Mock MoMo.
4. Mosquitto, a separate MQTT consumer and GPS simulator.
5. Telemetry history, geofences, alerts and retention.
6. Docker and Compose.
7. Consolidated tests and GitHub Actions CI.
8. Render deployment.
9. Portfolio demonstration, README and production evolution documentation.

Tests and documentation accompany every milestone. No paid cloud resources are
needed for the local implementation.
