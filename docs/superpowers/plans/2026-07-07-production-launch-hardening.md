# Production Launch Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the product launch monitor from a local prototype to a safe small-scale production service for real users.

**Architecture:** Keep the current FastAPI + PostgreSQL + Redis/RQ + static frontend architecture. Harden the existing path before adding larger infrastructure: reliable job recovery, cookie-only auth, Redis-backed rate limits, crawl diagnostics, and operational gates.

**Tech Stack:** FastAPI, PostgreSQL, Redis, RQ, httpx, Playwright, vanilla JavaScript, PowerShell deployment scripts.

## Global Constraints

- PostgreSQL is the production database; SQLite is allowed only for local demo and tests.
- Redis/RQ is the production scan queue; API must not run scan loops in production.
- Public user login must use HTTPS and HttpOnly Secure SameSite cookies.
- All user-provided crawl and webhook URLs must pass SSRF checks before request dispatch.
- Every task must include a focused automated test or a reproducible smoke check.
- Do not implement CAPTCHA bypass as a default feature; only support authorized crawling and compliant rate limits.

---

### Task 1: Queue/DB Reconciliation

**Files:**
- Modify: `app/task_queue.py`
- Modify: `app/monitor.py`
- Create: `app/job_reaper.py`
- Create: `test_job_reaper.py`

**Interfaces:**
- Produces: `mark_stale_scan_jobs_failed(max_age_minutes: int) -> int`
- Produces: `requeue_stale_scan_jobs(max_age_minutes: int) -> int`

- [ ] Add `external_job_id`, `heartbeat_at`, and `attempts` fields to scan job migrations.
- [ ] Store the RQ job id returned by `Queue.enqueue`.
- [ ] Update workers to refresh `heartbeat_at` while running or at task boundaries.
- [ ] Add a reaper that marks jobs stale when `queued/running` exceeds the configured timeout.
- [ ] Add tests covering queued job timeout, running job timeout, and no-op for fresh jobs.
- [ ] Add a health-check output field for stale scan job count.

### Task 2: Cookie-Only Authentication

**Files:**
- Modify: `app/auth.py`
- Modify: `app/main.py`
- Modify: `static/app.js`
- Create: `test_cookie_auth.py`

**Interfaces:**
- Produces: login/register responses with `user` and `expires_at`, but no raw token in JSON.
- Consumes: `monitor_session` HttpOnly cookie for authenticated requests.

- [ ] Remove bearer token from login/register JSON in production mode.
- [ ] Remove frontend `state.token` Authorization header usage.
- [ ] Keep cookie-based `credentials: "same-origin"` requests.
- [ ] Add CSRF token for mutating routes, or SameSite Strict plus origin checks for the first production launch.
- [ ] Add tests confirming session token is hashed in DB and not returned in response body.

### Task 3: Redis-Backed Abuse Limits

**Files:**
- Modify: `app/auth.py`
- Create: `app/rate_limit.py`
- Modify: `app/main.py`
- Create: `test_rate_limit_redis.py`

**Interfaces:**
- Produces: `check_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None`

- [ ] Move login failure limit from process memory to Redis.
- [ ] Add limits for register, login, add site, add source, manual scan, notification retry.
- [ ] Return 429 with a clear retry message.
- [ ] Add fallback behavior that fails closed for auth routes if Redis is unavailable in production.

### Task 4: SSRF Final-Connection Hardening

**Files:**
- Modify: `app/url_safety.py`
- Modify: `app/crawler.py`
- Modify: `app/notifier.py`
- Create: `test_url_safety_network.py`

**Interfaces:**
- Produces: `validate_public_http_url(url: str) -> str`
- Produces: redirect validation and final target validation for every outbound request.

- [ ] Keep scheme, port, hostname, DNS, private IP, loopback, link-local, and redirect checks.
- [ ] Add max redirect count.
- [ ] Add response size limit.
- [ ] Add content type allowlist for HTML/XML/JSON/text where applicable.
- [ ] Add tests for 127.0.0.1, localhost, private IP, metadata IP, blocked port, and redirect-to-private.

### Task 5: Crawl Diagnostics and Product Quality

**Files:**
- Modify: `app/crawler.py`
- Modify: `app/monitor.py`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Create: `test_scan_diagnostics.py`

**Interfaces:**
- Produces: per scan result fields `candidate_count`, `accepted_count`, `rejected_count`, `render_used`, `failure_reason`.

- [ ] Store why candidates were rejected: duplicate, off-domain, low relevance, low confidence, request failed, render failed.
- [ ] Display scan diagnostics in the UI when product count is 0.
- [ ] Show baseline products separately from new products.
- [ ] Add field-level confidence display for title, price, image, description, availability.

### Task 6: Notification Delivery Hardening

**Files:**
- Modify: `app/notifier.py`
- Modify: `app/main.py`
- Modify: `static/app.js`
- Create: `test_notification_delivery.py`

**Interfaces:**
- Produces: `delivery_id`, `signature`, `attempts`, `next_attempt_at`, `last_error`.

- [ ] Add HMAC signature for outbound webhooks.
- [ ] Add delivery id for idempotency.
- [ ] Surface pending/sending/sent/failed states in notification UI.
- [ ] Keep manual retry and show retry result.
- [ ] Add tests for successful send, retryable failure, final failure, and manual retry.

### Task 7: Production Observability

**Files:**
- Modify: `app/main.py`
- Modify: `app/monitor.py`
- Create: `app/metrics.py`
- Modify: `health-check-production.ps1`
- Create: `test_metrics.py`

**Interfaces:**
- Produces: `/api/system/health` with database, redis, worker, stale jobs, and notification backlog.

- [ ] Add `trace_id` to each scan job and log entry.
- [ ] Emit structured scan logs with domain, source_type, duration, candidate_count, product_count, error_type.
- [ ] Add health endpoint for deployment checks.
- [ ] Update production health script to fail if Redis, DB, API, or workers are unhealthy.

### Task 8: Production Deployment Gate

**Files:**
- Modify: `DEPLOYMENT.md`
- Modify: `.env.production.example`
- Modify: `preflight-production.ps1`
- Modify: `deploy-check.ps1`

**Interfaces:**
- Produces: one command that proves production readiness before launch.

- [ ] Require `SESSION_COOKIE_SECURE=true`.
- [ ] Require PostgreSQL backend and RQ backend.
- [ ] Require Redis reachable.
- [ ] Require backup dry-run and optional restore drill.
- [ ] Require Caddy config validation before public HTTPS launch.
- [ ] Document exact launch checklist for Alibaba Cloud or any VPS.

### Task 9: UI Scale and Operations

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Create: `test_static_operations_ui.py`

**Interfaces:**
- Produces: product list filters, task diagnostics, source editing feedback, and stable save state.

- [ ] Add table mode for product library with fixed header.
- [ ] Add filters for site, source, confidence, status, and date.
- [ ] Add visible loading and disabled states during saves.
- [ ] Add toast system for save success/failure.
- [ ] Add aria states for active tabs, toggles, and pressed buttons.

### Task 10: Final Launch Smoke

**Files:**
- Modify: `app/api_smoke.py`
- Modify: `DEPLOYMENT.md`

**Interfaces:**
- Produces: repeatable launch acceptance test.

- [ ] Register user.
- [ ] Login through cookie-only session.
- [ ] Add site.
- [ ] Add source.
- [ ] Run scan through RQ.
- [ ] Confirm products or diagnostics are visible.
- [ ] Trigger notification outbox.
- [ ] Retry failed notification.
- [ ] Export CSV.
- [ ] Verify audit logs.

