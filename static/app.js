const state = {
  token: null,
  user: null,
  sites: [],
  products: [],
  changes: [],
  logs: [],
  jobs: [],
  notifications: [],
  auditLogs: [],
  activeView: "products",
  logTab: "jobs",
  productFilter: "catalog",
  currentSiteId: null,
  searchTerm: "",
};

const sourceTypeLabels = {
  homepage: "官网首页",
  sitemap: "Sitemap 站点地图",
  rss: "RSS 订阅",
  listing_page: "产品列表页",
  news_page: "新品发布页",
  custom_page: "自定义页面",
};

const priorityLabels = {
  1: "高优先级",
  2: "中优先级",
  3: "低优先级",
};

const itemTypeLabels = {
  product_detail: "产品",
  collection_page: "分类页",
  promo_page: "活动页",
  unknown: "待复核",
};

const inboxStatusLabels = {
  unread: "未读",
  read: "已读",
  important: "重要",
  follow_up: "待跟进",
  archived: "已归档",
};

const viewCopy = {
  products: ["产品库与新品发现", "这里展示当前已盘点到的产品；基线之后新增的产品会用醒目标记区分。"],
  extraction: ["新品信息提取", "查看已发现产品的价格、图片、描述、功能卖点和待补充信息。"],
  sources: ["采集范围设置", "这是高级设置：告诉系统从哪些页面找商品；查看商品结果请回到产品库。"],
  logs: ["提醒与日志", "查看未读变化、扫描失败、候选链接数量和每次检查记录。"],
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const useAuth = options.auth !== false;
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (useAuth && state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const res = await fetch(path, {
    headers,
    credentials: "same-origin",
    ...options,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      clearSession();
    }
    throw new Error(formatApiError(data.detail));
  }
  return res.json();
}

async function downloadCsv(path, filename) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { headers, credentials: "same-origin" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(formatApiError(data.detail));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function scopedExportPath(path) {
  if (!state.currentSiteId) return path;
  return `${path}?site_id=${encodeURIComponent(state.currentSiteId)}`;
}

function formatApiError(detail) {
  if (!detail) return "请求失败";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      if (typeof item === "string") return item;
      const path = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
      const message = item.msg || JSON.stringify(item);
      return path ? `${path}: ${message}` : message;
    }).join("\n");
  }
  if (typeof detail === "object") {
    return detail.msg || detail.message || JSON.stringify(detail, null, 2);
  }
  return String(detail);
}

function formatTime(value) {
  if (!value) return "尚未检查";
  return new Date(value).toLocaleString("zh-CN");
}

