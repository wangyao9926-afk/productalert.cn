# Deployment Guide

This guide describes the current production-style Windows deployment path using PostgreSQL, Redis, FastAPI, RQ, and the notification worker.

## Process Layout

Run the app as three separate processes:

- API: serves FastAPI and static files.
- RQ scan worker: consumes scan jobs from Redis.
- Notification worker: delivers notification outbox records.

The API process should not run background loops in production. Set:

```env
START_BACKGROUND_WORKERS=false
START_NOTIFICATION_WORKER=false
QUEUE_BACKEND=rq
```

## Required Services

- PostgreSQL, with an application database and role.
- Redis, reachable from the app host.
- Python virtual environment with `requirements.txt` installed.

Local helper commands:

```powershell
.\setup-postgres-local.ps1 `
  -PsqlPath "C:\Program Files\PostgreSQL\18\bin\psql.exe" `
  -AdminPassword your-postgres-admin-password `
  -RunDeployCheck
```

## Environment File

Copy `.env.production.example` to `.env` on the target host and replace placeholders.

Minimum production values:

```env
DATABASE_URL=postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor
QUEUE_BACKEND=rq
REDIS_URL=redis://127.0.0.1:6379/0
START_BACKGROUND_WORKERS=false
START_NOTIFICATION_WORKER=false
SESSION_COOKIE_SECURE=true
```

If testing without HTTPS, set `SESSION_COOKIE_SECURE=false`. Use HTTPS before real users log in.

You can generate a local `.env` without echoing the database password:

```powershell
.\write-production-env.ps1 -DryRun -DatabasePassword "replace-with-long-random-password"
.\write-production-env.ps1 -Force
```

Without `-DatabasePassword`, the script prompts for the password with hidden input. The generated `.env` is ignored by git.

## Release Gate

Run the full production preflight after `.env` is ready:

```powershell
.\preflight-production.ps1 -EnvPath .\.env
```

Use `-SkipApi` before the API process is running. Add `-RunBackup` when you want the preflight to create and verify a real backup instead of only doing a backup dry-run. Add `-RunRestoreDrill` to restore the latest backup into a disposable database and run a database health check.

Restore-drill preflight example:

```powershell
.\preflight-production.ps1 `
  -EnvPath .\.env `
  -SkipApi `
  -RunBackup `
  -RunRestoreDrill `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -AdminPassword your-postgres-admin-password
```

Check production configuration before running release gates:

```powershell
.\check-production-config.ps1 -EnvPath .\.env
```

Run this before starting or updating production:

```powershell
.\deploy-check.ps1 `
  -Backend postgresql `
  -Queue rq `
  -DatabaseUrl postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor `
  -RedisUrl redis://127.0.0.1:6379/0
```

Expected final lines:

```text
production readiness smoke ok checks=11
Deploy check passed.
```

## Start Commands

Open three terminals from the project directory.

API:

```powershell
.\start-api-production.ps1 `
  -DatabaseUrl postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor `
  -Queue rq `
  -RedisUrl redis://127.0.0.1:6379/0
```

RQ scan worker:

```powershell
$env:DATABASE_URL='postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor'
$env:QUEUE_BACKEND='rq'
$env:REDIS_URL='redis://127.0.0.1:6379/0'
.\start-rq-worker.ps1
```

Notification worker:

```powershell
$env:DATABASE_URL='postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor'
.\start-notification-worker.ps1
```

## Health Checks

API health:

```powershell
curl http://127.0.0.1:8000/api/system/ping
```

Redis:

```powershell
.\.venv\Scripts\python.exe -m app.rq_preflight --check-redis
```

RQ smoke:

```powershell
$env:QUEUE_BACKEND='rq'
$env:REDIS_URL='redis://127.0.0.1:6379/0'
.\.venv\Scripts\python.exe -m app.rq_smoke
```

Notification worker one-shot:

```powershell
.\.venv\Scripts\python.exe -m app.notification_worker --once --limit 5
```

## HTTPS Reverse Proxy

Keep the API bound to `127.0.0.1:8000` and put an HTTPS reverse proxy in front of it. A Caddy template is provided in `Caddyfile.example`.

Before public launch:

```powershell
.\check-reverse-proxy-config.ps1 -Domain monitor.example.com
```

Replace `monitor.example.com` with your real domain. The check verifies the domain shape, `.env` cookie security, local API reachability, Caddyfile target, and whether `caddy validate` is available. Use `-SkipBackend` only when the API is not currently running or the check is being run from a context that cannot reach the local task session.

If Caddy is installed but not on `PATH`, pass its executable path:

```powershell
.\check-reverse-proxy-config.ps1 `
  -Domain monitor.example.com `
  -CaddyPath "C:\path\to\caddy.exe"
