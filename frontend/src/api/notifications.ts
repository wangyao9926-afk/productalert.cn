import { getJson, sendJson } from "./client";

export type NotificationRecord = {
  id: number;
  site_id: number;
  site_name?: string | null;
  product_id?: number | null;
  product_title?: string | null;
  product_url?: string | null;
  event_id?: number | null;
  event_summary?: string | null;
  change_type?: string | null;
  channel?: string | null;
  target_url?: string | null;
  status?: string | null;
  attempts?: number | null;
  last_error?: string | null;
  next_attempt_at?: string | null;
  sent_at?: string | null;
  created_at?: string | null;
};

export type NotificationRule = {
  id: number;
  user_id?: number;
  site_id?: number | null;
  site_name?: string | null;
  site_url?: string | null;
  name: string;
  channel: "webhook" | "email" | "wecom" | "feishu" | string;
  target_url: string;
  event_types: string[];
  min_severity: "low" | "normal" | "high" | "critical" | string;
  inbox_status: "unread" | "important" | "read" | "false_positive" | "follow_up" | string;
  max_price_amount?: number | null;
  require_in_stock?: boolean;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CreateNotificationRuleInput = {
  name: string;
  channel: "webhook" | "wecom" | "feishu";
  target_url: string;
  event_types: string[];
  min_severity?: "low" | "normal" | "high" | "critical";
  inbox_status?: "unread" | "important" | "read" | "false_positive" | "follow_up";
  max_price_amount?: number;
  require_in_stock?: boolean;
};

export function loadNotifications(siteId?: number): Promise<NotificationRecord[]> {
  const query = siteId ? `?site_id=${siteId}` : "";
  return getJson<NotificationRecord[]>(`/api/notifications${query}`);
}

export function loadNotificationRules(siteId?: number): Promise<NotificationRule[]> {
  const query = siteId ? `?site_id=${siteId}` : "";
  return getJson<NotificationRule[]>(`/api/notification-rules${query}`);
}

export function createNotificationRule(payload: CreateNotificationRuleInput): Promise<NotificationRule> {
  return sendJson<NotificationRule>("/api/notification-rules", payload);
}

export function retryNotification(notificationId: number): Promise<NotificationRecord> {
  return sendJson<NotificationRecord>(`/api/notifications/${notificationId}/retry`, {});
}
