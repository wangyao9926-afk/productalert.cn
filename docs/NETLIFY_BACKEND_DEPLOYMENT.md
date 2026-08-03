# Netlify frontend and API deployment

This project is a split deployment: Netlify hosts the React frontend, while an HTTPS Python service hosts the FastAPI API, PostgreSQL connection, and Redis/RQ workers. Do not put database or Redis credentials into Netlify variables.

## 1. Deploy the backend first

Deploy the repository root to an HTTPS Python service such as Render or Railway. Create three processes that share the same environment variables:

| Process | Start command | Purpose |
| --- | --- | --- |
| API | `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Login, API, exports, evidence access |
| Scan worker | `python -m app.rq_worker` | Scheduled and manual crawl jobs |
| Notification worker | `python -m app.notification_worker` | Webhook, Enterprise WeChat, and Feishu delivery |

Set these backend variables before starting the API. Replace the example domains; do not copy credentials into Git.

```text
APP_ENV=production
DATABASE_URL=postgresql://<user>:<password>@<host>/<database>?sslmode=require
QUEUE_BACKEND=rq
REDIS_URL=rediss://:<password>@<host>:<port>/0
START_BACKGROUND_WORKERS=false
START_NOTIFICATION_WORKER=false
APP_PUBLIC_URL=https://<your-netlify-site>.netlify.app
CORS_ALLOWED_ORIGINS=https://<your-netlify-site>.netlify.app
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
```

After the Netlify site has a custom domain, append it to both public URL and CORS settings:

```text
APP_PUBLIC_URL=https://app.productalert.cn
CORS_ALLOWED_ORIGINS=https://<your-netlify-site>.netlify.app,https://app.productalert.cn
```

Run the production readiness gate with PostgreSQL and RQ before release:

```powershell
.\deploy-check.ps1 -Backend postgresql -Queue rq -DatabaseUrl $env:DATABASE_URL -RedisUrl $env:REDIS_URL
```

## 2. Deploy the frontend on Netlify

Import the GitHub repository in Netlify. `netlify.toml` already sets the frontend base directory, build command, and SPA redirect.

In **Site configuration → Environment variables**, set:

```text
VITE_API_BASE_URL=https://<your-backend-domain>
VITE_ENABLE_DEMO_FALLBACK=false
```

`VITE_API_BASE_URL` is the API origin only: do not append `/api`. Netlify compiles these values into the frontend at build time, so trigger a new deploy after changing them.

## 3. Release check

1. Visit the Netlify URL and register a test account.
2. Confirm login persists after refresh; a cross-site Cookie must be `Secure` and `SameSite=None`.
3. Create a monitor, run a scan, and confirm the result appears in the product library.
4. Trigger one notification rule and confirm its detail link opens the Netlify frontend.
5. Open the operations page and confirm the API reports PostgreSQL, RQ, Redis, and both worker processes.

If the browser shows a CORS error, compare the exact browser origin with `CORS_ALLOWED_ORIGINS`; scheme, host, and port must match exactly.
