# Frontend Shell And Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable React/Vite/TypeScript frontend slice with the approved macOS operations-console shell and a data-backed overview screen.

**Architecture:** Keep FastAPI as the API and deployment boundary. Add a separate `frontend/` source tree that builds to `static/dist`, with typed API access and feature-scoped React components. The first slice uses the existing endpoints for current sites, products, change events, scan logs, jobs, notifications, and health; later slices add new endpoints without changing the shell contract.

**Tech Stack:** React 19, Vite, TypeScript, React Router, CSS variables and semantic CSS. Avoid a large component framework; use the approved design tokens and focused reusable primitives.

## Global Constraints

- Keep the macOS Operations Console direction: light neutral background, white work surfaces, compact dark navigation rail, restrained blue actions, dense tables, and right-side drawers.
- Do not rewrite backend business behavior during the frontend shell pass.
- Use `/overview`, `/monitors`, `/inbox`, `/products`, `/reports`, `/operations`, and `/settings` route contracts.
- The global action is `新建监控`; the inbox is the only navigation item with a dynamic unread badge.
- Every interactive component needs keyboard focus-visible styling and explicit loading, empty, and error states where applicable.
- Mobile layout must avoid horizontal overflow and keep touch targets at least 44px.
- New colors must use CSS variables from `DESIGN.md`; do not scatter hard-coded colors in feature code.
- A live preview must be provided after the overview slice is built; preview tooling or dependency installation must not be bypassed when permission is required.

---

### Task 1: Scaffold the frontend workspace

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/routes.tsx`

**Interfaces:**
- Produces a Vite build at `frontend/dist` that later deployment work can copy or serve from `static/dist`.
- Exposes route components for `/overview`, `/monitors`, `/inbox`, `/products`, `/reports`, `/operations`, and `/settings`.

- [ ] **Step 1: Create package metadata and TypeScript/Vite configuration**

Use React 19, Vite, TypeScript, `react-router-dom`, and `lucide-react`. Keep scripts limited to `dev`, `build`, and `preview`.

- [ ] **Step 2: Add the application entry and route shell**

Create `main.tsx` with `React.StrictMode` and `BrowserRouter`; create `routes.tsx` with temporary route state pages that render the shared page header and an explicit `未完成` state until each feature receives its own implementation plan.

- [ ] **Step 3: Run the build**

Run from `frontend/`:

```powershell
npm.cmd run build
```

Expected: Vite produces `frontend/dist` with no TypeScript errors.

### Task 2: Implement design tokens and global shell styles

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/global.css`
- Create: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/TopBar.tsx`
- Create: `frontend/src/components/layout/WorkspaceSwitcher.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- `AppShell({ children }: { children: React.ReactNode })` owns the page grid and navigation state.
- `Sidebar({ unreadCount, currentPath }: { unreadCount: number; currentPath: string })` renders the seven approved navigation entries.
- `TopBar({ onCreateMonitor }: { onCreateMonitor: () => void })` renders workspace, search, create-monitor, notification, and account controls.

- [ ] **Step 1: Write shell rendering tests**

Add a lightweight DOM test setup only if the project already has a test runner; otherwise use a build-time smoke check and a static accessibility assertion script. Assert that the seven navigation labels and `新建监控` are present in the rendered shell.

- [ ] **Step 2: Implement tokens and responsive shell CSS**

Port the approved variables from `DESIGN.md`, including navigation, surface, border, text, semantic, shadow, and spacing tokens. Add desktop, tablet, and mobile breakpoints without using global `overflow: hidden`.

- [ ] **Step 3: Implement the shell components**

Use lucide icons, semantic buttons/links, `aria-current`, `aria-label`, and a collapsible mobile navigation. Keep the shell independent from feature data except for the unread count and active route.

- [ ] **Step 4: Run build and static assertions**

Run:

```powershell
npm.cmd run build
```

Expected: the shell compiles and all navigation labels remain in the generated bundle.

