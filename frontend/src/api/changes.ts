import { getJson, sendJson } from "./client";
import type { ChangeEvent, ScanLog } from "../types/api";

export type SourceSnapshot = {
  id: number;
  source_id: number;
  url?: string | null;
  selector?: string | null;
  fetched_at?: string | null;
  content_hash?: string | null;
  text_hash?: string | null;
  extracted_text?: string | null;
  capture_method?: "http" | "browser_render" | string | null;
  http_status?: number | null;
  content_type?: string | null;
  content_length?: number | null;
  screenshot_hash?: string | null;
  screenshot_url?: string | null;
  visual_change_ratio?: number | null;
  screenshot_error?: string | null;
};

export type ChangeDiffItem = {
  field?: string;
  label?: string;
  before?: unknown;
  after?: unknown;
  old?: unknown;
  new?: unknown;
};

export type ChangeDetail = ChangeEvent & {
  severity?: string | null;
  inbox_status?: string | null;
  site_url?: string | null;
  source_type?: string | null;
  source_url?: string | null;
  selector?: string | null;
  product_price?: string | number | null;
  product_currency?: string | null;
  product_availability?: string | null;
  diff?: ChangeDiffItem[] | null;
  snapshot_before?: SourceSnapshot | null;
  snapshot_after?: SourceSnapshot | null;
  scan_metadata?: ScanLog | null;
};

export type ChangeEventFilters = {
  site_id?: number | string | null;
  inbox_status?: string | null;
  assignee?: string | null;
  change_type?: string | null;
  severity?: string | null;
  q?: string | null;
};

function queryString(filters: ChangeEventFilters = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function loadChangeEvents(filters: ChangeEventFilters = {}): Promise<ChangeEvent[]> {
  return getJson<ChangeEvent[]>(`/api/change-events${queryString(filters)}`);
}

export function loadChangeDetail(id: number | string): Promise<ChangeDetail> {
  return getJson<ChangeDetail>(`/api/change-events/${id}`);
}

export type EventSuppressionRule = {
  id: number;
  site_id: number;
  source_id: number;
  change_type: string;
  reason?: string | null;
  enabled: boolean;
};

export function suppressSimilarChangeEvents(eventId: number | string, reason: string): Promise<EventSuppressionRule> {
  return sendJson<EventSuppressionRule>(`/api/change-events/${eventId}/suppress-similar`, { reason });
}