function emptyToNull(value) {
  return value && String(value).trim() ? value : null;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayFeatures(features = [], limit = 4) {
  const noisyPattern = /(liquid error|could not find asset|sections\/|snippets\/|header line|undefined|exception|traceback)/i;
  const seen = new Set();
  return features
    .map((feature) => String(feature || "").replace(/\s+/g, " ").trim())
    .filter((feature) => feature && feature.length >= 2 && feature.length <= 80 && !noisyPattern.test(feature))
    .filter((feature) => {
      const key = feature.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, limit)
    .map((feature) => feature.length > 34 ? `${feature.slice(0, 34)}...` : feature);
}

function confidencePercent(product) {
  const score = Number(product.confidence_score || 0);
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

function confidenceLevel(product) {
  const percent = confidencePercent(product);
  if (percent >= 85) return "high";
  if (percent >= 70) return "medium";
  return "low";
}

function confidenceText(product) {
  const sourceLabels = {
    shopify_api: "Shopify API",
    json_ld: "JSON-LD",
    meta_tags: "Meta",
    browser_render: "浏览器渲染",
    html_inference: "HTML 推断",
    unknown: "未知来源",
  };
  const source = sourceLabels[product.extraction_source] || product.extraction_source || "未知来源";
  return `${confidencePercent(product)}% · ${source}`;
}

function confidenceBadge(product) {
  return `<span class="confidence-badge ${confidenceLevel(product)}">${escapeHtml(confidenceText(product))}</span>`;
}

function moneyText(amount, currency) {
  if (amount === null || amount === undefined || amount === "") return "";
  const value = Number(amount);
  if (Number.isNaN(value)) return "";
  const symbols = { USD: "$", CNY: "¥", EUR: "€", GBP: "£", JPY: "¥" };
  const code = String(currency || "").toUpperCase();
  const symbol = symbols[code] || (code ? `${code} ` : "");
  return `${symbol}${value.toFixed(2).replace(/\.?0+$/, "")}`;
}

function productPriceText(product) {
  const structured = moneyText(product.price_amount, product.currency);
  return structured || product.price || "价格未识别";
}

function availabilityLabel(value) {
  const labels = {
    in_stock: "有货",
    out_of_stock: "缺货",
    preorder: "预售",
    backorder: "可延期交付",
  };
  return labels[value] || value || "库存未知";
}

function productMetaText(product) {
  const parts = [];
  if (product.availability) parts.push(availabilityLabel(product.availability));
  if (product.variant_count) parts.push(`${product.variant_count} 个变体`);
  if (product.compare_at_price) parts.push(`原价 ${moneyText(product.compare_at_price, product.currency)}`);
  return parts.join(" · ");
}

function formPayload(form) {
  const formData = new FormData(form);
  const data = Object.fromEntries(formData.entries());
  Object.keys(data).forEach((key) => {
    data[key] = emptyToNull(data[key]);
  });
  if (form.querySelector('[name="notification_events"]')) {
    data.notification_events = formData.getAll("notification_events");
    if (!data.notification_events.length) data.notification_events = ["product_new"];
  }
  if ("name" in data && data.name === null) data.name = "";
  if (data.scan_interval_minutes) data.scan_interval_minutes = Number(data.scan_interval_minutes);
  if (data.priority) data.priority = Number(data.priority);
  return data;
}

function authPayload(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function setSession(data) {
  state.token = data.token;
  state.user = data.user;
}

function clearSession() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("monitor_token");
}

function showAuth(mode = "login") {
  $("#auth-screen").hidden = false;
  $("#app-shell").hidden = true;
  const form = $("#auth-form");
  form.dataset.mode = mode;
  $("#auth-title").textContent = mode === "register" ? "注册工作台账号" : "登录工作台";
  $("#auth-copy").textContent = mode === "register"
    ? "注册后即可创建自己的官网监控、产品库和通知规则。"
    : "登录后，每个用户只看到自己的官网监控、产品库和通知记录。";
  $("#auth-submit").textContent = mode === "register" ? "注册并进入" : "登录";
  $("#auth-toggle").textContent = mode === "register" ? "已有账号？去登录" : "没有账号？注册一个";
}

function showApp() {
  $("#auth-screen").hidden = true;
  $("#app-shell").hidden = false;
  $("#user-email").textContent = state.user?.email || "";
}

function selectedSite() {
  if (!state.currentSiteId) return null;
  return state.sites.find((site) => String(site.id) === String(state.currentSiteId)) || null;
}

function siteScoped(items) {
  if (!state.currentSiteId) return items;
  return items.filter((item) => String(item.site_id) === String(state.currentSiteId));
}

function scopedProducts() {
  return siteScoped(state.products);
}

function scopedChanges() {
  return siteScoped(state.changes);
}

function scopedLogs() {
  return siteScoped(state.logs);
}

function scopedJobs() {
  return siteScoped(state.jobs);
}

function scopedNotifications() {
  return siteScoped(state.notifications);
}

function scopedAuditLogs() {
  return siteScoped(state.auditLogs);
}

const notificationStatusLabels = {
  pending: "等待发送",
  sending: "发送中",
  sent: "已发送",
  failed: "发送失败",
};

const auditActionLabels = {
  "site.create": "新增官网",
  "site.reuse": "复用官网",
  "site.update": "修改官网",
  "site.delete": "删除官网",
  "source.create": "新增采集入口",
  "source.update": "修改采集入口",
  "source.delete": "删除采集入口",
  "scan.site": "手动扫描官网",
  "scan.source": "手动扫描入口",
  "notification.retry": "重试通知",
};

const changeTypeLabels = {
  product_new: "新增产品",
  price_change: "价格变化",
  availability_change: "库存变化",
  description_change: "描述变化",
  text_change: "页面文本变化",
};

function notificationStatusLabel(status) {
  return notificationStatusLabels[status] || status || "未知状态";
}

function auditActionLabel(action) {
  return auditActionLabels[action] || action || "未知操作";
}

function changeTypeLabel(type) {
  return changeTypeLabels[type] || type || "页面变化";
}

function notificationEventOptions(selected = []) {
  const active = new Set(selected.length ? selected : ["product_new"]);
  return Object.entries(changeTypeLabels).map(([value, label]) => `
    <label>
      <input type="checkbox" name="notification_events" value="${value}" ${active.has(value) ? "checked" : ""} />
      ${label}
    </label>
  `).join("");
}

function syncNotificationCheckboxes(container, selected = []) {
  const selectedSet = new Set(selected.length ? selected : ["product_new"]);
  container.querySelectorAll('input[name="notification_events"]').forEach((input) => {
    input.checked = selectedSet.has(input.value);
  });
}

function showFeedback(container, message, tone = "success") {
  const target = container.querySelector("[data-feedback]");
  if (!target) return;
  target.textContent = message;
  target.dataset.tone = tone;
}

function showToast({ type = "info", title = "提示", message = "" } = {}) {
  const stack = $("#toast-stack");
  if (!stack) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div>
      <strong>${escapeHtml(title)}</strong>
      ${message ? `<p>${escapeHtml(message)}</p>` : ""}
    </div>
    <button type="button" aria-label="关闭通知">×</button>
  `;
  toast.querySelector("button").addEventListener("click", () => closeToast(toast));
  stack.appendChild(toast);
  window.setTimeout(() => closeToast(toast), 4200);
}

function closeToast(toast) {
  if (!toast || !toast.parentElement) return;
  toast.style.opacity = "0";
  toast.style.transform = "translateY(-6px)";
  window.setTimeout(() => toast.remove(), 160);
}

function confirmAction({ title = "确认操作", message = "", confirmText = "确认", danger = false } = {}) {
  const root = $("#modal-root");
  if (!root) return Promise.resolve(window.confirm(message || title));
  return new Promise((resolve) => {
    root.innerHTML = `
      <div class="modal-backdrop" role="presentation">
        <section class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
          <h3 id="confirm-title">${escapeHtml(title)}</h3>
          ${message ? `<p>${escapeHtml(message)}</p>` : ""}
          <div class="modal-actions">
            <button class="secondary" type="button" data-modal-cancel>取消</button>
            <button class="${danger ? "danger" : ""}" type="button" data-modal-confirm>${escapeHtml(confirmText)}</button>
          </div>
        </section>
      </div>
    `;
    const close = (answer) => {
      root.innerHTML = "";
      resolve(answer);
    };
    root.querySelector("[data-modal-cancel]").addEventListener("click", () => close(false));
    root.querySelector("[data-modal-confirm]").addEventListener("click", () => close(true));
    root.querySelector(".modal-backdrop").addEventListener("click", (event) => {
      if (event.target === event.currentTarget) close(false);
    });
    root.querySelector("[data-modal-cancel]").focus();
  });
}

function confirmedProducts(items = scopedProducts()) {
  return items.filter((item) => item.item_type === "product_detail" && item.review_status !== "false_positive");
}

function extractionScore(products = confirmedProducts()) {
  if (!products.length) return 0;
  const total = products.length * 4;
  const complete = products.reduce((sum, product) => {
    return sum
      + ((product.price || product.price_amount) ? 1 : 0)
      + (product.description ? 1 : 0)
      + (product.image_url ? 1 : 0)
      + ((product.features || []).length ? 1 : 0);
  }, 0);
  return Math.round((complete / total) * 100);
}

function recentNewProducts(days = 7) {
  const since = Date.now() - days * 24 * 60 * 60 * 1000;
  return confirmedProducts().filter((product) => {
    if (product.discovery_status !== "new" || !product.detected_at) return false;
    const detectedAt = new Date(product.detected_at).getTime();
    return !Number.isNaN(detectedAt) && detectedAt >= since;
  });
}

function scopedSites() {
  const site = selectedSite();
  return site ? [site] : state.sites;
}

function scopedSources() {
  return scopedSites().flatMap((site) => site.sources || []);
}

function latestScanLog() {
  return scopedLogs()[0] || null;
}

function productResults() {
  const products = confirmedProducts(scopedProducts());
  const term = state.searchTerm.trim().toLowerCase();
  const matchesSearch = (item) => !term
    || [item.title, item.site_name, item.url, item.description, item.price, item.currency, item.availability]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term));
  const catalog = products.filter(matchesSearch);
  if (state.productFilter === "new") {
    return catalog.filter((item) => item.discovery_status === "new");
  }
  if (state.productFilter === "pending") {
    return catalog.filter((item) => (
      item.discovery_status === "new" && item.inbox_status === "unread"
    ) || item.inbox_status === "follow_up");
  }
  if (state.productFilter === "marked") {
    return catalog.filter((item) => ["read", "important", "follow_up", "archived"].includes(item.inbox_status));
  }
  return catalog;
}

function setActiveView(view) {
  state.activeView = view;
  document.querySelectorAll(".feature-tabs button").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".side-nav button").forEach((button) => {
    const active = button.dataset.sidebarView === view;
    button.classList.toggle("active", active);
    if (active) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  });
  renderActiveView();
}

async function updateInboxStatus(kind, id, inboxStatus) {
  const path = kind === "product"
    ? `/api/products/${id}/inbox-status`
    : `/api/change-events/${id}/inbox-status`;
  await api(path, {
    method: "PATCH",
    body: JSON.stringify({ inbox_status: inboxStatus }),
  });
  await loadAll();
}

async function retryNotification(id) {
  await api(`/api/notifications/${id}/retry`, { method: "POST" });
  await loadAll();
}

function renderOverview() {
  const site = selectedSite();
  const visibleSites = site ? [site] : state.sites;
  const sourceCount = visibleSites.reduce((total, item) => total + (item.sources || []).length, 0);
  const productCount = confirmedProducts().length;
  const unreadCount = scopedProducts().filter((item) => item.discovery_status === "new" && item.inbox_status === "unread").length
    + scopedChanges().filter((item) => item.inbox_status === "unread").length;
  const failedCount = scopedLogs().filter((item) => item.status === "failed").length;
  const activeJobCount = scopedJobs().filter((item) => ["queued", "running"].includes(item.status)).length;
  const pendingNotificationCount = scopedNotifications().filter((item) => ["pending", "failed"].includes(item.status)).length;

  const productCountEl = $("#count-products");
  const extractionCountEl = $("#count-extraction");
  const sourceCountEl = $("#count-sources");
  const logCountEl = $("#count-logs");
  if (productCountEl) productCountEl.textContent = productCount;
  if (extractionCountEl) extractionCountEl.textContent = recentNewProducts().length;
  if (sourceCountEl) sourceCountEl.textContent = sourceCount;
  if (logCountEl) logCountEl.textContent = unreadCount + failedCount + activeJobCount + pendingNotificationCount;
}

function renderActiveView() {
  const [title, subtitle] = viewCopy[state.activeView];
  const site = selectedSite();
  $("#current-site-label").textContent = site ? `当前官网：${site.name}` : "全部官网";
  $("#view-title").textContent = title;
  $("#view-subtitle").textContent = subtitle;
  $("#view-actions").innerHTML = "";

  if (state.activeView === "products") renderProductsView();
  if (state.activeView === "extraction") renderExtractionView();
  if (state.activeView === "sources") renderSourcesView();
  if (state.activeView === "logs") renderLogsView();
}

function renderProductFilters() {
  const products = confirmedProducts(scopedProducts());
  const counts = {
    catalog: products.length,
    new: products.filter((item) => item.discovery_status === "new").length,
    pending: products.filter((item) => (
      item.discovery_status === "new" && item.inbox_status === "unread"
    ) || item.inbox_status === "follow_up").length,
    marked: products.filter((item) => ["read", "important", "follow_up", "archived"].includes(item.inbox_status)).length,
  };
  const filters = [
    ["catalog", "全部商品", counts.catalog],
    ["new", "新增商品", counts.new],
    ["pending", "待处理", counts.pending],
    ["marked", "已标注", counts.marked],
  ];
  $("#view-actions").innerHTML = `
    <div class="filter-tabs" id="product-filter">
      ${filters.map(([key, label, count]) => `
        <button class="${state.productFilter === key ? "active" : ""}" data-filter="${key}">
          <span>${label}</span>
          <b>${count}</b>
        </button>
      `).join("")}
    </div>
    <button class="secondary" id="export-products-csv" type="button">导出 CSV</button>
  `;
  $("#product-filter").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) return;
    state.productFilter = button.dataset.filter;
    renderActiveView();
  });
  $("#export-products-csv").addEventListener("click", async () => {
    try {
      await downloadCsv(scopedExportPath("/api/export/products.csv"), "products.csv");
      showToast({ type: "success", title: "导出已开始", message: "产品库 CSV 正在下载。" });
    } catch (error) {
      showToast({ type: "error", title: "导出失败", message: error.message });
    }
  });
}

function nextInboxStatus(currentStatus, targetStatus) {
  return currentStatus === targetStatus ? "unread" : targetStatus;
}

function renderProductsView() {
  renderProductFilters();
  const root = $("#view-content");
  const products = productResults();
  if (!products.length) {
    const latestLog = latestScanLog();
    const sources = scopedSources();
    const baselineDone = sources.filter((source) => source.baseline_completed_at).length;
    const sourceCount = sources.length;
    const statusRows = [
      ["采集范围", sourceCount ? `${baselineDone}/${sourceCount} 已建基线` : "还没有采集范围"],
      ["最近扫描", latestLog ? `${latestLog.candidates_count} 个候选链接` : "暂无扫描记录"],
      ["新增产品", latestLog ? `${latestLog.new_count} 个` : "等待检查"],
    ];
    root.innerHTML = `
      <div class="empty-state">
        <div>
          <strong>当前还没有盘点到产品详情页。</strong>
          <p>系统会先从官网、Sitemap、RSS 或产品列表页找到产品详情链接，再提取价格、图片、功能和卖点。已经存在的商品会标为“基线产品”，后续新出现的商品会标为“新增”。</p>
        </div>
        <div class="empty-metrics">
          ${statusRows.map(([label, value]) => `
            <div>
              <span>${label}</span>
              <strong>${value}</strong>
            </div>
          `).join("")}
        </div>
        <div class="empty-note">
          ${latestLog
            ? `最近一次检查结果：${escapeHtml(latestLog.message || `发现 ${latestLog.new_count} 个新品`)}。`
            : "在顶部输入官网后，系统会先建立基线并盘点当前产品。后续新增产品会用“新增”标记区分。"}
        </div>
        <button id="show-sources-from-empty" type="button">查看采集范围设置</button>
      </div>`;
    $("#show-sources-from-empty").addEventListener("click", () => setActiveView("sources"));
    return;
  }
  renderProductsTable(root, products);
  return;
  const template = $("#product-template");
  root.innerHTML = "";
  const list = document.createElement("div");
  list.className = "product-list";
  products.forEach((product) => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector(".product-card");
    const isNew = product.discovery_status === "new";
    card.classList.toggle("new-product", isNew);
    const image = node.querySelector(".product-image");
    image.src = product.image_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='220'%3E%3Crect width='100%25' height='100%25' fill='%23e8ecf2'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dominant-baseline='middle' fill='%23687385' font-family='Arial' font-size='18'%3ENo Image%3C/text%3E%3C/svg%3E";
    image.alt = product.title;
    node.querySelector(".eyebrow").innerHTML = `
      <span class="product-badge ${isNew ? "new" : "baseline"}">${isNew ? "新增" : "基线产品"}</span>
      ${confidenceBadge(product)}
      ${escapeHtml(product.site_name)} · ${sourceTypeLabels[product.source_type] || "采集入口"} · ${itemTypeLabels[product.item_type] || "待复核"}
    `;
    node.querySelector("h3").textContent = product.title;
    node.querySelector(".price").textContent = productPriceText(product);
    node.querySelector(".desc").textContent = [product.description || "暂无描述", productMetaText(product)].filter(Boolean).join(" · ");
    const features = node.querySelector(".features");
    displayFeatures(product.features).forEach((feature) => {
      const li = document.createElement("li");
      li.textContent = feature;
      features.appendChild(li);
    });
    if (!features.children.length) {
      const li = document.createElement("li");
      li.textContent = "待补充卖点";
      features.appendChild(li);
    }
    node.querySelector(".time").textContent = `发现于 ${formatTime(product.detected_at)}`;
    const link = node.querySelector(".product-foot a");
    link.textContent = product.link_label || (product.item_type === "product_detail" ? "查看产品" : "查看来源页");
    if (product.display_url || product.url) {
      link.href = product.display_url || product.url;
      link.removeAttribute("aria-disabled");
    } else {
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
      link.textContent = "暂无链接";
    }
    node.querySelectorAll(".inbox-actions button").forEach((button) => {
      const status = button.dataset.status;
      const active = product.inbox_status === status;
      button.classList.toggle("active", active);
      button.title = active ? "再次点击取消标注" : `标记为${button.textContent}`;
      button.addEventListener("click", () => updateInboxStatus("product", product.id, nextInboxStatus(product.inbox_status, status)));
    });
    list.appendChild(node);
  });
  root.appendChild(list);
}

function discoveryBadge(product) {
  const isNew = product.discovery_status === "new";
  return `<span class="status-badge ${isNew ? "new" : "neutral"}">${isNew ? "新增" : "基线"}</span>`;
}

function inboxBadge(status) {
  const tone = status === "important" ? "hot" : status === "follow_up" ? "warn" : status === "archived" ? "neutral" : "new";
  return `<span class="status-badge ${tone}">${escapeHtml(inboxStatusLabels[status] || "未读")}</span>`;
}

function availabilityBadge(value) {
  const text = value || "库存未知";
  const normalized = String(text).toLowerCase();
  const tone = normalized.includes("out") || normalized.includes("缺") || normalized.includes("sold") ? "warn" : "neutral";
  return `<span class="status-badge ${tone}">${escapeHtml(text)}</span>`;
}

function renderProductsTable(root, products) {
  root.innerHTML = `
    <section class="data-table-shell" aria-label="产品监控表格">
      <table class="data-table">
        <thead>
          <tr>
            <th>商品</th>
            <th>状态</th>
            <th>价格</th>
            <th>库存/变体</th>
            <th>来源与置信度</th>
            <th>发现时间</th>
            <th>处理</th>
          </tr>
        </thead>
        <tbody>
          ${products.map((product) => {
            const url = product.display_url || product.url || "";
            return `
              <tr>
                <td>
                  <div class="table-title">
                    <strong>${escapeHtml(product.title)}</strong>
                    <span>${escapeHtml(product.site_name)} · ${escapeHtml(itemTypeLabels[product.item_type] || "待复核")}</span>
                  </div>
                </td>
                <td>${discoveryBadge(product)} ${inboxBadge(product.inbox_status)}</td>
                <td><strong>${escapeHtml(productPriceText(product))}</strong></td>
                <td>${availabilityBadge(productMetaText(product) || product.availability)}</td>
                <td>
                  <div class="table-title compact">
                    <strong>${escapeHtml(sourceTypeLabels[product.source_type] || "采集入口")}</strong>
                    <span>${escapeHtml(confidenceText(product))}</span>
                  </div>
                </td>
                <td>${formatTime(product.detected_at)}</td>
                <td>
                  <div class="row-actions">
                    <button type="button" data-product-status="${product.id}:important">重点</button>
                    <button type="button" data-product-status="${product.id}:follow_up">跟进</button>
                    ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开</a>` : ""}
                  </div>
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </section>
    <div class="product-list product-list-fallback">
      ${products.map((product) => {
        const url = product.display_url || product.url || "";
        return `
          <article class="product-card ${product.discovery_status === "new" ? "new-product" : ""}">
            <div class="eyebrow">${discoveryBadge(product)} ${confidenceBadge(product)} ${escapeHtml(product.site_name)}</div>
            <h3>${escapeHtml(product.title)}</h3>
            <p class="price">${escapeHtml(productPriceText(product))}</p>
            <p class="desc">${escapeHtml([product.description || "暂无描述", productMetaText(product)].filter(Boolean).join(" · "))}</p>
            <div class="product-foot">
              <span class="time">发现于 ${formatTime(product.detected_at)}</span>
              ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开</a>` : ""}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
  root.querySelectorAll("[data-product-status]").forEach((button) => {
    button.addEventListener("click", () => {
      const [id, status] = button.dataset.productStatus.split(":");
      const product = products.find((item) => String(item.id) === id);
      updateInboxStatus("product", id, nextInboxStatus(product?.inbox_status, status));
    });
  });
}

function renderExtractionView() {
  const root = $("#view-content");
  const term = state.searchTerm.trim().toLowerCase();
  const products = confirmedProducts().filter((product) => !term
    || [product.title, product.site_name, product.url, product.description, product.price, product.currency, product.availability]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term)));
  if (!products.length) {
    root.innerHTML = `
      <div class="empty">
        <strong>还没有可提取的新品详情。</strong><br>
        系统发现真正的产品详情页后，会在这里拆解价格、图片、描述、功能卖点和待补充字段。
      </div>`;
    return;
  }

  root.innerHTML = `
    <div class="extraction-summary">
      <div>
        <span>已提取产品</span>
        <strong>${products.length}</strong>
        <small>当前筛选范围内</small>
      </div>
      <div>
        <span>已识别价格</span>
        <strong>${products.filter((item) => item.price || item.price_amount).length}</strong>
        <small>${products.length} 个产品中</small>
      </div>
      <div>
        <span>有功能卖点</span>
        <strong>${products.filter((item) => displayFeatures(item.features).length).length}</strong>
        <small>可用于选品和竞品分析</small>
      </div>
    </div>
    <div class="intel-list">${products.map((product) => {
      const features = displayFeatures(product.features, 5);
      const missing = [
        (product.price || product.price_amount) ? null : "价格",
        product.description ? null : "描述",
        product.image_url ? null : "图片",
        features.length ? null : "卖点",
      ].filter(Boolean);
      const productUrl = product.display_url || product.url || "";
      return `
        <article class="intel-card intel-product">
          <div class="intel-main">
            <div class="intel-title-row">
              <div>
                <span class="eyebrow">${escapeHtml(product.site_name)} · ${formatTime(product.detected_at)}</span>
                <h3>${escapeHtml(product.title)}</h3>
                ${confidenceBadge(product)}
              </div>
                <strong class="intel-price">${escapeHtml(productPriceText(product))}</strong>
            </div>
            <p class="intel-desc">${escapeHtml(product.description || "暂无描述，后续可通过更精准的产品页规则补充。")}</p>
            <div class="intel-feature-block">
              <span>功能卖点</span>
              <ul class="intel-feature-list">
                ${features.length
                  ? features.map((feature) => `<li>${escapeHtml(feature)}</li>`).join("")
                  : '<li class="muted">待补充卖点</li>'}
              </ul>
            </div>
          </div>
          <aside class="intel-side">
            <div>
              <span>信息状态</span>
              <strong>${product.review_status === "needs_review" ? "待人工复核" : (missing.length ? `待补 ${missing.join("、")}` : "信息完整")}</strong>
            </div>
            <div>
              <span>可信度</span>
              <strong>${escapeHtml(confidenceText(product))}</strong>
            </div>
            <div>
              <span>库存/变体</span>
              <strong>${escapeHtml(productMetaText(product) || "库存未知")}</strong>
            </div>
            ${productUrl
              ? `<a href="${escapeHtml(productUrl)}" target="_blank" rel="noreferrer">${escapeHtml(product.link_label || "查看产品")}</a>`
              : '<span class="disabled-link">暂无链接</span>'}
          </aside>
        </article>
      `;
    }).join("")}</div>
  `;
}

function renderChangesView() {
  const root = $("#view-content");
  const changes = scopedChanges();
  if (!changes.length) {
    root.innerHTML = '<div class="empty">还没有页面变化。采集入口完成基线后，后续文本变化会显示在这里。</div>';
    return;
  }
  root.innerHTML = `<div class="change-list">${changes.slice(0, 50).map((event) => {
    const diff = (event.diff || []).slice(0, 12).map((item) => {
      if (item.type === "changed") {
        return `<span class="diff-line changed"><b>~</b>${escapeHtml(item.field || "字段")}：${escapeHtml(item.before ?? "空")} → ${escapeHtml(item.after ?? "空")}</span>`;
      }
      const cls = item.type === "added" ? "added" : "removed";
      const prefix = item.type === "added" ? "+" : "-";
      return `<span class="diff-line ${cls}"><b>${prefix}</b>${escapeHtml(item.text || "")}</span>`;
    }).join("");
    const eventTitle = event.product_title || event.site_name;
    const eventUrl = event.product_url || event.source_url;
    return `
      <article class="change-card ${event.severity === "high" ? "high" : ""}">
        <div class="change-head">
          <div>
            <strong>${escapeHtml(eventTitle)}</strong>
            <span>${changeTypeLabel(event.change_type)} · ${sourceTypeLabels[event.source_type] || "采集入口"} · ${formatTime(event.created_at)} · ${inboxStatusLabels[event.inbox_status] || "未读"}</span>
          </div>
          <a href="${eventUrl}" target="_blank" rel="noreferrer">打开来源</a>
        </div>
        <p>${escapeHtml(event.summary || "页面发生变化")}</p>
        <div class="diff-box">${diff || '<span class="muted">没有可展示的文本片段</span>'}</div>
        <div class="inbox-actions" data-kind="change" data-id="${event.id}">
          <button data-status="read">已读</button>
          <button data-status="important">重要</button>
          <button data-status="follow_up">待跟进</button>
          <button data-status="archived">归档</button>
        </div>
      </article>
    `;
  }).join("")}</div>`;
  root.querySelectorAll(".inbox-actions").forEach((group) => {
    group.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        const event = state.changes.find((item) => String(item.id) === String(group.dataset.id));
        updateInboxStatus("change", group.dataset.id, nextInboxStatus(event?.inbox_status, button.dataset.status));
      });
    });
  });
}

function renderSourcesView() {
  const root = $("#view-content");
  const term = state.searchTerm.trim().toLowerCase();
  const baseSites = selectedSite() ? [selectedSite()] : state.sites;
  const sites = baseSites.filter((site) => !term
    || [site.name, site.url, site.category]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term)));
  if (!sites.length) {
    root.innerHTML = '<div class="empty">还没有官网。先在顶部输入官网网址并开始监控。</div>';
    return;
  }
  root.innerHTML = `<div class="site-grid">${sites.map((site) => `
    <article class="site-card" data-site-id="${site.id}">
      <div class="source-explainer">
        <strong>这和产品库有什么区别？</strong>
        <div class="source-explain-grid">
          <p><b>产品库</b> 是结果页：看系统已经找到哪些商品、哪些是新增、价格和卖点是什么。</p>
          <p><b>采集范围</b> 是设置页：告诉系统还要去哪些页面找商品，通常只有发现商品不全时才需要调整。</p>
        </div>
      </div>
      <div class="site-title">
        <div>
          <span class="section-kicker">正在监控的官网</span>
          <h3>${escapeHtml(site.name)}</h3>
          <a href="${site.url}" target="_blank" rel="noreferrer">${escapeHtml(site.url)}</a>
        </div>
        <span class="status ${site.enabled ? "" : "off"}">${site.enabled ? "监控中" : "已暂停"}</span>
      </div>
      <div class="site-status-grid">
        <div><span>品类</span><strong>${escapeHtml(site.category || "未分类")}</strong></div>
        <div><span>优先级</span><strong>${priorityLabels[site.priority] || "中优先级"}</strong></div>
        <div><span>最近检查</span><strong>${formatTime(site.last_checked_at)}</strong></div>
        <div><span>检查结果</span><strong>${escapeHtml(site.last_status || "等待检查")}</strong></div>
      </div>
      ${renderSiteSettingsForm(site)}
      <div class="notification-policy site-policy">
        <strong>Webhook 通知事件</strong>
        <div class="policy-options">${notificationEventOptions(site.notification_events || ["product_new"])}</div>
        <button class="secondary" data-action="save-notification-policy" type="button">保存通知策略</button>
        <span class="form-feedback" data-feedback></span>
      </div>
      <div class="actions">
        <button data-action="scan-site">检查官网</button>
        <button data-action="toggle-site">${site.enabled ? "暂停官网" : "启用官网"}</button>
        <button class="danger" data-action="delete-site">删除</button>
      </div>
      <div class="source-head">
        <div>
          <strong>采集入口列表</strong>
          <p>每一行代表系统会定期检查的页面。入口越准确，产品发现越完整。</p>
        </div>
        <span>${(site.sources || []).length} 个采集入口</span>
      </div>
      <div class="sources">${renderSourceRows(site.sources || [])}</div>
      ${renderSourceForm()}
    </article>
  `).join("")}</div>`;

  root.querySelectorAll(".site-card").forEach((card) => {
    const site = state.sites.find((item) => String(item.id) === card.dataset.siteId);
    bindSiteCard(card, site);
  });
}