### Task 3: Add typed API access for the existing overview data

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/overview.ts`
- Create: `frontend/src/types/api.ts`
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- `apiRequest<T>(path: string, options?: RequestInit): Promise<T>` adds JSON headers, parses API errors, and preserves credentials.
- `loadOverview(): Promise<OverviewData>` loads `/api/system/health`, `/api/sites`, `/api/products`, `/api/change-events`, `/api/scan-logs`, `/api/scan-jobs`, and `/api/notifications` with bounded concurrency.
- `OverviewData` contains `health`, `sites`, `products`, `changes`, `scanLogs`, `scanJobs`, and `notifications`.

- [ ] **Step 1: Define response types from current FastAPI payloads**

Model nullable timestamps, status strings, confidence values, and current JSON fields explicitly. Do not use `any` for feature data.

- [ ] **Step 2: Implement API client and error mapping**

Return a readable error with HTTP status and API `detail`. Treat 401 as an authentication state that the shell can redirect to the existing auth surface later.

- [ ] **Step 3: Implement overview loader**

Use `Promise.all` for the independent reads, but return partial data with an error list when one non-health endpoint fails so the overview can show partial state.

- [ ] **Step 4: Run build**

Run `npm.cmd run build`; expected: no implicit `any` or TypeScript errors.

### Task 4: Build the overview screen

**Files:**
- Create: `frontend/src/features/overview/OverviewPage.tsx`
- Create: `frontend/src/features/overview/HealthStrip.tsx`
- Create: `frontend/src/features/overview/PendingIntelligence.tsx`
- Create: `frontend/src/features/overview/RecentChanges.tsx`
- Create: `frontend/src/features/overview/MonitorHealthRail.tsx`
- Create: `frontend/src/components/data/MetricCard.tsx`
- Create: `frontend/src/components/data/StatusBadge.tsx`
- Create: `frontend/src/components/data/ConfidenceBadge.tsx`
- Create: `frontend/src/components/feedback/EmptyState.tsx`
- Create: `frontend/src/components/feedback/Skeleton.tsx`
- Create: `frontend/src/components/feedback/Toast.tsx`

**Interfaces:**
- `OverviewPage` consumes `loadOverview()` and renders loading, partial, empty, and error states.
- `HealthStrip` receives derived counts and status labels.
- `PendingIntelligence` receives change events and products and exposes an `onOpenEvent(id)` callback.
- `MonitorHealthRail` receives sites and scan jobs and links to `/monitors`.

- [ ] **Step 1: Add data derivation helpers**

Derive active monitors, failed sources, pending review count, new products, unread changes, and active jobs without mutating API data.

- [ ] **Step 2: Implement the health strip**

Use four metric cards: active monitors, new products, price/information changes, and failed sources. Each card has a semantic status and a link to its destination.

- [ ] **Step 3: Implement the primary work surface**

Render the pending intelligence table with change type, product/site, value summary, confidence, time, and a primary action. Empty state must explain why there is no data and link to `新建监控`.

- [ ] **Step 4: Implement recent changes and health rail**

The timeline groups the latest changes; the health rail shows site status, last check, freshness, and failure count. Keep the rail actionable rather than decorative.

- [ ] **Step 5: Run build**

Run `npm.cmd run build`; expected: the overview route compiles and has no missing imports.

### Task 5: Serve and preview the first slice

**Files:**
- Modify: `app/main.py`
- Modify: `frontend/vite.config.ts`
- Create: `tools/preview-frontend.ps1`
- Create: `test_frontend_shell.py`

**Interfaces:**
- Development mode proxies `/api` to the FastAPI server.
- Production mode serves the built frontend entry and preserves `/api/*` routes.
- `test_frontend_shell.py` checks generated HTML for required navigation labels and the `新建监控` entry point.

- [ ] **Step 1: Add FastAPI static distribution handling**

Keep the current `static/index.html` fallback until the React build is verified. Add an explicit environment or file-existence gate so a missing frontend build never takes down the API.

- [ ] **Step 2: Add local preview script**

The script starts the frontend preview server and documents the URL. It must not change databases or start background workers by default.

- [ ] **Step 3: Run backend and frontend checks**

Run:

```powershell
python -m compileall -q app
python -m unittest -v test_frontend_shell.py test_static_advanced_toggle.py test_static_monitor_settings_ui.py
cd frontend
npm.cmd run build
```

Expected: all checks pass and the preview URL renders the shell and overview.

- [ ] **Step 4: Capture preview evidence**

Open the preview in the approved Codex browser surface, capture desktop and mobile screenshots, inspect them, and provide the user with the preview URL and screenshots. If annotation support is available in the preview surface, keep the preview open for user markup; if it is unavailable, ask for permission or explicit direction before substituting another surface.

## Self-review

- Scope is limited to the shell and overview slice; monitors, inbox, products, reports, operations, and settings remain explicit temporary route states for later plans.
- The current API is reused; no backend behavior is silently rewritten.
- Loading, partial, empty, error, and responsive requirements have dedicated tasks.
- No dependency installation is performed without the user's requested permission flow.
