export type Site = {
  id: number;
  name: string;
  url: string;
  enabled?: boolean;
  scan_interval_minutes?: number;
  sources?: Array<{ id: number; source_type?: string; enabled?: boolean }>;
};

export type Product = {
  id: number;
  site_id: number;
  site_name?: string;
  source_type?: string | null;
  title?: string;
  price?: string | number | null;
  price_amount?: string | number | null;
  compare_at_price?: string | number | null;
  currency?: string | null;
  availability?: string | null;
  variant_count?: number | null;
  display_url?: string | null;
  link_label?: string | null;
  detected_at?: string | null;
  image_url?: string | null;
  url?: string | null;
  inbox_status?: string | null;
  review_status?: string | null;
};

export type ChangeEvent = {
  id: number;
  site_id: number;
  product_id?: number | null;
  site_name?: string;
  product_title?: string | null;
  product_url?: string | null;
  change_type?: string | null;
  summary?: string | null;
  created_at?: string | null;
  status?: string | null;
  inbox_status?: string | null;
  assignee?: string | null;
  review_note?: string | null;
  false_positive_reason?: string | null;
  reviewed_at?: string | null;
};

export type ScanLog = {
  id: number;
  site_id: number;
  site_name?: string;
  status?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  message?: string | null;
  error_message?: string | null;
};

export type SystemHealth = {
  ok: boolean;
  database_backend?: string;
  queue_configured_backend?: string;
  queue_backend?: string;
  redis_configured?: boolean;
  background_workers_enabled?: boolean;
  notification_worker_enabled?: boolean;
  sqlite_path?: string | null;
};
