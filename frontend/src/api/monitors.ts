import { patchJson, sendJson } from "./client";
import type { Site } from "../types/api";

type BackendSourceType = "listing_page" | "custom_page";
type NotificationEvent = "product_new" | "variant_new" | "price_change" | "availability_change" | "description_change" | "text_change";

export type CreateMonitorTaskInput = {
  targetUrl: string;
  targets: string[];
  extractionMethod: string;
  frequency: string;
  channels: string[];
  selector?: string;
};

export type MonitorSource = {
  id: number;
  site_id: number;
  source_type: BackendSourceType;
  url: string;
  selector?: string | null;
  scan_interval_minutes?: number;
  enabled?: boolean;
};

export type CreateMonitorTaskResult = {
  site: Site;
  source: MonitorSource;
};

export type ScanJob = {
  id?: number | string;
  site_id?: number;
  source_id?: number;
  status?: string;
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

function extractionToSourceType(extractionMethod: string): BackendSourceType {
  return extractionMethod === "auto" ? "listing_page" : "custom_page";
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

  const source = await sendJson<MonitorSource>(`/api/sites/${site.id}/sources`, {
    source_type: extractionToSourceType(input.extractionMethod),
    url: input.targetUrl,
    selector: input.extractionMethod === "css" ? input.selector || "body" : undefined,
    scan_interval_minutes,
  });

  return { site, source };
}

export function triggerSiteScan(siteId: number): Promise<ScanJob> {
  return sendJson<ScanJob>(`/api/sites/${siteId}/scan`, {});
}

export function updateSiteEnabled(siteId: number, enabled: boolean): Promise<Site> {
  return patchJson<Site>(`/api/sites/${siteId}`, { enabled });
}
