# ProductAlert Product Roadmap

Domain: productalert.cn

ProductAlert is a professional website monitoring and product intelligence platform for operators, merchandisers, buyer researchers, and brand monitoring teams.

The product is not a generic crawler first. Its core purpose is to continuously monitor brand sites, product listing pages, collection pages, and product detail pages, then convert product launches, price changes, stock changes, and content changes into an actionable intelligence workflow.

## Product Positioning

ProductAlert should focus on:

- New product launch monitoring.
- Price change monitoring.
- Stock, sold-out, and restock monitoring.
- Product information change monitoring.
- Website page and selected-area change monitoring.
- Operational intelligence inbox and review workflow.

The product should feel like a professional SaaS operations console: dense, calm, scannable, and reliable. The UI direction is a macOS-console-inspired backend tool, not a marketing landing page.

## Competitor Reference

ProductAlert should borrow from three categories of professional tools.

### Website Change Monitoring

Reference products: Visualping, Distill, Wachete.

Important capabilities:

- Page change monitoring.
- Visual screenshot comparison.
- Text and keyword change detection.
- Selected area monitoring.
- Scheduled checks.
- Alerts and change history.

### Data Extraction and Crawler Platforms

Reference products: Apify, Browse AI, Octoparse, ParseHub.

Important capabilities:

- Structured extraction tasks.
- Browser automation for dynamic pages.
- Rule configuration.
- Scheduling and retries.
- Data export.
- Logs and task health diagnostics.

### E-commerce and Competitor Monitoring

Reference products: Prisync, Price2Spy, Dataweave, Keepa-like product intelligence tools.

Important capabilities:

- Product list monitoring.
- New and removed product detection.
- Price increase and decrease detection.
- Stock and availability tracking.
- SKU-level history.
- Competitor comparison and reporting.

## Differentiation

ProductAlert should not try to become a full generic crawler at the beginning.

The initial differentiation is:

- Stronger focus on brand official websites and collection pages.
- First-class support for new product detection.
- Product-oriented change records instead of raw page diffs only.
- An intelligence inbox designed for operations teams to review, classify, and process changes.
- Practical monitoring flows that work for non-engineering users, while still allowing advanced selector configuration.

## Core Capability Layers

### 1. Monitor Tasks

The system must support:

- Add target websites, brand official sites, collection pages, and product detail pages.
- Monitor new product launches.
- Monitor price changes.
- Monitor stock, sold-out, and restock changes.
- Monitor title, description, image, specification, color, and size changes.
- Monitor keyword changes and selected page regions.
- Configure frequency, pause state, retries, and manual scans.

### 2. Extraction Rules

The system should gradually support:

- Automatic product list and product card detection.
- CSS selector configuration for advanced users.
- Screenshot-based monitoring.
- DOM and text content monitoring.
- Structured field mapping: title, price, image, URL, stock, SKU, variants.
- Anti-noise rules to ignore ads, recommendation blocks, timestamps, counters, and dynamic content.
- Playwright-based dynamic page extraction.

### 3. Change Detection

The system must identify:

- Newly added products.
- Removed or unavailable products.
- Price increases.
- Price decreases.
- Product field changes.
- Page visual differences.
- Text and HTML differences.
- Change severity.
- Confidence score.
- Historical versions.

### 4. Intelligence Workflow

The product should include an intelligence inbox with:

- Unified list of all detected changes.
- Categories for new product, price drop, price rise, out of stock, restock, and content change.
- Filters by brand, site, monitor type, severity, and status.
- Mark as processed.
- Mark as false positive.
- Mark as watched or important.
- Batch operations.
- CSV or Excel export.
- Notification integrations in later phases.

### 5. Operations and System Health

The platform should expose:

- Monitor health status.
- Recent scan logs.
- Failure reason diagnostics.
- Success rate.
- Scan duration.
- Error rate.
- Retry records.
- Proxy, rate limit, and anti-blocking strategy in later phases.
- Team, permission, billing, and plan limits in later phases.

## Implementation Order

Follow this order strictly unless the user explicitly changes priority.

### Phase 1: Fix Foundation and Encoding

