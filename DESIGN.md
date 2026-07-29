# DESIGN.md

> 第一阶段 UI 改造目标：把“官网新品情报监控系统”从原型工作台升级为可正式上线的 macOS 控制台风格 B 端监控平台，优先服务运营、选品、竞品研究和技术运维的日常处理效率。

## 1. Visual Theme & Atmosphere

**Style**: macOS Operations Console
**Keywords**: 苹果风格、极简、高级、精密、克制、可扫描、状态驱动、正式上线
**Tone**: 专业、稳定、数据可信，NOT 营销型、装饰型、花哨大屏。
**Feel**: 像一个原生 macOS 专业工具：轻侧栏、柔和白灰背景、精密表格、清晰状态和少量蓝色主操作。

**Interaction Tier**: L1 精致静态 + 少量状态动效
**Dependencies**: CSS only，第一阶段不引入新前端依赖。

**Confirmed Final UI Reference**: 用户已确认采用当前预览版：浅色 macOS 控制台、轻量左侧导航、顶部官网监控输入区、四个指标卡、表格优先产品库、右侧时间线和已监控官网。后续第一阶段 UI 实现以该版本为准，不再切回深色窄图标栏或三方向选择页。

设计原则：
- 主平台采用 A 方向：macOS 控制台感。B 的毛玻璃只允许少量用于概览浮层或登录页背景；C 的 Apple Store 留白只用于登录页、空状态和引导态。
- 这是 B 端监控平台，不做 landing page，不做大面积 hero，不用营销型大标题。
- 首屏必须回答四个问题：是否在监控、哪里失败、发现了什么、我该处理什么。
- 所有视觉层级围绕任务优先级、状态和证据展开。
- 默认桌面优先，适配 1366、1440、1920 宽度；移动端保持可用但不是主要效率场景。

## 2. Color Palette & Roles

```css
:root {
  /* Backgrounds */
  --bg: #f5f7fb;
  --surface: #ffffff;
  --surface-alt: #f8fafc;
  --surface-subtle: #eef2f7;
  --surface-hover: #f3f7ff;

  /* Borders */
  --border: #dfe5ef;
  --border-soft: #edf1f7;
  --border-hover: #b9c8e6;
  --border-strong: #8ea4c8;

  /* Text */
  --text: #101828;
  --text-secondary: #475467;
  --text-tertiary: #667085;
  --text-disabled: #98a2b3;
  --text-inverse: #ffffff;

  /* Navigation */
  --nav-bg: #0b1220;
  --nav-text: #cbd5e1;
  --nav-text-active: #ffffff;
  --nav-item-hover: rgba(255, 255, 255, 0.08);

  /* Accent */
  --accent: #2563eb;
  --accent-hover: #1d4ed8;
  --accent-soft: #eff6ff;
  --accent-muted: #dbeafe;

  /* RGB variants for rgba() */
  --bg-rgb: 245, 247, 251;
  --surface-rgb: 255, 255, 255;
  --accent-rgb: 37, 99, 235;

  /* Semantic */
  --success: #039855;
  --success-soft: #ecfdf3;
  --warning: #dc6803;
  --warning-soft: #fff7ed;
  --error: #d92d20;
  --error-soft: #fef3f2;
  --info: #0ea5e9;
  --info-soft: #f0f9ff;
  --neutral: #667085;
  --neutral-soft: #f2f4f7;

  /* Priority */
  --priority-high: #b42318;
  --priority-medium: #b54708;
  --priority-low: #344054;
}
```

**Color Rules:**
- 所有新增 CSS 必须通过变量引用颜色，不允许散落硬编码色值。
- 蓝色只用于当前状态、主操作、链接和信息提示。
- 红色只用于失败、危险操作、严重告警和安全风险。
- 橙色用于需要关注但不阻塞的异常，如低置信度、部分失败、待复核。
- 绿色用于成功、健康、已发送、已完成，不用于普通装饰。
- 页面背景保持浅灰，主工作区用白色表面承载；不要继续扩大玻璃拟态范围。

## 3. Typography Rules

**Font Stack:**
```css
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap");
```

| Role | Font | Size | Weight | Line Height | Letter Spacing |
|------|------|------|--------|-------------|----------------|
| Page Title | "Noto Sans SC", Inter | 22-24px | 750 | 1.25 | 0 |
| Section H2 | "Noto Sans SC", Inter | 18-20px | 700 | 1.35 | 0 |
| Panel H3 | "Noto Sans SC", Inter | 15-16px | 700 | 1.4 | 0 |
| Table Header | "Noto Sans SC", Inter | 12px | 700 | 1.3 | 0 |
| Body | "Noto Sans SC", Inter | 13-14px | 400-500 | 1.55 | 0 |
| Label | "Noto Sans SC", Inter | 12px | 650 | 1.35 | 0 |
| Metric Number | Inter, "Noto Sans SC" | 24-30px | 780 | 1 | 0 |
| Mono/URL | "SFMono-Regular", Consolas | 12-13px | 500 | 1.45 | 0 |