function intervalSelect(value = 60) {
  const intervals = [
    [30, "30 分钟"],
    [60, "1 小时"],
    [180, "3 小时"],
    [360, "6 小时"],
    [720, "12 小时"],
  ];
  return `
    <select name="scan_interval_minutes">
      ${intervals.map(([minutes, label]) => `<option value="${minutes}" ${Number(value) === minutes ? "selected" : ""}>${label}</option>`).join("")}
    </select>
  `;
}

function renderSiteSettingsForm(site) {
  return `
    <form class="site-settings-form">
      <label>
        品类
        <input name="category" value="${escapeHtml(site.category || "")}" placeholder="例如 3C / 家电 / 户外" />
      </label>
      <label>
        优先级
        <select name="priority">
          <option value="1" ${Number(site.priority) === 1 ? "selected" : ""}>高优先级</option>
          <option value="2" ${Number(site.priority || 2) === 2 ? "selected" : ""}>中优先级</option>
          <option value="3" ${Number(site.priority) === 3 ? "selected" : ""}>低优先级</option>
        </select>
      </label>
      <label>
        官网检查间隔
        ${intervalSelect(site.scan_interval_minutes || 60)}
      </label>
      <label>
        包含关键词
        <input name="include_keywords" value="${escapeHtml(site.include_keywords || "")}" placeholder="new, launch, 新品" />
      </label>
      <label>
        排除关键词
        <input name="exclude_keywords" value="${escapeHtml(site.exclude_keywords || "")}" placeholder="sale, outlet, 二手" />
      </label>
      <button class="secondary" data-action="save-site-settings" type="submit">保存官网设置</button>
      <span class="form-feedback" data-feedback></span>
    </form>
  `;
}

