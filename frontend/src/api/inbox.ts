import { patchJson } from "./client";
import type { ChangeEvent } from "../types/api";

export type BackendInboxStatus = "unread" | "read" | "important" | "follow_up" | "archived" | "false_positive";

export type ChangeEventReviewPayload = {
  inbox_status: BackendInboxStatus;
  assignee?: string | null;
  review_note?: string | null;
  false_positive_reason?: string | null;
};

export function updateChangeEventInboxStatus(
  eventId: number,
  inbox_statusOrPayload: BackendInboxStatus | ChangeEventReviewPayload,
): Promise<ChangeEvent> {
  const payload = typeof inbox_statusOrPayload === "string" ? { inbox_status: inbox_statusOrPayload } : inbox_statusOrPayload;
  return patchJson<ChangeEvent>(`/api/change-events/${eventId}/inbox-status`, payload);
}
