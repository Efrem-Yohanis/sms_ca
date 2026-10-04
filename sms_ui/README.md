# SMS Campaign Manager UI

The `sms_ui` application is the browser interface used by campaign operators to
create and manage SMS campaigns. It is a frontend application; campaign
execution, authentication, configuration, and message delivery are handled by
the campaign and admin backend services.

## What the UI does

The main navigation provides these areas:

- **Dashboard** — campaign overview and operational status.
- **Campaigns** — create, review, edit draft campaigns, and manage campaign
  execution actions such as start, pause, resume, and stop where available.
- **Audiences** — create and inspect campaign recipients. An audience can be
  entered manually, imported from CSV or Excel, or sourced from a configured
  database table. Recipient numbers are validated and the audience build
  reports valid and invalid counts.
- **Schedules** — create, inspect, and edit campaign schedules, including
  one-time, daily, weekly, or monthly schedules and time windows.
- **Messages** — create and maintain reusable message content. Campaign
  messages support English, Amharic, Tigrinya, Afaan Oromoo, and Somali.
- **Reports** — create and manage campaign reports, choose campaigns and
  recipients, configure report frequency, and run or trigger reports.
- **Configurations** — view assigned SMSC, Sender ID, Channel, TPS, and
  N-address configuration. These settings are read-only in this UI; changes
  are made through the separate Admin UI.
- **Test SMS** — submit a test message using an assigned active Sender ID and
  Channel, inspect the provider response, resend, and review recent test
  messages.

Campaigns are assembled through a wizard covering campaign information,
audience, message, schedule, and review. The campaign UI is not the SMS
delivery engine: it sends requests to backend APIs, and the backend and
messaging services perform campaign processing and delivery.

## Technology and request flow

- **Frontend:** React 18, TypeScript, and Vite.
- **Navigation:** React Router.
- **Server state:** TanStack Query.
- **UI:** Tailwind CSS, Radix UI/shadcn-style components, and Lucide icons.
- **API calls:** Fetch-based API modules under `src/lib/api/`.

The UI calls the campaign backend for login, campaigns, audiences, schedules,
messages, reports, and test SMS. The default campaign API base is relative
(`/api/v1`), so it uses the same origin as the UI. The UI also calls the
admin backend directly to retrieve the signed-in user's assigned active
configurations through `GET /api/v1/configurations/assigned/`.

After login, the UI keeps the JWT access token, refresh token, and username in
browser `localStorage`. Authenticated campaign API requests carry the access
token in the `Authorization: Bearer <token>` header. On an expired access
token, the API helper attempts a refresh; if refresh fails, the UI clears the
stored auth values and returns to the login page. Users who sign in with a
temporary password must change it before continuing.

## Access points

With Docker Compose, open the campaign UI at:

- `http://localhost:3000`

The default backend addresses used by the local stack are:

- Campaign backend: `http://localhost:8000`
- Admin backend: `http://localhost:8002`

For local frontend development, run Vite from this directory. It serves on
`http://localhost:5123` and proxies `/api/` requests to the campaign backend
at `http://localhost:8000`.

## Configuration

Vite variables are build-time values:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Empty | Optional origin/prefix for campaign API requests. Leave empty when the API is available at the same origin under `/api/v1/`. |
| `VITE_ADMIN_API_BASE_URL` | `http://localhost:8002` | Admin backend origin, without `/api/v1`; used to load assigned configurations and perform password-reset requests. |

When deploying, set `VITE_ADMIN_API_BASE_URL` to an origin reachable by the
user's browser, not only by the frontend container. The admin backend must
allow the campaign UI origin in `ADMIN_BACKEND_CORS_ORIGINS`. The campaign and
admin backends must also use compatible JWT signing configuration for the
campaign UI to retrieve the signed-in user's assigned configurations.

The Docker image accepts both variables as build arguments. The Compose
campaign UI service passes `VITE_ADMIN_API_BASE_URL`; configure
`VITE_API_BASE_URL` as a build argument too if the campaign API is not
available through the same origin.

## Assigned configuration and access boundary

The campaign UI does not provide a fallback to the campaign backend's global
configuration list. Its configuration view and campaign/Test SMS selectors
use the signed-in user's assigned active Sender IDs and Channels, and the
configuration page displays the other assigned settings returned by the admin
backend. If the admin API cannot be reached, those features report an error
rather than silently using a different configuration source.

Configuration creation and assignment are performed in the Admin UI. The
campaign backend remains responsible for enforcing its own authorization and
business rules; hiding or limiting a control in this frontend is not a
replacement for backend access control.

## Logging and operational visibility

The UI displays campaign execution progress and report information returned
by the campaign backend. The Test SMS page also stores and displays test
submissions, acceptance/provider status, and available request/response
details. This is not a general application log viewer. Administrative audit
events and login-attempt history belong to the Admin UI and admin backend.

## Local development

Requirements: Node.js and npm, plus the campaign backend. The admin backend
must also be available for assigned configuration and password-reset
functionality.

```powershell
npm ci
npm run dev
```

Useful commands:

```powershell
npm run build
npm run lint
npm test
```

The Docker Compose stack can also build and serve the UI:

```powershell
docker compose up --build -d campaing__manager_ui_app
```

The Compose service name retains the existing spelling
`campaing__manager_ui_app`.