**Typography Rules:**
- Dashboard/App UI 不使用 hero 级别大字；页面主标题最大 24px。
- 表格、日志、URL、错误原因必须优先可读，不使用过浅灰色。
- 中文正文行高不低于 1.55，长说明不超过两行，更多信息放进详情抽屉。
- 禁止负字距、花体、纯英文 UI 字体作为中文主字体。

**Text Decoration:**
- 页面标题无渐变、无投影。
- 状态数值可用轻微色彩强调，但不使用发光效果。
- 链接使用下划线 hover 或浅蓝底 pill，不使用彩色渐变文字。

## 4. Component Stylings

### Buttons
```css
.btn {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0 12px;
  color: var(--text);
  background: var(--surface);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.btn:hover {
  border-color: var(--border-hover);
  background: var(--surface-hover);
}
.btn:active {
  transform: translateY(1px);
}
.btn:focus-visible {
  outline: 3px solid rgba(var(--accent-rgb), 0.18);
  outline-offset: 2px;
}
.btn:disabled {
  color: var(--text-disabled);
  background: var(--surface-subtle);
  cursor: not-allowed;
  transform: none;
}
.btn-primary {
  border-color: var(--accent);
  color: var(--text-inverse);
  background: var(--accent);
}
.btn-primary:hover {
  border-color: var(--accent-hover);
  background: var(--accent-hover);
}
.btn-danger {
  border-color: var(--error);
  color: var(--error);
  background: var(--surface);
}
```

### Cards / Panels
```css
.panel {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.panel:hover {
  border-color: var(--border-hover);
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 52px;
  border-bottom: 1px solid var(--border-soft);
  padding: 12px 16px;
}
```

### Navigation
```css
.side-rail {
  width: 244px;
  background: var(--nav-bg);
  color: var(--text-inverse);
}
.nav-item {
  min-height: 38px;
  border-radius: 8px;
  padding: 0 10px;
  color: var(--nav-text);
}
.nav-item:hover,
.nav-item[aria-current="page"] {
  color: var(--nav-text-active);
  background: var(--nav-item-hover);
}
```

### Tables
```css
.data-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
}
.data-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  height: 38px;
  border-bottom: 1px solid var(--border);
  color: var(--text-tertiary);
  background: var(--surface-alt);
  font-size: 12px;
  font-weight: 750;
  text-align: left;
}
.data-table td {
  height: 52px;
  border-bottom: 1px solid var(--border-soft);
  color: var(--text-secondary);
}
.data-table tr:hover td {
  background: var(--surface-hover);
}
```

### Tags / Badges
```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 700;
}
.badge-success { color: var(--success); background: var(--success-soft); }
.badge-warning { color: var(--warning); background: var(--warning-soft); }
.badge-error { color: var(--error); background: var(--error-soft); }
.badge-info { color: var(--accent); background: var(--accent-soft); }
.badge-neutral { color: var(--neutral); background: var(--neutral-soft); }
```

### Forms
```css
.field {
  display: grid;
  gap: 6px;
}
.field label {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}
.input,
.select,
.textarea {
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 7px 10px;
  color: var(--text);
  background: var(--surface);
}
.input:focus,
.select:focus,
.textarea:focus {
  border-color: var(--accent);
  outline: 3px solid rgba(var(--accent-rgb), 0.12);
}
```

## 5. Layout Principles

**Shell:**
- Left nav: 232-248px fixed.
- Workspace padding: 18-24px.
- Main grid: 24-column mental model; actual CSS uses named regions for clarity.
- Right rail: 320-360px only when it carries actionable filters or health summary.

**First Screen Structure:**
1. Compact top command bar: URL input, start monitoring, refresh, current health.
2. Health strip: success rate, active jobs, failed sources, pending review.
3. Main split: left primary work surface, right operational rail.
4. Primary work surface starts with product/changes table, not empty decorative card.

**Spacing Scale:**
- Page gap: 16px.
- Panel padding: 14-16px.
- Table row height: 48-56px.
- Toolbar height: 44-52px.
- Card radius: 8-10px.

**Grid:**
```css
.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 16px;
}
.primary-workspace {
  min-width: 0;
  min-height: 0;
}
.ops-rail {
  min-width: 0;
  min-height: 0;
}
```

## 6. Depth & Elevation

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat | no shadow, border only | tables, filters, dense rows |
| Subtle | `0 1px 2px rgba(16, 24, 40, 0.06)` | panels and cards |
| Elevated | `0 10px 24px rgba(16, 24, 40, 0.10)` | modal, drawer |
| Overlay | backdrop + elevated panel | confirm dialogs, detail drawer |

