# Source Event Suppression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator suppress future events of one type from one monitored source after confirming an event is noise.

**Architecture:** Add a source-scoped suppression-rule table with ownership derived from its site. Event creation will consult it before inserting an event or notification. The change-detail page will provide an explicit “ignore same-source events” action; it never suppresses a rule automatically when an event is merely marked false positive.

**Tech Stack:** FastAPI, SQLite/PostgreSQL migrations, existing database helpers, React/TypeScript, unittest.

## Global Constraints

- Rules are scoped to one source and one `change_type`, never globally across a user's sites.
- A rule is only created through explicit operator action from an owned change event.
- Suppressed events produce no inbox record or notification; product and snapshot storage still continues.
- Existing `price_change`, `availability_change`, `product_new`, and variant event flows must remain covered by regression tests.

---

### Task 1: Persist source-scoped rules and expose an owned-event API

**Files:**
- Create: `app/migrations/sqlite/006_source_event_suppression.sql`
- Create: `app/migrations/postgresql/006_source_event_suppression.sql`
- Modify: `app/main.py`
- Test: `test_event_suppression.py`

**Interfaces:**
- Produces `POST /api/change-events/{event_id}/suppress-similar` accepting `{"reason": "..."}`.
- Produces `GET /api/event-suppression-rules` returning rules owned through `sites.user_id`.

- [x] **Step 1: Write failing API ownership and persistence tests**

```python
response = owner.post(f"/api/change-events/{event_id}/suppress-similar", json={"reason": "Rotating banner"})
self.assertEqual(response.status_code, 200)
self.assertEqual(response.json()["change_type"], "text_change")
self.assertEqual(stranger.post(f"/api/change-events/{event_id}/suppress-similar", json={}).status_code, 404)
```

- [x] **Step 2: Run the focused test and verify it fails because the endpoint is missing**

Run: `..\\..\\.venv\\Scripts\\python.exe -m unittest test_event_suppression.EventSuppressionApiTests -v`

- [x] **Step 3: Add migrations, request model, and owner-scoped create/list endpoints**

```python
class EventSuppressionCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
```

Use a unique `(source_id, change_type)` rule and return the existing rule on repeat requests.

- [x] **Step 4: Re-run the focused API test and verify it passes**

### Task 2: Prevent future matching events from entering the inbox or notification outbox

**Files:**
- Modify: `app/monitor.py`
- Test: `test_event_suppression.py`

**Interfaces:**
- `insert_product_change_event(...) -> int | None` returns `None` when an enabled rule exists for the provided source and change type.

- [x] **Step 1: Write a failing test that inserts a text-change rule, performs a changed snapshot, and expects zero change events**

```python
result = await capture_source_snapshot(source, baseline_mode=False, notify=True)
self.assertTrue(result["changed"])
self.assertTrue(result["suppressed"])
self.assertEqual(count_rows("change_events", source_id), 0)
```

- [x] **Step 2: Run the focused test and verify it fails because a matching event is still inserted**

Run: `..\\..\\.venv\\Scripts\\python.exe -m unittest test_event_suppression.EventSuppressionRuntimeTests -v`

- [x] **Step 3: Make the shared event inserter consult `event_suppression_rules`, then guard notification enqueue calls when no event id is returned**

```python
if is_event_suppressed(db, source_id, change_type):
    return None
```

Route source snapshot changes through the shared inserter so text and visual events use identical suppression behavior.

- [x] **Step 4: Re-run the focused runtime test and the existing variant tests**

### Task 3: Give operators an explicit feedback control in change detail

**Files:**
- Modify: `frontend/src/api/changes.ts`
- Modify: `frontend/src/features/changes/ChangeDetailPage.tsx`
- Modify: `test_product_variants_ui.py`

**Interfaces:**
- `suppressSimilarChangeEvents(eventId, reason)` posts to the new owned-event endpoint.

- [x] **Step 1: Write a failing UI contract test for the API call and the “忽略此来源同类变化” action**

```python
self.assertIn("suppressSimilarChangeEvents", api_source)
self.assertIn("忽略此来源同类变化", page_source)
```

- [x] **Step 2: Run the UI contract test and verify it fails because the action is absent**

- [x] **Step 3: Add the explicit action with loading, success, and error states**

The action must call the API only for real event detail data and must not change the current event's review status.

- [x] **Step 4: Run full backend tests, API smoke, frontend build, UI contract test, and restart the preview services**

Run:

```powershell
..\\..\\.venv\\Scripts\\python.exe -m unittest discover -q
$env:START_BACKGROUND_WORKERS='false'; ..\\..\\.venv\\Scripts\\python.exe -m app.api_smoke
Set-Location frontend; npm.cmd run build; npm.cmd run test:ui-contract
```