function renderSourceRows(sources) {
  if (!sources.length) return '<div class="source-row muted">暂无采集入口</div>';
  return sources.map((source) => {
    const baseline = source.baseline_completed_at ? "基线完成" : "待基线";
    return `
      <div class="source-row" data-source-id="${source.id}">
        <div class="source-main">
          <strong>${sourceTypeLabels[source.source_type] || source.source_type}</strong>
          <a href="${source.url}" target="_blank" rel="noreferrer">${escapeHtml(source.url)}</a>
          <span>${baseline} · ${source.selector ? `只看页面中的 ${escapeHtml(source.selector)} · ` : ""}${escapeHtml(source.last_status || "等待检查")} · 最近检查 ${formatTime(source.last_checked_at)}</span>
        </div>
        <form class="source-edit-form">
          <input name="url" value="${escapeHtml(source.url)}" required />
          <input name="selector" value="${escapeHtml(source.selector || "")}" placeholder="页面区域 CSS，可选" />
          <input name="include_keywords" value="${escapeHtml(source.include_keywords || "")}" placeholder="包含词" />
          <input name="exclude_keywords" value="${escapeHtml(source.exclude_keywords || "")}" placeholder="排除词" />
          ${intervalSelect(source.scan_interval_minutes || 60)}
          <button class="secondary" data-action="save-source" type="submit">保存入口</button>
          <span class="form-feedback" data-feedback></span>
        </form>
        <div class="source-actions">
          <button data-action="scan-source">检查</button>
          <button data-action="toggle-source">${source.enabled ? "暂停" : "启用"}</button>
          <button class="danger" data-action="delete-source">删除</button>
        </div>
      </div>
    `;
  }).join("");
}