```

Public launch requirements:

- DNS A/AAAA record points the domain to this host.
- Firewall allows inbound 80 and 443.
- `SESSION_COOKIE_SECURE=true` in `.env`.
- Caddy is installed and running with a Caddyfile based on `Caddyfile.example`.

## Operational Notes

- Keep Redis and PostgreSQL running before starting API or workers.
- Restart RQ workers after code deploys.
- Run `deploy-check.ps1` after database migrations or dependency changes.
- Treat failed notification rows as recoverable; use the notification retry action after fixing webhook endpoints.
- Rotate the PostgreSQL admin password if it was shared or pasted into logs.
- Redact old log files before sharing or archiving them:

```powershell
.\redact-log-secrets.ps1
.\redact-log-secrets.ps1 -Apply
```

## Windows Scheduled Tasks

Run the pre-registration safety check first:

```powershell
.\pre-register-windows-tasks.ps1 -EnvPath .\.env
```

It validates production config, runs the release gate, verifies backup dry-run, checks scheduled task dry-runs, and prints administrator PowerShell registration commands. It does not register tasks.

Preview the scheduled task plan:

```powershell
.\install-windows-tasks.ps1 `
  -DryRun `
  -EnvPath .\.env
```

Register or update the tasks:

```powershell
.\install-windows-tasks.ps1 `
  -Register `
  -EnvPath .\.env
```

Register and start immediately:

```powershell
.\install-windows-tasks.ps1 `
  -Register `
  -StartAfterRegister `
  -EnvPath .\.env
```

By default tasks are registered with Windows Task Scheduler `Limited` run level for the current interactive user. Add `-Elevated` only when running from an administrator PowerShell and you explicitly need `RunLevel Highest`.
If registration returns `Access is denied`, open PowerShell with "Run as administrator" and rerun the same command.

Created task names:

- `ProductMonitor-API`
- `ProductMonitor-RQWorker`
- `ProductMonitor-NotificationWorker`
- `ProductMonitor-DatabaseBackup` after running `install-backup-task.ps1`

By default, the scheduled tasks write transcripts under:

```text
logs/api.log
logs/rq-worker.log
logs/notification-worker.log
```

Use `-LogDir D:\path\to\logs` on `install-windows-tasks.ps1` to put logs elsewhere.

Manage the registered tasks:

```powershell
.\manage-windows-tasks.ps1 -Action status
.\manage-windows-tasks.ps1 -Action start -DryRun
.\manage-windows-tasks.ps1 -Action stop -DryRun
.\manage-windows-tasks.ps1 -Action delete -DryRun
```

Deleting real tasks requires an explicit confirmation flag:

```powershell
.\manage-windows-tasks.ps1 -Action delete -ConfirmDelete
```

Quick troubleshooting commands:

```powershell
.\manage-windows-tasks.ps1 -Action status
Get-Content .\logs\api.log -Tail 80
Get-Content .\logs\rq-worker.log -Tail 80
Get-Content .\logs\notification-worker.log -Tail 80
```

Run a single deployment health check:

