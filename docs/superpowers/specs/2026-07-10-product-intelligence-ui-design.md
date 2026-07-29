# Product Intelligence Monitoring UI Design

Date: 2026-07-10
Status: Draft for user review; implementation pending spec approval

## 1. Product intent

The application is an online B2B workspace for operations and competitive-research users. It monitors public brand websites for new products, price changes, availability changes, product-information changes, promotions, and collection failures. The primary user task is reviewing trustworthy change events with evidence, not browsing raw crawler logs.

## 2. Visual direction

Use the existing macOS Operations Console direction: light neutral background, white work surfaces, a compact dark navigation rail, restrained blue primary actions, dense tables, and right-side evidence drawers. The tone is precise, calm, and operational. Do not introduce a marketing hero, large decorative gradients, or a glass-heavy dashboard.

Interaction tier is L1: subtle entrance, hover, focus, drawer, toast, and state transitions. All motion has a reduced-motion path.

## 3. Application shell

Desktop shell:

- fixed left navigation at 232–248px;
- top command bar with workspace, search, new monitor, notifications, and account;
- fluid workspace with 18–24px padding;
- optional 320–360px operational rail;
- drawers for product, change, and scan evidence.

Mobile shell:

- sticky top navigation;
- collapsed navigation drawer;
- stacked command bar;
- card rows replacing dense tables;
- filters in a drawer;
- 44px minimum touch targets.

## 4. Navigation and routes

Primary navigation:

```text
总览 /overview
监控中心 /monitors
情报收件箱 /inbox
产品库 /products
报告与趋势 /reports
运维中心 /operations
设置 /settings
```

Secondary routes:

```text
/monitors/new
/monitors/:id
/products/:id
/settings/team
/settings/notifications
/settings/api
```

`新建监控` is the primary global action. The inbox is the only navigation item with a dynamic unread badge.

## 5. Screen hierarchy

### Overview

Health strip, pending intelligence, recent timeline, monitor health, and active jobs. The first viewport must answer: are monitors healthy, what changed, what failed, and what should I handle next?

### Monitor center

Table-first monitor list with brand, URL, target types, cadence, freshness, status, and actions. The detail view combines source settings, rules, health, scan history, and discovered products.

### Intelligence inbox

Unified event list for new products, price, availability, product information, images, promotions, removals, and collection errors. Use filters for brand, type, time, severity, confidence, and workflow state. Open the evidence drawer from any row.

### Product library

Dense table by default, optional cards. Product detail shows canonical fields, price and availability history, images, provenance, confidence, and change timeline.

### Reports and trends

Operational reporting for launches, price movements, stock movements, brand timelines, coverage, freshness, and collection quality. Exports show scope before execution.

### Operations

Queued, running, failed, and retried scans; notification delivery; source health; freshness; and error categories. Failures are traceable to source, URL, time, category, and retry state.

### Settings

Workspace, members, notification channels, notification rules, API tokens, retention, security, and audit.

## 6. Monitor wizard

Four steps:

1. Brand and public website: name, URL, region, category, priority, notes, and automatic discovery of sitemap/RSS/listing/product sources.
2. Monitoring targets: new products, prices, availability, product information, images, promotions, or selected area.
3. Conditions and notifications: cadence, timezone, keyword rules, price thresholds, selector, ignored dynamic regions, review policy, and destinations.
4. Test and baseline: discovered pages/products/fields, sample records, failures, coverage, risks, and explicit baseline confirmation.

## 7. Evidence drawer

The drawer shows event type, severity, product, source, old/new values, delta, detection time, confidence, text diff, screenshot diff, provenance, scan job, and review actions. Closing restores focus to the source row.

## 8. Component system

Core primitives:

```text
AppShell, Sidebar, TopBar, WorkspaceSwitcher, PageHeader,
MetricCard, HealthCard, DataTable, FilterBar, StatusBadge,
ConfidenceBadge, ChangeTypeBadge, Drawer, Modal, Toast,
EmptyState, Skeleton, MonitorWizard, ChangeDiff, Timeline,
PriceHistoryChart, ErrorDetails
```

Each component defines default, hover, active, focus-visible, disabled, loading, empty, and error states when relevant. Use CSS variables from `DESIGN.md`; do not scatter hard-coded colors in feature code.

## 9. Frontend implementation boundary

Use React + Vite + TypeScript for the frontend. Keep FastAPI as the API and deployment boundary. The migration is incremental: reproduce current API-backed flows first, then add inbox, evidence, history, and wizard surfaces. Do not rewrite backend business behavior during the shell pass.

## 10. Acceptance criteria

- A new user can start a monitor from the global action and reach a tested baseline through the four-step wizard.
- A price-change row shows old value, new value, delta, confidence, and evidence.
- A product-information row shows field-level diff and source context.
- A failed scan shows source, URL, timestamp, error category, retry state, and next action.
- Inbox filters preserve context and open a drawer without losing list position.
- Empty, loading, partial, failed, low-confidence, and reduced-motion states are designed.
- Desktop and mobile layouts have no horizontal overflow and maintain accessible focus states.