function renderSourceForm() {
  return `
    <form class="source-form">
      <select name="source_type">
        <option value="listing_page">产品列表页（最常用）</option>
        <option value="homepage">官网首页（默认入口）</option>
        <option value="sitemap">Sitemap 站点地图</option>
        <option value="rss">RSS 订阅</option>
        <option value="news_page">新品发布 / 新闻页</option>
        <option value="custom_page">自定义页面</option>
      </select>
      <input name="url" required placeholder="要采集的页面 URL" />
      <input name="selector" placeholder="页面区域 CSS，可选" />
      <input name="include_keywords" placeholder="包含词" />
      <input name="exclude_keywords" placeholder="排除词" />
      ${intervalSelect(60)}
      <button type="submit">添加采集入口</button>
      <span class="form-feedback" data-feedback></span>
      <div class="source-type-guide">
        <div><strong>产品列表页</strong><span>商品集中展示页，最适合补全产品库。</span></div>
        <div><strong>官网首页</strong><span>默认入口，适合首次建立基线。</span></div>
        <div><strong>Sitemap</strong><span>网站地图，通常能发现最多产品链接。</span></div>
        <div><strong>RSS</strong><span>订阅新品文章或发布动态。</span></div>
        <div><strong>新品发布页</strong><span>品牌有 Launch / News 页面时使用。</span></div>
        <div><strong>自定义页面</strong><span>只想盯某个页面或区域时使用。</span></div>
      </div>
    </form>
  `;
}

