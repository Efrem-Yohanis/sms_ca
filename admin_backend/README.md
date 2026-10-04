# Admin Backend

`admin_backend` is a standalone Django service for platform administrators. It
shares the campaign service's database and existing SMSC, Sender ID, Channel,
global TPS, N-address request-size, and campaign tables. It owns the user
profiles and roles, configuration assignments, SMSC/channel and
Sender-ID/SMSC bindings, assignable N-addresses, audit records, and login
attempts.

The service does not replace or change the campaign service's message-sending
path. Existing configuration tables are mapped as unmanaged Django models, so
admin migrations do not recreate those tables.

## Roles

- **Admin**: can sign in to this service's Django admin and admin API.
- **Campaign Manager**: cannot access the Django admin or admin API; can read
  only active configuration assigned to their account through
  `GET /api/v1/configurations/assigned/`.

Profiles are backfilled by migration `0002`: existing Django staff and
superusers become Admins, and other existing users become Campaign Managers.
New users created through Django's user creation flow also get a profile.

## Local setup

From this directory, set `DJANGO_SECRET_KEY` and the same
`FIELD_ENCRYPTION_KEY` used by `sms_campign`, then run:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8002
```

The local SQLite default points to `sms_campign/db.sqlite3`. To use PostgreSQL,
set `DB_ENGINE=postgresql` and the shared `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_HOST`, and `DB_PORT` environment variables.

With Docker Compose, set the deployment secrets in the environment and start
the full stack, including the campaign UI, admin backend, and admin UI:

```powershell
docker compose up --build -d
docker compose exec admin_backend_app python manage.py createsuperuser
```

The campaign UI is at `http://localhost:3000`, the admin UI is at
`http://localhost:4173`, and the admin API and Django admin are at
`http://localhost:8002/api/v1/` and `http://localhost:8002/admin/`. The
admin_backend_app container applies migrations on startup after
the campaign service is healthy. Use the same Django signing secret across
the campaign and admin services so campaign users created here can sign in to
the campaign UI with their admin-assigned credentials. The browser-facing
campaign UI origin must also be included in `ADMIN_BACKEND_CORS_ORIGINS`.

## API docs and Swagger

The backend exposes an OpenAPI schema and Swagger UI via Drf Spectacular:

- `GET /api/v1/schema/` — raw OpenAPI schema
- `GET /api/v1/docs/` — Swagger UI
- `GET /api/v1/redoc/` — ReDoc UI

These endpoints are available from the same base API prefix and are enabled in
`admin_backend/settings.py`, `admin_backend/urls.py`, and
`admin_control/schema_urls.py`.

## API surface

All routes below are under `/api/v1/`. Login returns SimpleJWT access and
refresh tokens; send the access token as `Authorization: Bearer <token>`.

| Route | Purpose |
| --- | --- |
| `POST /admin/auth/login/` | Admin-only login using username or email |
| `POST /admin/auth/initial-password/` | Validate a temporary Admin password and require its replacement |
| `POST /admin/auth/password-reset/request/` | Email a one-time password reset link to the account address |
| `POST /admin/auth/password-reset/confirm/` | Validate a reset-link token and set a new password |
| `GET /admin/me/` | Current Admin profile |
| `/admin/users/` and `/admin/users/<id>/` | User CRUD, role, status, TPS limit, and assignments |
| `POST /admin/users/<id>/password-reset/` | Admin-initiated password reset |
| `GET/PATCH/POST /admin/email-config/` | Legacy default-service settings and test-email endpoint |
| `GET/POST /admin/email-services/` | List or create Admin-only SMTP email services |
| `PATCH/DELETE /admin/email-services/<id>/` | Update or delete an Admin email service |
| `POST /admin/email-services/<id>/test/` | Test a saved Admin email service |
| `/admin/smsc-configs/` | Existing SMSC API configurations |
| `/admin/sender-ids/` | Existing Sender IDs |
| `/admin/channels/` | Existing Channels |
| `/admin/tps-configs/` | Existing global TPS configurations |
| `/admin/n-address-configs/` | Existing max-addresses-per-request configurations |
| `/admin/n-addresses/` | Assignable N-address values and pools |
| `/admin/sender-smsc-bindings/` | Sender ID to SMSC bindings |
| `/admin/channel-smsc-bindings/` | Channel to SMSC bindings, TPS, and allowed Sender IDs |
| `GET /configurations/assigned/` | Active, user-scoped configuration for the campaign UI |
| `GET /admin/audit-log/` | Filterable administrative audit events |
| `GET /admin/login-attempts/` | Login history |
| `GET /health/` | Unauthenticated health check |

User list filters include `role`, `department`, `status` (`active`, `inactive`,
or `locked`), `is_active`, `assigned`, and `search`. User and config
assignments can be submitted from the user detail API or the corresponding
config API. Create Sender IDs with `smsc_ids`; Sender IDs also expose
`sender_type`, `country`, and optional `tps_limit`. Create Channels with one or
more `smsc_bindings` entries (`smsc`, optional `allowed_sender_ids`,
`default_tps`, and `priority`). SMSC secrets are write-only and audit values
redact credentials.

The The admin console creates accounts with no configuration assignments. It sends
the supplied temporary password and a role-specific login link using the active
default service configured under Email Config. New users must change that
password before tokens are issued. Manage their SMSC, Sender ID, Channel, TPS,
and N-address access from the corresponding tabs on the user detail page.
Admin email services are stored separately from Campaign Manager email
settings.

Forgot-password requests return a generic response and email a role-specific
reset link when an eligible account exists. Links expire after 10 minutes and
are single-use. The link opens `/reset-password` in the appropriate UI; the
new password is submitted to the API from that page. Account-created and
password-reset emails use responsive HTML templates with plain-text
alternatives.

## Current scope boundary

TPS values and assignments are stored and managed here, but applying their
effective minimum to message sending, generating throttling alerts, SMSC
connection testing/health monitoring, and recent-send monitoring are not
implemented in this iteration. The campaign UI uses assigned configuration
for display and selectors; this does not disable legacy campaign configuration
write routes at the API layer.

## Validation

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test admin_control
```
