import { getJson } from "./client";
import type { ScanLog, SystemHealth } from "../types/api";

export type ScanJob = {
  id: number;
  parent_job_id?: number | null;
  site_id: number;
  site_name?: string | null;
  source_id?: number | null;
  source_type?: string | null;
  source_url?: string | null;
  job_type?: string | null;
  trigger_type?: string | null;
  status?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  candidates_count?: number | null;
  new_count?: number | null;
  error_message?: string | null;
};

export type OperationsSummary = {
  scans: {
    total: number;
    successful: number;
    failed: number;
    success_rate: number | null;
    average_duration_ms: number | null;
  };
  queue: { queued: number; running: number; failed: number };
  notifications: { pending: number; sending: number; failed: number };
  failure_categories: Array<{ category: string; count: number }>;
};

export type QualityBenchmark = {
  scope: "controlled_fixture";
  case_count: number;
  passed: boolean;
  field_pass_rates: Record<string, number>;
  case_results: Array<{ name: string; passed: boolean; mismatches: Record<string, unknown> }>;
  coverage: string[];
  limitation: string;
};

export type RealSiteBenchmark = {
  updated_at: string;
  core_site_count: number;
  control_site_count: number;
  public_catalog_reference_count: number;
  accuracy_claim_allowed: boolean;
  next_action: string;
  sites: Array<{
    slug: string;
    name: string;
    url: string;
    platform_hint: string;
    reference_state: "public_catalog_count" | "sitemap_candidates" | "manual_required" | "negative_control";
    reference_count: number | null;
    evidence: string;
    is_control: boolean;
  }>;
};

export type OperationsContext = {
  health: SystemHealth;
  scanJobs: ScanJob[];
  scanLogs: ScanLog[];
  summary: OperationsSummary;
  qualityBenchmark?: QualityBenchmark;
  realSiteBenchmark?: RealSiteBenchmark;
};

export async function loadOperationsContext(): Promise<OperationsContext> {
  const [health, scanJobs, scanLogs, summary, qualityBenchmark, realSiteBenchmark] = await Promise.all([
    getJson<SystemHealth>("/api/system/health"),
    getJson<ScanJob[]>("/api/scan-jobs"),
    getJson<ScanLog[]>("/api/scan-logs"),
    getJson<OperationsSummary>("/api/operations/summary"),
    getJson<QualityBenchmark>("/api/quality-benchmark"),
    getJson<RealSiteBenchmark>("/api/real-site-benchmark"),
  ]);

  return { health, scanJobs, scanLogs, summary, qualityBenchmark, realSiteBenchmark };
}