function bindSiteCard(card, site) {
  const settingsForm = card.querySelector(".site-settings-form");
  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = settingsForm.querySelector('[data-action="save-site-settings"]');
    button.disabled = true;
    showFeedback(settingsForm, "正在保存...");
    try {
      await api(`/api/sites/${site.id}`, {
        method: "PATCH",
        body: JSON.stringify(formPayload(settingsForm)),
      });
      showFeedback(settingsForm, "保存成功");
      await loadAll();
    } catch (error) {
      showFeedback(settingsForm, error.message, "error");
    } finally {
      button.disabled = false;
    }
  });
  syncNotificationCheckboxes(card.querySelector(".site-policy"), site.notification_events || ["product_new"]);
  card.querySelector('[data-action="scan-site"]').addEventListener("click", async () => {
    await api(`/api/sites/${site.id}/scan`, { method: "POST" });
    await loadAll();
  });
  card.querySelector('[data-action="toggle-site"]').addEventListener("click", async () => {
    await api(`/api/sites/${site.id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled: !site.enabled }),
    });
    await loadAll();
  });
  card.querySelector('[data-action="save-notification-policy"]').addEventListener("click", async () => {
    const selected = Array.from(card.querySelectorAll('.site-policy input[name="notification_events"]:checked'))
      .map((input) => input.value);
    await api(`/api/sites/${site.id}`, {
      method: "PATCH",
      body: JSON.stringify({ notification_events: selected.length ? selected : ["product_new"] }),
    });
    showFeedback(card.querySelector(".site-policy"), "保存成功");
    await loadAll();
  });
  card.querySelector('[data-action="delete-site"]').addEventListener("click", async () => {
    const confirmed = await confirmAction({
      title: "删除监控站点",
      message: `删除 ${site.name} 的监控和历史记录？此操作不可撤销。`,
      confirmText: "删除",
      danger: true,
    });
    if (!confirmed) return;
    await api(`/api/sites/${site.id}`, { method: "DELETE" });
    showToast({ type: "success", title: "已删除站点", message: `${site.name} 已从监控列表移除。` });
    await loadAll();
  });
  card.querySelectorAll(".source-row[data-source-id]").forEach((row) => {
    const source = (site.sources || []).find((item) => String(item.id) === row.dataset.sourceId);
    const sourceForm = row.querySelector(".source-edit-form");
    sourceForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = sourceForm.querySelector('[data-action="save-source"]');
      button.disabled = true;
      showFeedback(sourceForm, "正在保存...");
      try {
        await api(`/api/sources/${source.id}`, {
          method: "PATCH",
          body: JSON.stringify(formPayload(sourceForm)),
        });
        showFeedback(sourceForm, "保存成功");
        await loadAll();
      } catch (error) {
        showFeedback(sourceForm, error.message, "error");
      } finally {
        button.disabled = false;
      }
    });
    row.querySelector('[data-action="scan-source"]').addEventListener("click", async () => {
      await api(`/api/sources/${source.id}/scan`, { method: "POST" });
      await loadAll();
    });
    row.querySelector('[data-action="toggle-source"]').addEventListener("click", async () => {
      await api(`/api/sources/${source.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      await loadAll();
    });
    row.querySelector('[data-action="delete-source"]').addEventListener("click", async () => {
      const confirmed = await confirmAction({
        title: "删除采集入口",
        message: "删除后该入口不会再参与扫描，历史记录会保留在审计日志中。",
        confirmText: "删除",
        danger: true,
      });
      if (!confirmed) return;
      await api(`/api/sources/${source.id}`, { method: "DELETE" });
      showToast({ type: "success", title: "已删除采集入口", message: "后续扫描不会再使用该入口。" });
      await loadAll();
    });
  });
  card.querySelector(".source-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    await api(`/api/sites/${site.id}/sources`, {
      method: "POST",
      body: JSON.stringify(formPayload(form)),
    });
    showFeedback(form, "已添加采集入口");
    form.reset();
    await loadAll();
  });
}

function renderLogsView() {
  const root = $("#view-content");
  const jobs = scopedJobs();
  const notifications = scopedNotifications();
  const auditLogs = scopedAuditLogs();
  const logs = scopedLogs();
  const changes = scopedChanges();
  renderLogsWorkbench(root, { jobs, notifications, auditLogs, logs, changes });
  return;
  $("#view-actions").innerHTML = '<button class="secondary" id="export-notifications-csv" type="button">导出通知 CSV</button>';
  $("#export-notifications-csv").addEventListener("click", async () => {
    try {
      await downloadCsv(scopedExportPath("/api/export/notifications.csv"), "notifications.csv");
    } catch (error) {
      alert(error.message);
    }
  });
  if (!jobs.length && !notifications.length && !auditLogs.length && !logs.length && !changes.length) {
    root.innerHTML = '<div class="empty">还没有提醒或扫描日志。</div>';
    return;
  }
  const unreadChanges = changes.filter((item) => item.inbox_status !== "archived").slice(0, 10);
  root.innerHTML = `
    ${jobs.length ? `
      <div class="job-list">
        ${jobs.slice(0, 20).map((job) => `
          <article class="job-row ${job.status}">
            <div>
              <strong>${escapeHtml(job.site_name)}</strong>
              <span>${job.job_type === "site_scan" ? "品牌扫描" : (sourceTypeLabels[job.source_type] || "采集源扫描")} · ${job.trigger_type} · ${formatTime(job.queued_at)}</span>
            </div>
            <div>
              <span>${job.status} · 候选 ${job.candidates_count} · 新品 ${job.new_count} · 错误 ${job.error_count}</span>
              <p>${escapeHtml(job.message || "等待扫描结果")}</p>
            </div>
          </article>
        `).join("")}
      </div>` : ""}
    ${notifications.length ? `
      <div class="notification-list">
        ${notifications.slice(0, 40).map((item) => `
          <article class="notification-row ${item.status}">
            <div>
              <strong>${escapeHtml(item.product_title || item.event_summary || "事件通知")}</strong>
              <span>${escapeHtml(item.site_name)} · ${changeTypeLabel(item.event_type || item.change_type)} · ${notificationStatusLabel(item.status)} · 尝试 ${item.attempts}/${item.max_attempts}</span>
            </div>
            <div>
              <span>${item.sent_at ? `发送于 ${formatTime(item.sent_at)}` : `下次尝试 ${formatTime(item.next_attempt_at)}`}</span>
              <p>${escapeHtml(item.last_error || item.product_url || item.target_url || "")}</p>
            </div>
            <div class="notification-actions">
              ${item.product_url ? `<a href="${escapeHtml(item.product_url)}" target="_blank" rel="noreferrer">查看产品</a>` : ""}
              ${["failed", "pending"].includes(item.status) ? `<button data-retry-notification="${item.id}" type="button">重试</button>` : ""}
            </div>
          </article>
        `).join("")}
      </div>` : ""}
    ${auditLogs.length ? `
      <div class="log-list">
        ${auditLogs.slice(0, 30).map((item) => `
          <article class="log-row">
            <div>
              <strong>${auditActionLabel(item.action)}</strong>
              <span>${escapeHtml(item.site_name || item.site_url || "已删除对象")} · ${formatTime(item.created_at)}</span>
            </div>
            <div>
              <span>${escapeHtml(item.entity_type || "")} #${item.entity_id || "-"}</span>
              <p>${escapeHtml(item.summary || "")}</p>
            </div>
          </article>
        `).join("")}
      </div>` : ""}
    ${unreadChanges.length ? `
      <div class="alert-list">
        ${unreadChanges.map((event) => {
          const eventTitle = event.product_title || event.site_name;
          const eventUrl = event.product_url || event.source_url;
          return `
            <article class="change-card ${event.severity === "high" ? "high" : ""}">
              <div class="change-head">
                <div>
                  <strong>${escapeHtml(eventTitle)}</strong>
                  <span>${changeTypeLabel(event.change_type)} · ${formatTime(event.created_at)} · ${inboxStatusLabels[event.inbox_status] || "未读"}</span>
                </div>
                <a href="${eventUrl}" target="_blank" rel="noreferrer">打开来源</a>
              </div>
              <p>${escapeHtml(event.summary || "页面发生变化")}</p>
            </article>
          `;
        }).join("")}
      </div>` : ""}
    <div class="log-list">${logs.slice(0, 80).map((log) => `
      <article class="log-row ${log.status === "failed" ? "failed" : ""}">
        <div>
          <strong>${escapeHtml(log.site_name)}</strong>
          <span>${sourceTypeLabels[log.source_type] || "品牌"} · ${log.mode} · ${formatTime(log.started_at)}</span>
        </div>
        <div>
          <span>候选 ${log.candidates_count} · 新品 ${log.new_count}</span>
          <p>${escapeHtml(log.message || "")}</p>
        </div>
      </article>
    `).join("")}</div>
  `;
  root.querySelectorAll("[data-retry-notification]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "重试中";
      try {
        await retryNotification(button.dataset.retryNotification);
      } catch (error) {
        showToast({ type: "error", title: "重试失败", message: error.message });
        button.disabled = false;
        button.textContent = "重试";
      }
    });
  });
}

