import { authFetch, handleResponse, API_BASE, API_V1_BASE, authHeaders } from "./base";
import type { PaginatedResponse } from "./base";

export interface ApiAudienceListItem {
  id: number;
  campaign: number;
  campaign_info?: {
    id: number;
    name: string;
    status: string;
    execution_status: string;
  };
  total_count: number;
  valid_count: number;
  invalid_count: number;
  valid_percentage: number;
  summary: { total: number; valid: number; invalid: number };
  database_table: string;
  id_field: string;
  filter_condition: string;
  created_at: string;
  updated_at: string;
}

export interface ApiAudienceDetail extends ApiAudienceListItem {
  statistics?: {
    total_recipients: number;
    valid_recipients: number;
    invalid_recipients: number;
    valid_percentage: number;
    invalid_percentage: number;
  };
  database_info?: { table: string; id_field: string; filter: string };
  recipients_preview?: { msisdn: string; lang: string }[];
}

export interface AudienceSummary {
  total_audiences: number;
  total_recipients: number;
  total_valid: number;
  total_invalid: number;
  avg_valid_percentage: number;
  by_campaign_status: Record<string, number>;
}

export interface AudienceStatistics {
  audience_id: number;
  campaign_id: number;
  campaign_name: string;
  total_count: number;
  valid_count: number;
  invalid_count: number;
  valid_percentage: number;
  invalid_percentage: number;
  language_distribution: Record<string, number>;
  invalid_samples: { msisdn: string; lang: string; error: string }[];
  database_table: string;
  id_field: string;
  created_at: string;
  updated_at: string;
}

export interface RecipientsPreview {
  audience_id: number;
  campaign_id: number;
  campaign_name: string;
  total_recipients: number;
  valid_recipients: number;
  invalid_recipients: number;
  preview: { msisdn: string; lang: string }[];
  preview_count: number;
  has_more: boolean;
}

/* -------- Payload types -------- */

export interface AudienceRecipient {
  msisdn: string;
  lang: string;
}

export interface AudienceCreatePayload {
  campaign: number;
  recipients: AudienceRecipient[];
  default_language?: string;
  source_type?: "manual" | "file_import" | "database";
}

export interface DatabaseAudienceConfigInput {
  source_database_id: number;
  source_table: string;
  source_msisdn_column: string;
  source_language_column: string;
  source_filter_clause: string;
  default_language_id: number;
  mapper_enabled: boolean;
  mapper_database_id?: number | null;
  mapper_table?: string;
  mapper_msisdn_column?: string;
  mapper_language_column?: string;
  mapper_join_type?: "LEFT" | "INNER";
  rebuild_before_each_run: boolean;
  rebuild_minutes_before: number;
  rebuild_timeout_minutes: number;
}

export interface AudienceBuildJob {
  id: number;
  audience_config_id: number;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
  processed_rows: number;
  valid_rows: number;
  invalid_rows: number;
  started_at: string | null;
  heartbeat_at: string | null;
  completed_at: string | null;
  error_message: string;
  result: Record<string, unknown>;
}

export interface AudienceBuildProgress {
  config_id: number;
  round_number: number;
  build_id: string;
  status: string;
  phase: string;
  processed: number;
  total: number;
  percent: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  counters: {
    valid: number;
    invalid: number;
    from_source: number;
    from_mapper: number;
    from_default: number;
  };
}

export interface CampaignAudienceConfig {
  id: number;
  campaign: number;
  source_type: "manual" | "file_import" | "database";
  source_database_id: number | null;
  source_table: string;
  source_msisdn_column: string;
  source_language_column: string;
  source_filter_clause: string;
  manual_msisdns: string[];
  manual_languages: string[];
  source_file_msisdn_column: string;
  source_file_language_column: string;
  default_language_id: number | null;
  total_count: number;
  valid_count: number;
  invalid_count: number;
  is_processed: boolean;
}

export interface CampaignAudienceMember {
  id: number;
  msisdn: string;
  language: number;
  is_valid: boolean;
  sequence_number: number;
}

export interface AudienceUpdatePayload {
  campaign?: number;
  recipients: AudienceRecipient[];
}

/* -------- API calls -------- */

/** GET /api/audiences/ */
export async function fetchAudiences(page = 1, pageSize = 10, filters?: Record<string, string>) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters) Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
  const res = await authFetch(`${API_BASE}/api/audiences/?${params}`, { headers: authHeaders() });
  return handleResponse<PaginatedResponse<ApiAudienceListItem>>(res);
}

/** GET /api/audiences/:id/ */
export async function fetchAudienceDetail(id: number) {
  const res = await authFetch(`${API_BASE}/api/audiences/${id}/`, { headers: authHeaders() });
  return handleResponse<ApiAudienceDetail>(res);
}

/** GET /api/audiences/summary/ */
export async function fetchAudienceSummary() {
  const res = await authFetch(`${API_BASE}/api/audiences/summary/`, { headers: authHeaders() });
  return handleResponse<AudienceSummary>(res);
}

