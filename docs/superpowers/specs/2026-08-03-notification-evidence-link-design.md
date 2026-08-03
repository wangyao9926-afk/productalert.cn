# Notification Evidence Link Design

## Goal

Every product-change notification provides a direct link to the authenticated change-detail view so an operator can review the saved field diff, page snapshot metadata, and screenshot evidence immediately.

## Scope

- Add `APP_PUBLIC_URL` as an optional server configuration value.
- Build a deterministic detail link as `{APP_PUBLIC_URL}/changes/{event_id}`.
- Include the link in the human-readable text payload and structured payload as `evidence_url`.
- Preserve the existing product/source URL as the external reference.
- Do not expose a public screenshot path, create a signed URL, or bypass application authentication.

## Behavior

- When `APP_PUBLIC_URL` is set to `https://app.example.com/`, the event id `42` produces `https://app.example.com/changes/42`.
- Trailing slashes are removed before composing the path.
- When the variable is unset, notifications retain their existing content and omit `evidence_url`; no invalid localhost link is sent to production recipients.
- The existing `/changes/{event_id}` route continues to enforce the logged-in user's ownership checks before displaying any evidence.

## Files and Responsibilities

- `app/settings.py`: read and normalize the optional public application URL.
- `app/notifier.py`: build an event evidence URL and include it in `change_event_payload`.
- `test_notification_evidence_links.py`: verify configured, trailing-slash, and unset behavior.

## Acceptance Criteria

1. A configured public URL appears both in the outgoing text and structured payload.
2. No `evidence_url` is emitted when no public URL is configured.
3. Existing webhook payload, notification outbox, and authentication behavior remain unchanged.