function logTabCounts({ jobs, notifications, auditLogs, logs, changes }) {
  return {
    jobs: jobs.length + logs.length,
    changes: changes.filter((item) => item.inbox_status !== "archived").length,
    notifications: notifications.length,
    audit: auditLogs.length,
  };
}

function renderLogsWorkbench(root, data) {
  const counts = logTabCounts(data);
  const tabs = [
    ["jobs", "扫描任务", counts.jobs],
    ["changes", "变更事件", counts.changes],
    ["notifications", "通知发送", counts.notifications],
    ["audit", "审计日志", counts.audit],
  ];
  if (!tabs.some(([, , count]) => count)) {
    $("#view-actions").innerHTML = "";
    root.innerHTML = '<div class="empty">还没有提醒或扫描日志。</div>';
    return;
  }
  if (!tabs.some(([key]) => key === state.logTab)) state.logTab = "jobs";
  $("#view-actions").innerHTML = '<button class="secondary" id="export-notifications-csv" type="button">导出通知 CSV</button>';
  $("#export-notifications-csv").addEventListener("click", async () => {
    try {
      await downloadCsv(scopedExportPath("/api/export/notifications.csv"), "notifications.csv");
      showToast({ type: "success", title: "导出已开始", message: "通知 CSV 正在下载。" });
    } catch (error) {
      showToast({ type: "error", title: "导出失败", message: error.message });
    }
  });
  root.innerHTML = `
    <div class="log-tabs" role="tablist" aria-label="日志分类">
      ${tabs.map(([key, label, count]) => `
        <button type="button" role="tab" aria-selected="${state.logTab === key}" class="${state.logTab === key ? "active" : ""}" data-log-tab="${key}">
          <span>${label}</span>
          <b>${count}</b>
        </button>
      `).join("")}
    </div>
    <section class="log-panel">
      ${state.logTab === "changes" ? renderChangeEventsPanel(data.changes) : ""}
      ${state.logTab === "notifications" ? renderNotificationsPanel(data.notifications) : ""}
      ${state.logTab === "audit" ? renderAuditLogsPanel(data.auditLogs) : ""}
      ${state.logTab === "jobs" ? renderScanJobsPanel(data.jobs, data.logs) : ""}
    </section>
  `;
  root.querySelectorAll("[data-log-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.logTab = button.dataset.logTab;
      renderLogsView();
    });
  });
  root.querySelectorAll("[data-retry-notification]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "重试中";
      try {
        await retryNotification(button.dataset.retryNotification);
        showToast({ type: "success", title: "已重新排队", message: "通知任务会在后台重新发送。" });
      } catch (error) {
        showToast({ type: "error", title: "重试失败", message: error.message });
        button.disabled = false;
        button.textContent = "重试";
      }
    });
  });
}

function renderScanJobsPanel(jobs, logs) {
  const rows = [
    ...jobs.slice(0, 20).map((job) => ({
      title: job.site_name,
      status: job.status,
      meta: `${job.job_type === "site_scan" ? "品牌扫描" : (sourceTypeLabels[job.source_type] || "采集源扫描")} · ${job.trigger_type} · ${formatTime(job.queued_at)}`,
      stats: `候选 ${job.candidates_count} · 新品 ${job.new_count} · 错误 ${job.error_count}`,
      message: job.message || "等待扫描结果",
    })),
    ...logs.slice(0, 40).map((log) => ({
      title: log.site_name,
      status: log.status,
      meta: `${sourceTypeLabels[log.source_type] || "品牌"} · ${log.mode} · ${formatTime(log.started_at)}`,
      stats: `候选 ${log.candidates_count} · 新品 ${log.new_count}`,
      message: log.message || "",
    })),
  ];
  if (!rows.length) return '<div class="empty">暂无扫描任务。</div>';
  return `<div class="log-list">${rows.map((row) => `
    <article class="log-row ${row.status === "failed" ? "failed" : ""}">
      <div>
        <strong>${escapeHtml(row.title)}</strong>
        <span>${escapeHtml(row.meta)}</span>
      </div>
      <div>
        <span>${escapeHtml(row.status)} · ${escapeHtml(row.stats)}</span>
        <p>${escapeHtml(row.message)}</p>
      </div>
    </article>
  `).join("")}</div>`;
}

function renderChangeEventsPanel(changes) {
  const unreadChanges = changes.filter((item) => item.inbox_status !== "archived").slice(0, 30);
  if (!unreadChanges.length) return '<div class="empty">暂无待处理变更。</div>';
  return `<div class="alert-list">${unreadChanges.map((event) => {
    const eventTitle = event.product_title || event.site_name;
    const eventUrl = event.product_url || event.source_url;
    return `
      <article class="change-card ${event.severity === "high" ? "high" : ""}">
        <div class="change-head">
          <div>
            <strong>${escapeHtml(eventTitle)}</strong>
            <span>${changeTypeLabel(event.change_type)} · ${formatTime(event.created_at)} · ${escapeHtml(inboxStatusLabels[event.inbox_status] || "未读")}</span>
          </div>
          ${eventUrl ? `<a href="${escapeHtml(eventUrl)}" target="_blank" rel="noreferrer">打开来源</a>` : ""}
        </div>
        <p>${escapeHtml(event.summary || "页面发生变化")}</p>
      </article>
    `;
  }).join("")}</div>`;
}

function renderNotificationsPanel(notifications) {
  if (!notifications.length) return '<div class="empty">暂无通知发送记录。</div>';
  return `<div class="notification-list">${notifications.slice(0, 50).map((item) => `
    <article class="notification-row ${item.status}">
      <div>
        <strong>${escapeHtml(item.product_title || item.event_summary || "事件通知")}</strong>
        <span>${escapeHtml(item.site_name)} · ${changeTypeLabel(item.event_type || item.change_type)} · ${notificationStatusLabel(item.status)} · 尝试 ${item.attempts}/${item.max_attempts}</span>
      </div>
      <div>
        <span>${item.sent_at ? `发送于 ${formatTime(item.sent_at)}` : `下次尝试 ${formatTime(item.next_attempt_at)}`}</span>
        <p>${escapeHtml(item.last_error || item.product_url || item.target_url || "")}</p>
      </div>
      <div class="notification-actions">
        ${item.product_url ? `<a href="${escapeHtml(item.product_url)}" target="_blank" rel="noreferrer">查看产品</a>` : ""}
        ${["failed", "pending"].includes(item.status) ? `<button data-retry-notification="${item.id}" type="button">重试</button>` : ""}
      </div>
    </article>
  `).join("")}</div>`;
}