```css
:root {
  --shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.06);
  --shadow-md: 0 10px 24px rgba(16, 24, 40, 0.10);
  --shadow-lg: 0 20px 48px rgba(16, 24, 40, 0.16);
}
```

不要使用大面积 `backdrop-filter`；只允许在 modal 背景或非常小的浮层中使用。

## 7. Animation & Interaction

**Motion Philosophy**: 动效只服务状态确认和操作反馈，不抢数据注意力。
**Tier**: L1

### Entrance Animation
```css
@keyframes fade-slide-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.panel,
.table-shell,
.ops-card {
  animation: fade-slide-in 160ms ease-out both;
}
```

### Loading States
- 初次加载：主表格显示 skeleton rows，右侧 rail 显示 compact skeleton。
- 提交/保存：按钮 disabled 并显示动词状态，例如“保存中”“扫描入队中”。
- 扫描入队后：不弹 alert，显示 toast + scan job row 状态变为 queued/running。

### Hover & Focus States
```css
.interactive-row:hover {
  background: var(--surface-hover);
}
.interactive-row:focus-visible {
  outline: 3px solid rgba(var(--accent-rgb), 0.14);
  outline-offset: -3px;
}
```

### Toast
- 右上角堆叠。
- 成功 3 秒自动消失；错误保持 6 秒并可关闭。
- 错误 toast 必须显示来自 API 的可读原因。

### Modal / Drawer
- 删除站点、删除 source 等危险操作使用 modal，不再使用 `confirm()`。
- 产品详情、变化 diff、扫描诊断使用右侧 drawer，不跳离当前列表上下文。

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 8. Do's and Don'ts

### Do
- 首屏优先展示运行健康和待处理事项。
- 产品库默认提供表格模式，卡片模式作为可选查看方式。
- 每个空状态必须展示“为什么没有数据”和“下一步操作”。
- 每个扫描失败必须能追踪到 source、URL、时间、错误类型。
- 每个通知失败必须能看到 attempts、next_attempt_at、last_error。
- 所有批量操作必须先显示选中数量和影响范围。
- 所有状态 badge 使用固定语义颜色。
- 所有危险操作使用 modal 确认。

### Don't
- 不要使用大面积渐变、玻璃拟态或装饰背景。
- 不要把产品列表只做成卡片流。
- 不要把扫描日志、通知投递、操作审计混成一个无分组长列表。
- 不要用 alert/confirm 作为正式上线交互。
- 不要让用户手动猜测 CSS selector 是否有效，必须提供测试反馈入口。
- 不要在首屏放长篇说明文案。
- 不要用“待处理提醒”这种合并指标替代具体风险分类。
- 不要隐藏失败原因或只显示“请求失败”。
- 不要让 body 和多个容器同时 `overflow: hidden` 导致内容不可达。
- 不要在中文 UI 中使用负字距或过浅文本。

## 9. Responsive Behavior

**Breakpoints:**

| Name | Width | Key Changes |
|------|-------|-------------|
| Wide Desktop | >= 1600px | left nav 248px, ops rail 360px, table columns fully visible |
| Desktop | 1180-1599px | left nav 232px, ops rail 320-340px, table keeps horizontal scroll only inside table shell |
| Tablet | 820-1179px | ops rail moves below primary workspace, KPI cards 2 columns |
| Mobile | < 820px | top nav replaces side nav, command bar stacks, tables become card rows |

**Touch Targets:** minimum 44px on touch breakpoints.

**Collapsing Strategy:**
- Product table on mobile becomes compact list rows with title, site, price, status, detected time, primary action.
- Filters collapse into a drawer opened by “筛选” button.
- Right rail cards stack below main content.
- Delete, retry, archive actions remain reachable through row action menu.

