# SMS Admin Application Guide

## Purpose

The admin application is the control plane for the SMS campaign platform. Platform administrators use it to manage accounts, assign the SMSC connections and messaging configuration available to campaign managers, and review administrative access records.

It has two parts:

- **Admin UI** (`admin-ui`): the browser console and sign-in page.
- **Admin backend** (`admin_backend`): a Django REST API and a restricted Django admin site. It shares the campaign service database. Existing campaign configuration tables are managed by the campaign service; the admin backend maps them without recreating them. It owns admin profiles, configuration bindings and assignments, audit events, and login-attempt records.

The admin application configures the SMS platform; it does not itself send SMS or replace the campaign service's sending path.

## What It Does

Administrators can use the API-backed parts of the console to:

- Create and manage Admin and Campaign Manager accounts, including status, lock state, department, notes, TPS limit, and assigned resources.
- Manage SMSC connection settings, Sender IDs, Channels, global TPS settings, and assignable N-address values; assign supported resources to campaign managers.
- Provide campaign managers with their assigned active configuration through the assigned-configuration API.

The backend API also supports administrator-initiated password resets, audit-log and login-attempt queries, maximum-addresses-per-request configuration, and explicit Sender-ID/SMSC and Channel/SMSC binding operations. The current console does not expose all of these as screens or controls.

Campaign managers cannot use the admin API or Django admin. They can read only their active assigned configuration from `GET /api/v1/configurations/assigned/`.

## How It Works

1. An administrator signs in at `/login` using a username or email address and password.
2. The UI sends credentials to `POST /api/v1/admin/auth/login/`. The backend returns access and refresh tokens; the UI stores them in browser local storage.
3. The console validates the session with `GET /api/v1/admin/me/` and loads users and configuration from the admin API.
4. User and configuration changes made in supported screens are sent to the backend with the access token as `Authorization: Bearer <token>`. The backend checks the Admin role and records relevant changes in the audit log.
5. Campaign managers authenticate in the campaign application and retrieve only configuration assigned to their account.

Only active, unlocked Admin accounts may access the admin API. The Django admin site requires an active staff account with the Admin role; a superuser without a profile is also accepted by its permission check. Campaign Manager accounts are not permitted to use either admin interface.

## Access Points

With the full local Docker Compose stack running, the default addresses are:

| Service | Address | Use |
| --- | --- | --- |
| Admin UI | `http://localhost:4173` | Administrator web console |
| Admin sign-in | `http://localhost:4173/login` | Sign-in page |
| Admin REST API | `http://localhost:8002/api/v1/` | Admin API base path |
| API health check | `http://localhost:8002/api/v1/health/` | Unauthenticated service health check |
| Django admin | `http://localhost:8002/admin/` | Restricted Django administration site |
| Campaign UI | `http://localhost:3000` | Campaign manager application |

The admin UI also has direct routes for `/users`, `/campaigns`, `/smsc-accounts`, `/sender-ids`, `/channels`, `/tps`, `/n-addresses`, `/tps-n-addresses`, `/smtp`, `/system-logs`, and `/kafka-monitor`. `/` opens the Users console. These URLs identify UI screens; they do not imply that every screen is connected to live operational data.

When running the UI with its development server, it normally uses `http://localhost:5173`. Set `VITE_ADMIN_API_URL` to the browser-reachable API base, including `/api/v1`, if the API is not at `http://localhost:8002/api/v1`.

## Live Data Versus Preview Screens

The current UI uses the admin API for sign-in, current-admin identity, user management, and SMSC, Sender ID, Channel, TPS, and N-address configuration. Supported edits in these sections persist through the backend.

The Campaigns list and details, dashboard metrics/activity, SMTP screen, System Logs screen, and Kafka Monitor currently display preview or sample data. Do not treat those screens as live campaign, mail, audit-log, or Kafka monitoring. The backend does expose audit-log and login-attempt APIs, but those preview screens are not wired to them.

TPS limits and assignments are stored and displayed, but this iteration does not enforce the effective TPS minimum in message sending. SMSC connection testing/health monitoring, throttling alerts, and recent-send monitoring are also outside the current implementation.

## API Access Points

All endpoints below are under `http://localhost:8002/api/v1` by default. Admin endpoints require an access token unless indicated otherwise.

| Method and path | Purpose |
| --- | --- |
| `POST /admin/auth/login/` | Admin sign-in; returns access and refresh tokens |
| `GET /admin/me/` | Current Admin profile |
| `GET, POST /admin/users/` | List or create users |
| `GET, PATCH, DELETE /admin/users/<id>/` | Read, update, or delete a user profile |
| `POST /admin/users/<id>/password-reset/` | Set another user's password |
| `GET, POST /admin/smsc-configs/`; `GET, PATCH, DELETE /admin/smsc-configs/<id>/` | Manage SMSC configurations |
| `GET, POST /admin/sender-ids/`; `GET, PATCH, DELETE /admin/sender-ids/<id>/` | Manage Sender IDs |
| `GET, POST /admin/channels/`; `GET, PATCH, DELETE /admin/channels/<id>/` | Manage Channels and their SMSC bindings |
| `GET, POST /admin/tps-configs/`; `GET, PATCH, DELETE /admin/tps-configs/<id>/` | Manage global TPS configuration |
| `GET, POST /admin/n-address-configs/`; `GET, PATCH, DELETE /admin/n-address-configs/<id>/` | Manage maximum addresses per request |
| `GET, POST /admin/n-addresses/`; `GET, PATCH, DELETE /admin/n-addresses/<id>/` | Manage assignable N-address values |
| `GET, POST /admin/sender-smsc-bindings/`; `GET, PATCH, DELETE /admin/sender-smsc-bindings/<id>/` | Manage Sender ID to SMSC bindings |
| `GET, POST /admin/channel-smsc-bindings/`; `GET, PATCH, DELETE /admin/channel-smsc-bindings/<id>/` | Manage Channel to SMSC bindings, default TPS, and allowed Sender IDs |
| `GET /configurations/assigned/` | Return active configuration assigned to the signed-in platform user |
| `GET /admin/audit-log/` | Read filterable administrative audit events |
| `GET /admin/login-attempts/` | Read login attempt history |
| `GET /health/` | Unauthenticated backend health check |

For authenticated API calls, send `Authorization: Bearer <access-token>`. SMSC credentials are write-only in the API, and audit snapshots redact credentials.

## Start the Local Stack

From the repository root, start the services and create the first admin account:

```powershell
docker compose up --build -d
docker compose exec admin-backend python manage.py createsuperuser
```

Open `http://localhost:4173` and sign in with the Admin account. The backend applies migrations when it starts after the campaign service is healthy.

For local development without Docker, see `admin_backend/README.md` for backend environment variables and database setup. The UI can be started from `admin-ui` with `npm install` followed by `npm run dev`; configure `VITE_ADMIN_API_URL` when the backend is not using its default address.

## Deployment Notes

Configure production secrets and database settings through the deployment environment. `DJANGO_SECRET_KEY` must be shared between the campaign service and admin backend so accounts created by an administrator can authenticate in the campaign application. `FIELD_ENCRYPTION_KEY` must match the campaign service key so existing encrypted SMSC credentials remain readable. Set `ADMIN_BACKEND_CORS_ORIGINS` to include the browser-facing UI origin, and set `VITE_ADMIN_API_URL` to the browser-reachable API URL.

Do not use the development fallback secrets in `compose.yaml` for a deployed environment.

## Related Documentation

- `admin_backend/README.md` - backend setup, roles, API filters, scope boundaries, and validation commands.
- `admin-ui/README.md` - UI development and API URL configuration.