function renderAuditLogsPanel(auditLogs) {
  if (!auditLogs.length) return '<div class="empty">暂无审计日志。</div>';
  return `<div class="log-list">${auditLogs.slice(0, 50).map((item) => `
    <article class="log-row">
      <div>
        <strong>${auditActionLabel(item.action)}</strong>
        <span>${escapeHtml(item.site_name || item.site_url || "已删除对象")} · ${formatTime(item.created_at)}</span>
      </div>
      <div>
        <span>${escapeHtml(item.entity_type || "")} #${item.entity_id || "-"}</span>
        <p>${escapeHtml(item.summary || "")}</p>
      </div>
    </article>
  `).join("")}</div>`;
}

function dateKey(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function renderTimeline() {
  const root = $("#monitor-calendar");
  const title = $("#calendar-title");
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  title.textContent = `${year}年${month + 1}月`;

  const site = selectedSite();
  const sites = site ? [site] : state.sites;
  const baselineDates = new Set();
  sites.forEach((item) => {
    (item.sources || []).forEach((source) => {
      const key = dateKey(source.baseline_completed_at || source.created_at);
      if (key) baselineDates.add(key);
    });
    const created = dateKey(item.created_at);
    if (created) baselineDates.add(created);
  });

  const launchDates = new Set(confirmedProducts()
    .filter((item) => item.discovery_status === "new")
    .map((item) => dateKey(item.detected_at))
    .filter(Boolean));
  const failedDates = new Set(scopedLogs().filter((item) => item.status === "failed").map((item) => dateKey(item.started_at)).filter(Boolean));
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = ["日", "一", "二", "三", "四", "五", "六"].map((day) => `<span class="calendar-week">${day}</span>`);

  for (let i = 0; i < firstDay; i += 1) {
    cells.push('<span class="calendar-day muted-day"></span>');
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const classes = [
      "calendar-day",
      key === dateKey(now) ? "today" : "",
      baselineDates.has(key) ? "has-baseline" : "",
      launchDates.has(key) ? "has-launch" : "",
      failedDates.has(key) ? "has-failed" : "",
    ].filter(Boolean).join(" ");
    cells.push(`<span class="${classes}">${day}<i></i></span>`);
  }
  root.innerHTML = cells.join("");
}

function renderMonitorList() {
  const root = $("#monitor-list");
  const term = state.searchTerm.trim().toLowerCase();
  const sites = state.sites.filter((site) => !term
    || [site.name, site.url, site.category]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term)));
  if (!sites.length) {
    root.innerHTML = '<div class="empty-mini">还没有官网</div>';
    return;
  }
  root.innerHTML = sites.map((site) => {
    const products = confirmedProducts(state.products.filter((item) => String(item.site_id) === String(site.id)));
    const failed = state.logs.filter((item) => String(item.site_id) === String(site.id) && item.status === "failed").length;
    return `
      <button class="monitor-item ${String(state.currentSiteId || "") === String(site.id) ? "active" : ""}" data-site-id="${site.id}" type="button">
        <span>
          <strong>${escapeHtml(site.name)}</strong>
          <small>${escapeHtml(site.category || "未分类")} · ${priorityLabels[site.priority] || "中优先级"}</small>
        </span>
        <span class="monitor-metrics">
          <b>${products.length}</b>
          <small>${failed ? `${failed} 失败` : "正常"}</small>
        </span>
      </button>
    `;
  }).join("");
  root.querySelectorAll(".monitor-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentSiteId = button.dataset.siteId;
      renderOverview();
      renderMonitorList();
      renderTimeline();
      renderActiveView();
    });
  });
}

async function loadAll() {
  const [sites, products, changes, logs, jobs, notifications, auditLogs] = await Promise.all([
    api("/api/sites"),
    api("/api/products"),
    api("/api/change-events"),
    api("/api/scan-logs"),
    api("/api/scan-jobs"),
    api("/api/notifications"),
    api("/api/audit-logs"),
  ]);
  state.sites = sites;
  state.products = products;
  state.changes = changes;
  state.logs = logs;
  state.jobs = jobs;
  state.notifications = notifications;
  state.auditLogs = auditLogs;
  if (state.currentSiteId && !state.sites.some((site) => String(site.id) === String(state.currentSiteId))) {
    state.currentSiteId = null;
  }
  renderOverview();
  renderMonitorList();
  renderTimeline();
  renderActiveView();
}

$("#site-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "正在建立基线";
  try {
    const created = await api("/api/sites", {
      method: "POST",
      body: JSON.stringify(formPayload(form)),
    });
    await api(`/api/sites/${created.id}/scan`, { method: "POST" });
    form.reset();
    setAdvancedSettingsOpen(false);
    await loadAll();
    setActiveView("products");
    if (created.already_exists) {
      showToast({ type: "success", title: "已重新检查", message: "这个官网已经在监控中，后续发现新品会进入产品库。" });
    } else {
      showToast({ type: "success", title: "已开始监控", message: "首次扫描会建立产品库基线；后续新品会用“新增”标记提醒。" });
    }
  } catch (error) {
    showToast({ type: "error", title: "提交失败", message: error.message });
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "开始监控";
  }
});

function setAdvancedSettingsOpen(open) {
  const toggle = $("#advanced-toggle");
  const panel = $("#advanced-panel");
  toggle.setAttribute("aria-expanded", String(open));
  panel.hidden = !open;
}

$("#advanced-toggle").addEventListener("click", () => {
  const isOpen = $("#advanced-toggle").getAttribute("aria-expanded") === "true";
  setAdvancedSettingsOpen(!isOpen);
});

$("#refresh-btn").addEventListener("click", loadAll);

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const mode = form.dataset.mode || "login";
  const submitButton = $("#auth-submit");
  submitButton.disabled = true;
  submitButton.textContent = mode === "register" ? "正在注册" : "正在登录";
  try {
    const data = await api(`/api/auth/${mode}`, {
      method: "POST",
      auth: false,
      body: JSON.stringify(authPayload(form)),
    });
    setSession(data);
    form.reset();
    showApp();
    await loadAll();
  } catch (error) {
    showToast({ type: "error", title: mode === "register" ? "注册失败" : "登录失败", message: error.message });
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = mode === "register" ? "注册并进入" : "登录";
  }
});

$("#auth-toggle").addEventListener("click", () => {
  const mode = $("#auth-form").dataset.mode === "register" ? "login" : "register";
  showAuth(mode);
});

$("#logout-btn").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (_error) {
    // Local logout should still succeed if the session is already expired.
  }
  clearSession();
  state.sites = [];
  state.products = [];
  state.changes = [];
  state.logs = [];
  state.jobs = [];
  state.notifications = [];
  state.auditLogs = [];
  showAuth("login");
});

$("#clear-site-filter").addEventListener("click", () => {
  state.currentSiteId = null;
  renderOverview();
  renderMonitorList();
  renderTimeline();
  renderActiveView();
});

document.querySelectorAll(".feature-tabs button").forEach((button) => {
  button.addEventListener("click", () => setActiveView(button.dataset.view));
});

document.querySelectorAll(".side-nav button").forEach((button) => {
  button.addEventListener("click", () => setActiveView(button.dataset.sidebarView));
});

$(".global-search input").addEventListener("input", (event) => {
  state.searchTerm = event.target.value;
  renderMonitorList();
  renderActiveView();
});

async function bootstrap() {
  try {
    state.user = await api("/api/auth/me");
    showApp();
    await loadAll();
  } catch (_error) {
    clearSession();
    showAuth("register");
  }
}

bootstrap();
