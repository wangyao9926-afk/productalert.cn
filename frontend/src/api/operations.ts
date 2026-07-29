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

export type OperationsContext = {
  health: SystemHealth;
  scanJobs: ScanJob[];
  scanLogs: ScanLog[];
};

export async function loadOperationsContext(): Promise<OperationsContext> {
  const [health, scanJobs, scanLogs] = await Promise.all([
    getJson<SystemHealth>("/api/system/health"),
    getJson<ScanJob[]>("/api/scan-jobs"),
    getJson<ScanLog[]>("/api/scan-logs"),
  ]);

  return { health, scanJobs, scanLogs };
}
