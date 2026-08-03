import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

function read(path) {
  return readFileSync(resolve(root, path), "utf8");
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function exists(path) {
  return existsSync(resolve(root, path));
}

const sourceFiles = [
  "index.html",
  "src/api/auth.ts",
  "src/api/changes.ts",
  "src/api/inbox.ts",
  "src/api/monitors.ts",
  "src/api/notifications.ts",
  "src/api/operations.ts",
  "src/api/products.ts",
  "src/app/routes.tsx",
  "src/components/layout/Sidebar.tsx",
  "src/components/layout/TopBar.tsx",
  "src/components/layout/WorkspaceSwitcher.tsx",
  "src/features/auth/LoginPage.tsx",
  "src/features/changes/ChangeDetailPage.tsx",
  "src/features/overview/OverviewPage.tsx",
  "src/features/inbox/InboxPage.tsx",
  "src/features/monitors/MonitorsPage.tsx",
  "src/features/monitors/CreateMonitorPage.tsx",
  "src/features/monitors/BaselineScanPage.tsx",
  "src/features/notifications/NotificationsPage.tsx",
  "src/features/operations/OperationsPage.tsx",
  "src/features/products/ProductDetailPage.tsx",
  "src/features/products/ProductsPage.tsx",
  "src/features/reports/ReportsPage.tsx",
  "src/features/settings/SettingsPage.tsx",
];

const viteConfig = read("vite.config.ts");
assert(viteConfig.includes('"http://127.0.0.1:8015"'), "Local preview must proxy to the active baseline-scan backend");

const mojibakePattern = /(鎬|鐩|鎯|浜|鍙|瀹|璁|閫|妫|浠|搴|绔|缂|鏌|杩|婕|闇|瑙|绠|鍝|鏂|姝|鍔|鏁|鈥|锛|銆|絔|閹|娑|楠|瀨|缁|爘|噟)/;

for (const file of sourceFiles) {
  const content = read(file);
  assert(!/[�锟]/.test(content), `${file} contains replacement-character mojibake`);
  assert(!mojibakePattern.test(content), `${file} contains likely Chinese mojibake`);
  assert(!content.includes("Product Intel"), `${file} must not use old Product Intel brand`);
}

const sidebar = read("src/components/layout/Sidebar.tsx");
const indexHtml = read("index.html");
const globalCss = read("src/styles/global.css");

assert(exists("public/productalert-logo.svg"), "Brand logo asset must exist");
assert(exists("public/favicon.svg"), "Favicon asset must exist");
assert(sidebar.includes("/productalert-logo.svg"), "Sidebar must render the ProductAlert logo asset");
assert(indexHtml.includes('href="/favicon.svg"'), "index.html must register the ProductAlert favicon");
assert(indexHtml.includes("ProductAlert"), "index.html title must use ProductAlert brand");
assert(globalCss.includes(".brand-logo"), "Global CSS must style the ProductAlert logo image");

for (const label of ["ProductAlert", "productalert.cn", "总览", "监控中心", "情报收件箱", "产品库", "通知中心", "报告与趋势", "运维中心", "设置"]) {
  assert(sidebar.includes(label), `Sidebar is missing label: ${label}`);
}

const topBar = read("src/components/layout/TopBar.tsx");
for (const text of ["打开导航", "搜索品牌、产品或变化记录", "登录 API", "快捷筛选", "新建监控", "运营研究员"]) {
  assert(topBar.includes(text), `TopBar is missing polished text: ${text}`);
}

const appShell = read("src/components/layout/AppShell.tsx");
assert(!exists("src/components/layout/AnnotationPanel.tsx"), "AnnotationPanel must not exist in ProductAlert");
for (const forbidden of ["批注模式", "annotation-mode", "AnnotationPanel", "annotationMode", "annotate", "annotation-panel", "annotation-hotspot", "annotation-mode-button", "has-annotation-panel"]) {
  assert(!topBar.includes(forbidden), `TopBar must not contain annotation feature: ${forbidden}`);
  assert(!appShell.includes(forbidden), `AppShell must not contain annotation feature: ${forbidden}`);
  assert(!globalCss.includes(forbidden), `Global CSS must not contain annotation feature: ${forbidden}`);
}

const workspaceSwitcher = read("src/components/layout/WorkspaceSwitcher.tsx");
for (const text of ["切换工作空间", "当前工作空间", "ProductAlert"]) {
  assert(workspaceSwitcher.includes(text), `WorkspaceSwitcher is missing polished text: ${text}`);
}

const routes = read("src/app/routes.tsx");
for (const path of ["/monitors", "/inbox", "/changes/:id", "/login", "/products", "/products/:id", "/notifications", "/operations", "/reports", "/settings"]) {
  assert(routes.includes(`path="${path}"`), `Routes must expose ${path}`);
}
for (const component of ["MonitorsPage", "CreateMonitorPage", "InboxPage", "ChangeDetailPage", "LoginPage", "ProductsPage", "ProductDetailPage", "NotificationsPage", "OperationsPage", "ReportsPage", "SettingsPage"]) {
  assert(routes.includes(`<${component}`), `Routes must render ${component}`);
}

const monitors = read("src/features/monitors/MonitorsPage.tsx");
for (const text of ["监控中心", "新建监控", "立即扫描", "暂停", "恢复", "编辑规则", "查看变化", "成功率", "最近扫描", "操作成功", "请先登录"]) {
  assert(monitors.includes(text), `Monitoring Center is missing required text: ${text}`);
}

const createMonitor = read("src/features/monitors/CreateMonitorPage.tsx");
for (const text of ["新建监控", "目标 URL", "新品上新", "价格变化", "库存变化", "自动识别", "CSS 选择器", "高级规则", "监控频率", "通知渠道", "保存监控", "保存到真实后端", "请先登录"]) {
  assert(createMonitor.includes(text), `Create Monitor Wizard is missing required text: ${text}`);
}

const monitorApi = read("src/api/monitors.ts");
for (const text of ["createMonitorAndStartBaseline", "getScanJob", "triggerSiteScan", "updateSiteEnabled", "deleteSite", "/api/sites", "/scan", "/api/scan-jobs", "notification_events"]) {
  assert(monitorApi.includes(text), `Monitor API client is missing required text: ${text}`);
}

const baselineScanPage = read("src/features/monitors/BaselineScanPage.tsx");
for (const text of ["setInterval", "已发现", "已处理", "查看产品库", "getScanJob", "triggerSiteScan"]) {
  assert(baselineScanPage.includes(text), `Baseline Scan Page is missing required behavior: ${text}`);
}
for (const text of ["resumeScanJob", "rate_limited_count", "pending_retry_count", "\u5f85\u9a8c\u8bc1\u5546\u54c1", "\u53d7\u9650\u6d41", "\u7ee7\u7eed\u626b\u63cf"]) {
  assert(baselineScanPage.includes(text), `Baseline Scan Page is missing catalog quality behavior: ${text}`);
}
const createMonitorPage = read("src/features/monitors/CreateMonitorPage.tsx");
assert(createMonitorPage.includes("createMonitorAndStartBaseline"), "Create Monitor Page must start the baseline scan");
assert(createMonitorPage.includes("/baseline/"), "Create Monitor Page must navigate to baseline progress");
const monitorsPage = read("src/features/monitors/MonitorsPage.tsx");
for (const text of ["deleteSite", "window.confirm", "删除监控", "Trash2"]) {
  assert(monitorsPage.includes(text), `Monitor Center is missing safe delete support: ${text}`);
}

const notificationsApi = read("src/api/notifications.ts");
for (const text of ["loadNotifications", "retryNotification", "/api/notifications", "/retry", "NotificationRecord"]) {
  assert(notificationsApi.includes(text), `Notifications API client is missing required text: ${text}`);
}
for (const text of ["loadNotificationRules", "NotificationRule", "/api/notification-rules", "event_types", "min_severity", "inbox_status"]) {
  assert(notificationsApi.includes(text), `Notification rules API client is missing required text: ${text}`);
}

const operationsApi = read("src/api/operations.ts");
for (const text of ["loadOperationsContext", "/api/system/health", "/api/scan-jobs", "/api/scan-logs", "ScanJob"]) {
  assert(operationsApi.includes(text), `Operations API client is missing required text: ${text}`);
}

const productsApi = read("src/api/products.ts");
for (const text of ["loadProducts", "/api/products", "ProductDetailContext"]) {
  assert(productsApi.includes(text), `Products API client is missing required text: ${text}`);
}

const inbox = read("src/features/inbox/InboxPage.tsx");
for (const text of ["情报收件箱", "新品上新", "价格变化", "库存变化", "信息变化", "标记已处理", "标记误报", "重点关注", "批量处理", "导出 CSV", "严重程度", "操作成功", "请先登录"]) {
  assert(inbox.includes(text), `Intelligence Inbox is missing required text: ${text}`);
}
for (const text of ["处理状态", "负责人", "处理备注", "需跟进", "误报原因", "运营处理流"]) {
  assert(inbox.includes(text), `Intelligence Inbox is missing workflow text: ${text}`);
}
for (const text of ["normalizeInboxStatus", "inbox_status", "false_positive", "important", "read"]) {
  assert(inbox.includes(text), `Intelligence Inbox must normalize backend inbox_status: ${text}`);
}
for (const text of ["assignee", "review_note", "false_positive_reason", "reviewPayloadFor"]) {
  assert(inbox.includes(text), `Intelligence Inbox must persist workflow field: ${text}`);
}
for (const text of ["loadChangeEvents", "changeEventFilters", "activeSite", "activeAssignee", "severity: activeSeverity", "q: debouncedQuery", "setDebouncedQuery", "setData({ ...overview, events })", "负责人筛选", "全部站点"]) {
  assert(inbox.includes(text), `Intelligence Inbox must use backend filters: ${text}`);
}

const inboxApi = read("src/api/inbox.ts");
for (const text of ["updateChangeEventInboxStatus", "ChangeEventReviewPayload", "/api/change-events", "false_positive", "important", "read", "assignee", "review_note", "false_positive_reason"]) {
  assert(inboxApi.includes(text), `Inbox API client is missing required text: ${text}`);
}

const changesApi = read("src/api/changes.ts");
for (const text of ["loadChangeDetail", "loadChangeEvents", "ChangeEventFilters", "inbox_status", "assignee", "change_type", "site_id", "severity", "q", "/api/change-events", "snapshot_after", "scan_metadata"]) {
  assert(changesApi.includes(text), `Change Detail API client is missing required text: ${text}`);
}

const changeDetail = read("src/features/changes/ChangeDetailPage.tsx");
for (const text of ["变化详情", "字段差异", "价格差异", "截图对比", "文本 Diff", "置信度", "严重程度", "扫描元数据", "处理记录", "标记误报"]) {
  assert(changeDetail.includes(text), `Change Detail is missing required text: ${text}`);
}
for (const text of ["负责人", "处理备注", "处理状态", "需跟进", "误报原因", "运营处理记录"]) {
  assert(changeDetail.includes(text), `Change Detail is missing workflow text: ${text}`);
}
for (const text of ["loadChangeDetail", "real-detail-api", "detail-api-fallback", "updateChangeEventInboxStatus", "handleReviewStatus", "操作成功", "操作失败", "请先登录"]) {
  assert(changeDetail.includes(text), `Change Detail is missing required behavior marker: ${text}`);
}
for (const text of ["assignee", "review_note", "false_positive_reason", "reviewed_at"]) {
  assert(changeDetail.includes(text), `Change Detail must persist workflow field: ${text}`);
}

const apiTypes = read("src/types/api.ts");
assert(apiTypes.includes("inbox_status?: string | null"), "ChangeEvent type must expose backend inbox_status");
for (const text of ["assignee?: string | null", "review_note?: string | null", "false_positive_reason?: string | null", "reviewed_at?: string | null"]) {
  assert(apiTypes.includes(text), `ChangeEvent type must expose workflow field: ${text}`);
}

const login = read("src/features/auth/LoginPage.tsx");
for (const text of ["登录 ProductAlert", "注册新账号", "邮箱", "密码", "进入工作台"]) {
  assert(login.includes(text), `Login Page is missing required text: ${text}`);
}

const notifications = read("src/features/notifications/NotificationsPage.tsx");
for (const text of ["通知中心", "通知规则", "新品上新", "价格变化", "库存变化", "信息变化", "邮件", "Webhook", "企业微信 / 飞书", "重试通知", "导出 CSV", "真实 API", "演示数据"]) {
  assert(notifications.includes(text), `Notifications Page is missing required text: ${text}`);
}
for (const text of ["通知策略", "真实规则 API", "事件类型", "严重程度", "处理状态", "只推送新品/价格变化", "只推送高严重程度", "只推送需跟进事件", "loadNotificationRules"]) {
  assert(notifications.includes(text), `Notifications Page is missing notification strategy text: ${text}`);
}

const products = read("src/features/products/ProductsPage.tsx");
for (const text of ["产品库", "产品搜索", "价格", "库存", "来源站点", "关联变化", "查看详情", "真实 API", "演示数据"]) {
  assert(products.includes(text), `Products Page is missing required text: ${text}`);
}
for (const text of ["URLSearchParams", "product-thumb", "onError", "slice(0, 2)", "product-type"]) {
  assert(products.includes(text), `Products Page is missing enriched product-library behavior: ${text}`);
}

const productDetail = read("src/features/products/ProductDetailPage.tsx");
for (const text of ["产品详情", "价格与库存", "关联变化事件", "打开官网", "返回产品库", "查看变化详情"]) {
  assert(productDetail.includes(text), `Product Detail Page is missing required text: ${text}`);
}

const reports = read("src/features/reports/ReportsPage.tsx");
for (const text of ["ReportsPage", "trendBars", "siteActivity", "scanReliability", "newProductCount", "priceChangeCount", "stockChangeCount", "infoChangeCount"]) {
  assert(reports.includes(text), `Reports Page is missing required analytics feature: ${text}`);
}
for (const text of ["loadChangeEvents", "processingSummary", "pendingCount", "followUpCount", "falsePositiveRate", "assigneeWorkload", "待处理", "需跟进", "误报率", "负责人工作量"]) {
  assert(reports.includes(text), `Reports Page is missing workflow analytics feature: ${text}`);
}

const operations = read("src/features/operations/OperationsPage.tsx");
for (const text of ["OperationsPage", "systemHealth", "scanJobs", "scanLogs", "queueStatus", "workerStatus", "databaseStatus", "redisStatus", "notificationWorkerStatus"]) {
  assert(operations.includes(text), `Operations Page is missing required ops feature: ${text}`);
}

const settings = read("src/features/settings/SettingsPage.tsx");
for (const text of ["SettingsPage", "accountSettings", "workspaceSettings", "notificationChannels", "scanDefaults", "webhookSettings", "apiKeySettings", "securitySettings", "exportBackup"]) {
  assert(settings.includes(text), `Settings Page is missing required settings feature: ${text}`);
}

const overview = read("src/features/overview/OverviewPage.tsx");
for (const text of ["真实 API", "演示数据", "需要登录", "API 不可用"]) {
  assert(overview.includes(text), `Overview data source status is missing required text: ${text}`);
}

console.log("UI contract checks passed.");
