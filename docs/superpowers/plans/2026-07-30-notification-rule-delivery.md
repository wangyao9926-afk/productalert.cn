# Notification Rule Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make saved Webhook, 企业微信, and 飞书 notification rules create real outbox jobs for matching product-change events.

**Architecture:** The existing event enqueue function will query enabled rules owned by the matching site, evaluate event type and minimum severity, and insert one outbox job per rule. The existing site-level webhook remains a backwards-compatible fallback only when no rule matches. The existing sender sends the compatible `msgtype: text` payload used by all three webhook channels.

**Tech Stack:** FastAPI, SQLite/PostgreSQL-compatible queries, httpx, React/TypeScript, unittest.

## Global Constraints

- Rule matching is limited to the current event's site or an all-sites rule owned by that site owner.
- Webhook, `wecom`, and `feishu` target URLs must be public HTTP(S) URLs; email remains unsupported by the delivery worker.
- Matching a rule produces one outbox row carrying that rule's channel and target URL.
- Site-level `webhook_url` compatibility remains when no enabled rule matches.

---

### Task 1: Match persisted notification rules during event creation

**Files:**
- Modify: `app/monitor.py`
- Test: `test_notification_rules_delivery.py`

**Interfaces:**
- `enqueue_event_notification_if_enabled(...)` writes matching rule jobs before considering the legacy site webhook.

- [x] **Step 1: Write a failing test with a `wecom` rule for a high-severity `price_change` event**

```python
enqueue_event_notification_if_enabled(db, site, event_id=event_id, event_type="price_change", product_id=None, event={"severity": "high"}, product=None)
self.assertEqual(outbox["channel"], "wecom")
self.assertEqual(outbox["target_url"], rule_url)
```

- [x] **Step 2: Run the focused test and verify it fails because no rule outbox row is created**

Run: `..\\..\\.venv\\Scripts\\python.exe -m unittest test_notification_rules_delivery -v`

- [x] **Step 3: Query enabled owner rules, filter by site/event/severity, and enqueue matching jobs**

- [x] **Step 4: Re-run the focused test and verify it passes**

### Task 2: Validate robot-channel rule creation and expose the rule composer

**Files:**
- Modify: `app/main.py`
- Modify: `frontend/src/api/notifications.ts`
- Modify: `frontend/src/features/notifications/NotificationsPage.tsx`
- Test: `test_notification_rules_delivery.py`
- Test: `test_notification_rules_ui.py`

**Interfaces:**
- `POST /api/notification-rules` rejects email delivery and validates robot webhook URLs.
- `createNotificationRule(payload)` creates webhook, 飞书, or 企业微信 rule from the notification page.

- [x] **Step 1: Write failing API and UI contract tests**

```python
self.assertEqual(client.post("/api/notification-rules", json={"name": "Mail", "channel": "email", ...}).status_code, 400)
self.assertIn("createNotificationRule", api_source)
self.assertIn("新建推送规则", page_source)
```

- [x] **Step 2: Run tests and verify missing validation/composer failures**

- [x] **Step 3: Add validation and a compact rule composer for supported robot channels**

- [x] **Step 4: Run full backend/API/frontend verification and restart preview services**
