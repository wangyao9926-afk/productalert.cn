# Notification Evidence Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include an authenticated change-detail URL in every event notification when the deployed public application URL is configured.

**Architecture:** `app/settings.py` exposes `public_app_url()`, normalizing `APP_PUBLIC_URL`. `app/notifier.py` composes the optional `/changes/{event_id}` path in `change_event_payload` and includes it both in the rendered text and JSON payload. No new database column or public evidence route is required.

**Tech Stack:** Python, existing dotenv settings, FastAPI event links, unittest.

## Global Constraints

- Only use an absolute URL supplied through `APP_PUBLIC_URL`.
- Never emit a localhost fallback when the value is unset.
- The generated route relies on existing authenticated ownership checks.

---

### Task 1: Compose a normalized, optional evidence URL

**Files:**
- Modify: `app/settings.py`
- Modify: `app/notifier.py`
- Create: `test_notification_evidence_links.py`

**Interfaces:**
- `public_app_url() -> str | None`
- `change_event_payload(event, product=None) -> dict`

- [x] **Step 1: Write failing tests**

```python
with patch.dict(os.environ, {"APP_PUBLIC_URL": "https://app.example.com/"}):
    payload = change_event_payload({"id": 42, "change_type": "price_change", "summary": "Price changed"})
self.assertEqual(payload["evidence_url"], "https://app.example.com/changes/42")
self.assertIn("https://app.example.com/changes/42", payload["text"]["content"])
```

Also assert an unset `APP_PUBLIC_URL` leaves `evidence_url` absent.

- [x] **Step 2: Run the focused test and verify it fails because the payload lacks `evidence_url`**

Run: `..\\..\\.venv\\Scripts\\python.exe -m unittest test_notification_evidence_links -v`

- [x] **Step 3: Add URL normalization and payload composition**

```python
base_url = public_app_url()
evidence_url = f"{base_url}/changes/{event_id}" if base_url and event_id else None
```

- [x] **Step 4: Re-run focused tests and the notification delivery tests**

### Task 2: Verify the production path and publish the preview

**Files:**
- Modify: `docs/superpowers/plans/2026-08-03-notification-evidence-link.md`

- [x] **Step 1: Run full backend tests, API smoke, frontend build, and UI contract test**

```powershell
..\\..\\.venv\\Scripts\\python.exe -m unittest discover -q
$env:START_BACKGROUND_WORKERS='false'; ..\\..\\.venv\\Scripts\\python.exe -m app.api_smoke
Set-Location frontend; npm.cmd run build; npm.cmd run test:ui-contract
```

- [x] **Step 2: Restart the local preview services and verify `/api/system/ping` and `/notifications` return HTTP 200**

- [x] **Step 3: Commit and push the implementation**