/** GET /api/audiences/:id/statistics/ */
export async function fetchAudienceStatistics(id: number) {
  const res = await authFetch(`${API_BASE}/api/audiences/${id}/statistics/`, { headers: authHeaders() });
  return handleResponse<AudienceStatistics>(res);
}

/** GET /api/audiences/:id/recipients_preview/ */
export async function fetchRecipientsPreview(id: number) {
  const res = await authFetch(`${API_BASE}/api/audiences/${id}/recipients_preview/`, { headers: authHeaders() });
  return handleResponse<RecipientsPreview>(res);
}

/** POST /api/v1/campaigns/:id/audience/ — persist recipients for a campaign */
export async function createAudience(payload: AudienceCreatePayload) {
  const res = await authFetch(`${API_BASE}/api/v1/campaigns/${payload.campaign}/audience/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      msisdns: payload.recipients.map((recipient) => recipient.msisdn),
      languages: payload.recipients.map((recipient) => recipient.lang ?? ""),
      default_language: payload.default_language ?? "en",
      source_type: payload.source_type ?? "manual",
    }),
  });
  return handleResponse<{ success: boolean; data: { campaign_id: number; total_count: number; valid_count: number } }>(res);
}

export async function configureDatabaseAudience(
  campaignId: number,
  payload: DatabaseAudienceConfigInput,
) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/audience/database/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<{ success: boolean; data: { id: number; campaign: number } }>(res);
}

export interface FileAudienceConfigInput {
  file: File;
  source_file_msisdn_column: string;
  source_file_language_column: string;
  default_language_id: number;
}

export async function configureFileAudience(campaignId: number, payload: FileAudienceConfigInput) {
  const body = new FormData();
  body.append("file", payload.file);
  body.append("source_file_msisdn_column", payload.source_file_msisdn_column);
  body.append("source_file_language_column", payload.source_file_language_column);
  body.append("default_language_id", String(payload.default_language_id));
  body.append("mapper_enabled", "false");
  body.append("rebuild_before_each_run", "false");
  body.append("rebuild_minutes_before", "10");
  body.append("rebuild_timeout_minutes", "30");

  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/audience/file/`, {
    method: "POST",
    body,
  });
  return handleResponse<{ success: boolean; data: { id: number; campaign: number } }>(res);
}

export async function startAudienceBuild(configId: number) {
  const res = await authFetch(`${API_V1_BASE}/audience-configs/${configId}/build/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({}),
  });
  return handleResponse<{ success: boolean; config_id: number; job_id: number; round_number: number }>(res);
}

export async function fetchAudienceBuildJob(jobId: number) {
  const res = await authFetch(`${API_V1_BASE}/audience-build-jobs/${jobId}/`, {
    headers: authHeaders(),
  });
  return handleResponse<{ success: boolean; data: AudienceBuildJob }>(res);
}

export async function fetchAudienceBuildProgress(configId: number) {
  const res = await authFetch(`${API_V1_BASE}/audience-configs/${configId}/progress/`, {
    headers: authHeaders(),
  });
  return handleResponse<{ success: boolean; data: AudienceBuildProgress }>(res);
}

export async function fetchCampaignAudienceConfig(campaignId: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/audience-config/`, {
    headers: authHeaders(),
  });
  const response = await handleResponse<{ success: boolean; data: CampaignAudienceConfig | null }>(res);
  return response.data;
}

export async function fetchCampaignAudienceMembers(campaignId: number, pageSize = 1000) {
  const params = new URLSearchParams({ page: "1", page_size: String(pageSize) });
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/audience/members/?${params}`, {
    headers: authHeaders(),
  });
  const response = await handleResponse<PaginatedResponse<CampaignAudienceMember>>(res);
  return response.results;
}

export async function waitForAudienceBuild(
  jobId: number,
  configId: number,
  timeoutMinutes = 30,
  onProgress?: (progress: AudienceBuildProgress) => void,
) {
  const deadline = Date.now() + timeoutMinutes * 60_000;
  while (Date.now() < deadline) {
    const job = await fetchAudienceBuildJob(jobId);
    const progress = await fetchAudienceBuildProgress(configId);
    onProgress?.(progress.data);
    if (job.data.status === "SUCCEEDED") return job.data;
    if (job.data.status === "FAILED") {
      throw new Error(job.data.error_message || `Audience build ${jobId} failed`);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error(`Audience build ${jobId} timed out after ${timeoutMinutes} minutes`);
}

// Alias
export const createAudienceStandalone = createAudience;

/** PUT /api/audiences/:id/ — full update with campaign + recipients */
export async function updateAudienceFull(id: number, payload: AudienceCreatePayload) {
  const res = await authFetch(`${API_BASE}/api/audiences/${id}/`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<ApiAudienceDetail>(res);
}

/** PATCH /api/audiences/:id/ — partial update (recipients only is fine) */
export async function updateAudience(id: number, payload: AudienceUpdatePayload) {
  const res = await authFetch(`${API_BASE}/api/audiences/${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return handleResponse<ApiAudienceDetail>(res);
}

/** DELETE /api/audiences/:campaignId/ */
export async function deleteAudienceById(campaignId: number) {
  const res = await authFetch(`${API_BASE}/api/audiences/${campaignId}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}