Goal: make the current UI and codebase safe to extend.

Scope:

- Fix broken Chinese encoding in frontend source files.
- Standardize sidebar navigation labels.
- Standardize page titles and visible copy.
- Keep the macOS-style console direction.
- Ensure local preview starts reliably on a stable URL.

Acceptance criteria:

- No visible mojibake or corrupted Chinese text.
- `/overview` loads locally.
- Production frontend build passes.
- The preview URL is clearly provided after the work.

### Phase 2: Monitoring Center

Goal: create the core operational entry point.

Scope:

- Add `/monitors` page.
- Display all monitor tasks.
- Show site or brand, target URL, monitor type, current status, last scan time, change count, success rate, and failure reason.
- Add actions: create monitor, run scan now, pause or resume, edit rule, view changes.
- Include empty, loading, and error states.

Acceptance criteria:

- `/monitors` is navigable from the sidebar.
- Users can understand all monitoring tasks at a glance.
- The page visually matches the overview console style.
- Mock data can be used before final API integration.

### Phase 3: Create Monitor Wizard

Goal: make first-time setup usable by non-engineering users.

Scope:

- Step 1: enter website, collection page, or product page URL.
- Step 2: select monitoring target: new products, price, stock, text, image, selected area.
- Step 3: select extraction method: automatic recognition, CSS selector, advanced rule.
- Step 4: configure frequency and notification preferences.
- Save task.

Acceptance criteria:

- The flow is clear enough for operators and buyer researchers.
- Advanced settings are available but not forced.
- The wizard can create a mock monitor task before backend integration.

### Phase 4: Intelligence Inbox

Goal: turn raw changes into reviewable work items.

Scope:

- Add `/inbox` page.
- List detected changes across all monitors.
- Classify change type.
- Filter by brand, site, severity, status, and time.
- Support mark processed, false positive, watched, and batch actions.
- Support export entry.

Acceptance criteria:

- Users can process detected changes from a single place.
- The page supports daily operational review.
- Change records are clear and scannable.

### Phase 5: Change Detail and Diff

Goal: provide trust and auditability for every detected change.

Scope:

- Add change detail view.
- Show old and new field values.
- Show price delta.
- Show product image and URL.
- Show screenshot comparison when available.
- Show text or HTML diff when available.
- Show confidence, severity, scan metadata, and processing history.

Acceptance criteria:

- Users can verify why a change was detected.
- False positives can be identified and marked.
- The page supports audit and handoff between team members.

### Phase 6: Real API Integration

Goal: connect the UI to the backend safely after the user experience is clear.

Scope:

- Replace mock data gradually with real endpoints.
- Keep typed frontend API clients.
- Add API error handling and retry-friendly UI states.
- Verify monitor list, scan logs, products, and change events.

Acceptance criteria:

- UI remains usable when the backend is unavailable.
- Backend integration does not break the demo flow.
- Core pages have realistic data contracts.

### Phase 7: Production Readiness Review

Goal: prepare the product for real users.

Scope:

- Review backend correctness.
- Review crawler stability.
- Review task scheduling.
- Review database migrations and seed data.
- Review security and input validation.
- Review logging and observability.
- Review deployment configuration.
- Review frontend build, routing, and runtime fallback behavior.
- Add focused tests for critical workflows.

Acceptance criteria:

- Known blockers are documented and prioritized.
- Critical launch risks are fixed.
- The product can be deployed for controlled user testing.

## Execution Rules

Use this document as the source of truth for future work.

For each development segment:

- State the phase being worked on.
- Keep scope limited to that phase unless the user approves a change.
- Implement the smallest useful vertical slice.
- Run verification before claiming completion.
- Provide the preview URL or clear visual preview after completion.
- Ask for permission immediately if a required permission, plugin, dependency, or external service is missing.

## Immediate Next Step

Start with Phase 1 and Phase 2:

1. Fix broken Chinese text and baseline UI copy.
2. Complete the Monitoring Center page at `/monitors`.
3. Verify local preview and production build.
4. Show the user the preview before moving to the Create Monitor Wizard.
