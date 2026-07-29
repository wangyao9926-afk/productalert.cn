# macOS Console UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the existing static frontend into a macOS-style operations console for the first production UI phase.

**Architecture:** Keep the current FastAPI and vanilla static frontend. Rework `static/index.html`, `static/styles.css`, and `static/app.js` around a macOS control-console layout, while preserving existing API calls and workflows. No backend, database, auth, or crawler behavior changes belong in this phase.

**Tech Stack:** FastAPI static files, vanilla HTML, CSS, JavaScript.

**Confirmed UI Baseline:** Use the user-approved preview version: light macOS console, left text navigation, command panel for URL monitoring, four compact metric cards, table-first product library, and right-side timeline/site rail. Do not switch to the alternate dark icon-only macOS window concept unless explicitly requested.

## Global Constraints

- Keep vanilla JS.
- Do not add package dependencies.
- Reuse existing API endpoints.
- Main visual direction is A: macOS console style.
- Do not implement scheduler, auth hardening, proxy pool, or crawler behavior in this phase.
- Do not break register/login, add site, scan, source edit/delete/toggle, notification retry, CSV export.
- Replace normal `alert()` and `confirm()` UI flows with toast and modal.
- Desktop table-first layout is primary.

---

## File Structure

- Modify `static/index.html`: shell landmarks, nav labels, toast root, modal root, product card template retained for optional card mode.
- Modify `static/styles.css`: replace current visual system with macOS console tokens, shell, panels, tables, forms, tabs, toast, modal, drawer-ready styles.
- Modify `static/app.js`: add toast/modal helpers, loading state, log sub-tabs, product table rendering, updated nav labels and view rendering.
- Modify `test_static_advanced_toggle.py`: keep advanced toggle coverage if selectors still apply.
- Modify `test_static_monitor_settings_ui.py`: update expected UI markers if text or classes change.

## Task 1: macOS Visual System and Shell

**Files:**
- Modify: `static/index.html`
- Modify: `static/styles.css`

**Interfaces:**
- Produces CSS classes consumed by JS renderers: `.app-shell`, `.side-rail`, `.workspace`, `.command-panel`, `.health-strip`, `.result-panel`, `.data-table`, `.toast-stack`, `.modal-layer`.

- [ ] Update `static/index.html` shell labels to: `监控概览`, `产品库`, `采集源`, `通知中心`.
- [ ] Add `<div id="toast-stack" class="toast-stack" aria-live="polite"></div>` near the end of body.
- [ ] Add `<div id="modal-root"></div>` near the end of body.
- [ ] Replace old glass-heavy CSS tokens in `static/styles.css` with `DESIGN.md` macOS console variables.
- [ ] Verify the app still loads at `http://127.0.0.1:8000`.

## Task 2: Toast, Confirm Modal, and Loading Feedback

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Produces `showToast({ type, title, message })`.
- Produces `confirmAction({ title, message, confirmText, danger }) -> Promise<boolean>`.
- Consumes existing API errors through `formatApiError()`.

- [ ] Add `showToast()` helper.
- [ ] Add `confirmAction()` helper.
- [ ] Replace add-site success/failure `alert()` calls with toast.
- [ ] Replace export/retry/save error `alert()` calls with toast.
- [ ] Replace delete site/source `confirm()` calls with `confirmAction()`.
- [ ] Add CSS for `.toast-stack`, `.toast`, `.modal-backdrop`, `.modal-card`.
- [ ] Verify no normal flow still uses `alert(` or `confirm(` in `static/app.js`.

## Task 3: Product Library Table-First View

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Produces `renderProductsTable(products)`.
- Reuses existing `productResults()`, `confidenceBadge()`, `productPriceText()`, `availabilityLabel()`, `updateInboxStatus()`.

- [ ] Add a compact product toolbar with filters and CSV export.
- [ ] Render desktop product library as a table with columns: 产品, 官网/来源, 价格, 库存, 发现类型, 置信度, 处理状态, 发现时间, 操作.
- [ ] Keep product card template available but do not use as default desktop view.
- [ ] Add row actions for product URL and inbox status.
- [ ] Add mobile fallback list below 820px.
- [ ] Update empty state with current source count, latest scan count, and next action.

## Task 4: Logs View Sub Tabs

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Produces `state.logTab`.
- Produces `renderLogsTabs()`.
- Produces `renderScanJobsPanel()`, `renderChangeEventsPanel()`, `renderNotificationsPanel()`, `renderAuditLogsPanel()`.
- Reuses existing state arrays: `jobs`, `changes`, `notifications`, `auditLogs`, `logs`.

- [ ] Add `state.logTab = "jobs"`.
- [ ] Replace the long mixed logs view with four tabs: 扫描作业, 变化事件, 通知投递, 操作审计.
- [ ] Keep retry notification functionality in the notification tab.
- [ ] Show empty states per tab.
- [ ] Use table/list rows with status badges.

## Task 5: Validation

**Files:**
- Modify tests only if static selectors changed.

**Interfaces:**
- Consumes local app at `http://127.0.0.1:8000`.

- [ ] Run `.\.venv\Scripts\python.exe -m app.api_smoke`.
- [ ] Run `.\.venv\Scripts\python.exe test_static_advanced_toggle.py`.
- [ ] Run `.\.venv\Scripts\python.exe test_static_monitor_settings_ui.py`.
- [ ] Open the app in the in-app browser.
- [ ] Verify register/login, empty product view, source view, logs tabs, toast, delete modal.
