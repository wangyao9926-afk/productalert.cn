import { ApiError, getJson } from "./client";
import type { ChangeEvent, Product, ScanLog, Site, SystemHealth } from "../types/api";

export type OverviewReason = "live" | "auth_required" | "api_unavailable" | "api_error";

export type OverviewData = {
  health: SystemHealth;
  sites: Site[];
  products: Product[];
  events: ChangeEvent[];
  logs: ScanLog[];
  live: boolean;
  mode: "live" | "demo";
  reason: OverviewReason;
  message: string;
};

const demo: OverviewData = {
  health: { ok: true, database_backend: "postgresql", queue_backend: "rq", background_workers_enabled: true, notification_worker_enabled: true },
  sites: [
    { id: 1, name: "Nike · Global", url: "nike.com", enabled: true, sources: [{ id: 1, source_type: "sitemap", enabled: true }] },
    { id: 2, name: "Aesop · CN", url: "aesop.com.cn", enabled: true, sources: [{ id: 2, source_type: "collection", enabled: true }] },
    { id: 3, name: "Uniqlo · JP", url: "uniqlo.com/jp", enabled: true, sources: [{ id: 3, source_type: "rendered", enabled: true }] },
  ],
  products: [
    { id: 1, site_id: 1, site_name: "Nike · Global", title: "Air Max Dn8", price: 899, currency: "CNY", availability: "in_stock", detected_at: "2026-07-10T09:28:00Z" },
    { id: 2, site_id: 2, site_name: "Aesop · CN", title: "香芹籽抗氧化眼霜", price: 475, currency: "CNY", availability: "in_stock", detected_at: "2026-07-10T08:52:00Z" },
  ],
  events: [
    { id: 1, site_id: 1, site_name: "Nike · Global", product_title: "Air Max Dn8", change_type: "new_product", summary: "检测到新品上架", created_at: "2026-07-10T09:28:00Z", status: "unread" },
    { id: 2, site_id: 2, site_name: "Aesop · CN", product_title: "香芹籽抗氧化眼霜", change_type: "price_changed", summary: "价格从 ¥450 调整为 ¥475", created_at: "2026-07-10T08:52:00Z", status: "unread" },
    { id: 3, site_id: 3, site_name: "Uniqlo · JP", product_title: "AIRism 外套", change_type: "availability_changed", summary: "库存状态恢复", created_at: "2026-07-10T07:40:00Z", status: "reviewed" },
  ],
  logs: [
    { id: 1, site_id: 1, site_name: "Nike · Global", status: "success", started_at: "2026-07-10T09:27:00Z", duration_ms: 1840 },
    { id: 2, site_id: 2, site_name: "Aesop · CN", status: "success", started_at: "2026-07-10T08:51:00Z", duration_ms: 2260 },
    { id: 3, site_id: 3, site_name: "Uniqlo · JP", status: "warning", started_at: "2026-07-10T07:39:00Z", duration_ms: 4980, error_message: "页面响应较慢" },
  ],
  live: false,
  mode: "demo",
  reason: "api_unavailable",
  message: "API 不可用，当前显示演示数据。",
};

function demoWith(reason: OverviewReason, message: string): OverviewData {
  return { ...demo, reason, message };
}

export async function loadOverview(): Promise<OverviewData> {
  try {
    const [health, sites, products, events, logs] = await Promise.all([
      getJson<SystemHealth>("/api/system/health"),
      getJson<Site[]>("/api/sites"),
      getJson<Product[]>("/api/products"),
      getJson<ChangeEvent[]>("/api/change-events"),
      getJson<ScanLog[]>("/api/scan-logs"),
    ]);
    return {
      health,
      sites,
      products,
      events,
      logs,
      live: true,
      mode: "live",
      reason: "live",
      message: "真实 API 已连接，当前数据来自后端数据库。",
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return demoWith("auth_required", "需要登录后才能读取真实 API，当前显示演示数据。");
    }
    if (error instanceof ApiError) {
      return demoWith("api_error", `API 返回异常 ${error.status}，当前显示演示数据。`);
    }
    return demoWith("api_unavailable", "API 不可用，当前显示演示数据。");
  }
}