```css
@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
  .ops-rail {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
  .side-rail {
    position: sticky;
    top: 0;
    z-index: 10;
    width: 100%;
    min-height: auto;
  }
  .data-table {
    display: none;
  }
  .mobile-row-list {
    display: grid;
  }
}

## 10. Product Information Architecture

The product is a B2B product-intelligence workspace, not a marketing landing page. The shell must keep the primary task visible: understand what changed and decide what to do next.

### Primary navigation

```text
总览
监控中心
情报收件箱
产品库
报告与趋势
运维中心
设置
```

The global primary action is `新建监控`. It is available in the top bar and in the empty state of the monitor center. The inbox displays an unread count and is the only navigation item that may use a dynamic badge.

### Routes

```text
/overview
/monitors
/monitors/new
/monitors/:id
/inbox
/products
/products/:id
/reports
/operations
/settings
/settings/team
/settings/notifications
/settings/api
```

### Global shell

- Left rail: 232–248px, fixed on desktop, collapsible on mobile.
- Top bar: workspace switcher, global search, `新建监控`, notification shortcut, user menu.
- Workspace: 18–24px padding, max-width fluid layout, no hero banner.
- Right rail: 320–360px only when it carries actionable health, filters, or evidence.
- Detail context: use a right drawer for product, diff, and scan diagnostics; do not force a list-to-detail page jump for routine review.

## 11. Core Screens And Entry Points

### Overview

The first viewport answers four questions: whether monitoring is healthy, where it failed, what was discovered, and what needs action. It contains the health strip, pending intelligence list, recent change timeline, and monitor health rail.

### Monitor center

The monitor list is table-first. Columns are: brand, URL, monitored targets, cadence, last check, freshness, status, and actions. The detail page groups source settings, rules, scan history, health, and discovered products.

### Intelligence inbox

The inbox groups product-new, price, availability, product-info, image, promotion, removal, and collection-error events. Filters include brand, change type, time, severity, confidence, and workflow status. Each row opens the evidence drawer.

### Product library

The default view is a dense table with optional card view. Product detail includes canonical fields, price history, availability history, image history, source provenance, confidence, and a chronological change timeline.

### Reports and trends

Reports are operational rather than BI-heavy: launch volume, price movement, stock movement, brand timeline, coverage, freshness, and collection quality. Export actions are always scoped and show the selected count before execution.

### Operations

Operations exposes queued/running/failed jobs, retry state, notification delivery, source health, freshness, and the last error. Every failure must be traceable to source, URL, time, error category, and retry state.

## 12. Monitor Creation Workflow

`新建监控` is a four-step wizard. Progress is explicit and the user can return to prior steps without losing configuration.

1. **品牌与官网** — name, public URL, region, category, priority, notes. The system probes sitemap, RSS, listing pages, product pages, Shopify data, and JSON-LD without silently activating a monitor.
2. **监控目标** — choose one or more of new products, prices, availability, product information, images, promotions, or a selected page region.
3. **条件与通知** — cadence, timezone, include/exclude keywords, price thresholds, percentage thresholds, selector, dynamic-content exclusions, review policy, and notification destinations.
4. **测试与基线** — show discovered pages, products, fields, extraction failures, sample records, coverage estimate, and risk warnings. Baseline is created only after explicit confirmation.

The wizard must provide a test result for every selector and field. A user should be able to reach a useful first monitor without writing CSS by hand.

## 13. Evidence Drawer

The evidence drawer is the canonical review surface. It shows:

- event type and severity;
- product, brand, and source;
- old value, new value, absolute delta, and percentage delta when applicable;
- detected time and confidence;
- before/after text diff;
- before/after screenshot when available;
- field provenance and extraction method;
- source URL and scan job;
- actions: open source, mark important, assign, comment, ignore, archive.

The drawer stays in the current list context and restores focus to the triggering row when closed.

## 14. Component Inventory

The first component layer contains:

```text
AppShell
Sidebar
TopBar
WorkspaceSwitcher
PageHeader
MetricCard
HealthCard
DataTable
FilterBar
StatusBadge
ConfidenceBadge
ChangeTypeBadge
Drawer
Modal
Toast
EmptyState
Skeleton
MonitorWizard
ChangeDiff
Timeline
PriceHistoryChart
ErrorDetails
```

Every interactive component must define default, hover, active, focus-visible, disabled, loading, empty, and error states where applicable. Destructive actions use `Modal`; routine context stays in `Drawer`.

## 15. Data States And Feedback

- **Loading:** skeleton rows in the primary table and compact skeletons in the health rail.
- **Queued/running:** show the job state in the source row and toast the action; do not use blocking alerts.
- **Empty:** state why no data exists and provide one next action, such as `新建监控` or `调整筛选`.
- **Partial:** show successful and failed source counts separately.
- **Error:** preserve the API reason, source URL, timestamp, retry count, and next retry time.
- **Low confidence:** use warning styling and route the event to review when configured.
- **Reduced motion:** all transitions degrade to immediate state changes under `prefers-reduced-motion`.

## 16. Frontend Architecture

The UI will be implemented as a React + Vite + TypeScript application while the existing FastAPI service remains the API and deployment boundary.

```text
frontend/src/
├── app/                 # shell, routing, providers
├── api/                 # typed request functions and error mapping
├── components/          # reusable visual primitives
├── features/            # overview, monitors, inbox, products, reports, operations
├── types/               # domain and API response types
└── styles/              # tokens, global styles, responsive rules
```

The migration is incremental: the new frontend first reproduces existing API-backed flows, then adds the new inbox, evidence, history, and monitoring-wizard surfaces. Backend business behavior is not rewritten as part of the UI shell pass.
