import { deleteJson, getJson, patchJson, sendJson } from "./client";
import type { Site } from "../types/api";

type NotificationEvent = "product_new" | "variant_new" | "price_change" | "availability_change" | "description_change" | "text_change";

export type CreateMonitorTaskInput = {
  targetUrl: string;
  targets: string[];
  extractionMethod: string;
  frequency: string;
  channels: string[];
  selector?: string;
};

export type CreateMonitorTaskResult = {
  site: Site;
};

export type ScanProgress = {
  phase?: string;
  discovered_count?: number;
  processed_count?: number;
  failed_count?: number;
  product_count?: number | null;
  baseline_completed?: boolean;
  quality?: ScanQuality;
};

export type ScanQuality = {
  discovered_product_count?: number;
  attempted_product_count?: number;
  stored_product_count?: number;
  rate_limited_count?: number;
  blocked_count?: number;
  fetch_failed_count?: number;
  parse_failed_count?: number;
  non_product_count?: number;
  pending_retry_count?: number;
  baseline_state?: "pending" | "complete" | "incomplete";
  catalog_reference_count?: number | null;
  discovery_source_counts?: Record<string, number>;
  adapter_attempts?: Array<{
    adapter: string;
    status: "available" | "not_applicable" | "limited" | "blocked" | "failed";
    http_status?: number;
    reason?: string;
  }>;
  coverage_state?: "pending" | "verified" | "best_effort" | "incomplete" | "failed";
};

export type ScanJob = {
  id: number | string;
  site_id: number;
  source_id?: number | null;
  status: string;
  message?: string | null;
  result?: { progress?: ScanProgress };
};

const targetToNotificationEvent: Record<string, NotificationEvent[]> = {
  "new-products": ["product_new", "variant_new"],
  price: ["price_change"],
  stock: ["availability_change"],
  text: ["text_change"],
  image: ["description_change"],
  area: ["text_change"],
};

function frequencyToMinutes(frequency: string) {
  if (frequency.includes("15")) return 15;
  if (frequency.includes("30")) return 30;
  if (frequency.includes("每天")) return 1440;
  return 60;
}

function siteNameFromUrl(targetUrl: string) {
  try {
    const url = new URL(targetUrl);
    return url.hostname.replace(/^www\./, "");
  } catch {
    return "ProductAlert Monitor";
  }
}

function notificationEventsForTargets(targets: string[]) {
  const events = targets.flatMap((target) => targetToNotificationEvent[target] || []);
  return Array.from(new Set(events.length ? events : ["product_new"]));
}

export async function createMonitorTask(input: CreateMonitorTaskInput): Promise<CreateMonitorTaskResult> {
  const scan_interval_minutes = frequencyToMinutes(input.frequency);
  const site = await sendJson<Site>("/api/sites", {
    name: siteNameFromUrl(input.targetUrl),
    url: input.targetUrl,
    category: "ProductAlert",
    priority: input.targets.includes("price") || input.targets.includes("new-products") ? 1 : 2,
    notes: JSON.stringify({
      monitor_targets: input.targets,
      extraction_method: input.extractionMethod,
      notification_channels: input.channels,
    }),
    scan_interval_minutes,
    notification_events: notificationEventsForTargets(input.targets),
  });

  return { site };
}

export function triggerSiteScan(siteId: number): Promise<ScanJob> {
  return sendJson<ScanJob>(`/api/sites/${siteId}/scan`, {});
}

export async function createMonitorAndStartBaseline(input: CreateMonitorTaskInput): Promise<{ site: Site; job: ScanJob }> {
  const { site } = await createMonitorTask(input);
  const job = await triggerSiteScan(site.id);
  return { site, job };
}

export function getScanJob(jobId: number | string): Promise<ScanJob> {
  return getJson<ScanJob>(`/api/scan-jobs/${jobId}`);
}

export function resumeScanJob(jobId: number | string): Promise<ScanJob> {
  return sendJson<ScanJob>(`/api/scan-jobs/${jobId}/resume`, {});
}

export function updateSiteEnabled(siteId: number, enabled: boolean): Promise<Site> {
  return patchJson<Site>(`/api/sites/${siteId}`, { enabled });
}

export function deleteSite(siteId: number): Promise<{ ok: boolean }> {
  return deleteJson<{ ok: boolean }>(`/api/sites/${siteId}`);
}