```powershell
.\health-check-production.ps1 `
  -EnvPath .\.env
```

Use `-SkipApi` before the API task has been started. Add `-Strict` when warnings such as missing logs should fail the check.

## Backups

Create a PostgreSQL custom-format backup:

```powershell
.\backup-database.ps1 `
  -DatabaseUrl postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor `
  -Verify
```

The default output directory is `backups/`, which is ignored by git. `-Verify` runs `pg_restore --list` against the dump, proving the file is readable. For restore drills, restore into a new temporary database first; do not test restore against the production database.

Run a restore drill against a disposable database:

```powershell
.\restore-drill-database.ps1 `
  -BackupPath .\backups\product-monitor-YYYYMMDD-HHMMSS.dump `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -TargetDatabaseUrl postgresql://product_monitor:replace-with-strong-password@127.0.0.1:5432/product_monitor_restore_drill_YYYYMMDD
```

The target database name must start with `product_monitor_restore_drill_`. By default the script drops the drill database after a successful check. Use `-KeepDatabase` only when you need to inspect the restored data manually.

Install a daily backup task:

```powershell
.\install-backup-task.ps1 `
  -DryRun `
  -EnvPath .\.env `
  -KeepLast 14 `
  -At 03:20
```

Register it after reviewing the dry-run output:

```powershell
.\install-backup-task.ps1 `
  -Register `
  -EnvPath .\.env `
  -KeepLast 14 `
  -At 03:20
```

The backup task also defaults to `Limited`. Add `-Elevated` only from an administrator PowerShell.
If registration returns `Access is denied`, rerun from an administrator PowerShell.

The backup task calls `run-scheduled-backup.ps1`, verifies each dump with `pg_restore --list`, and keeps the newest `KeepLast` dump files.

## Credential Rotation

Rotate the PostgreSQL application role password before production use. Preview first:

```powershell
.\rotate-postgres-app-password.ps1 `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -NewPassword "replace-with-a-long-random-password"
```

Apply and run the PostgreSQL + Redis release gate:

```powershell
.\rotate-postgres-app-password.ps1 `
  -Apply `
  -RunDeployCheck `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -AdminPassword your-postgres-admin-password `
  -NewPassword "replace-with-a-long-random-password" `
  -RedisUrl redis://127.0.0.1:6379/0
```

After rotation, update planned task commands, backup task command, and any reverse-proxy/service configuration from `.env`. Rotation output redacts the password by design.

Recommended no-password-in-command flow:

1. Generate or update `.env` with the final application password:

```powershell
.\write-production-env.ps1 -Force
```

2. Preview the rotation:

```powershell
.\rotate-postgres-password-from-env.ps1 -EnvPath .\.env
```

3. Apply and verify:

```powershell
.\rotate-postgres-password-from-env.ps1 `
  -Apply `
  -RunDeployCheck `
  -EnvPath .\.env `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -AdminPassword your-postgres-admin-password `
  -RedisUrl redis://127.0.0.1:6379/0
```

This reads the new application password from `.env` instead of placing it in command history. The terminal output redacts the password.

Manual equivalent:

1. Put the final `DATABASE_URL` with the new application password in `.env`.
2. Preview the rotation:

```powershell
.\rotate-postgres-password-from-env.ps1 -EnvPath .\.env
```

3. Apply and verify:

```powershell
.\rotate-postgres-password-from-env.ps1 `
  -Apply `
  -RunDeployCheck `
  -EnvPath .\.env `
  -AdminDatabaseUrl postgresql://postgres@127.0.0.1:5432/postgres `
  -AdminPassword your-postgres-admin-password `
  -RedisUrl redis://127.0.0.1:6379/0
```

This reads the new application password from `.env` instead of placing it in command history. The terminal output redacts the password.

After installing the backup task, `manage-windows-tasks.ps1` and `health-check-production.ps1` include `ProductMonitor-DatabaseBackup` in their task status checks.
