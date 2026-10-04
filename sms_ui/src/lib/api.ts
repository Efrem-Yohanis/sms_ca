// Re-export base utilities so existing imports from "@/lib/api" still work
export {
  API_BASE,
  API_V1_BASE,
  authHeaders,
  authFetch,
  handleResponse,
} from "./api/base";
export type { PaginatedResponse } from "./api/base";

// Re-export standalone resource APIs
export * from "./api/audiences";
export * from "./api/schedules";
export * from "./api/messages";
export * from "./api/dashboard";

// Keep local imports for functions that use the module-level variable
import {
  API_BASE,
  API_V1_BASE,
  authFetch,
  authHeaders,
  handleResponse,
} from "./api/base";
import { fetchLanguages } from "./api/configurations";
import {
  configureDatabaseAudience,
  configureFileAudience,
  fetchCampaignAudienceConfig,
  startAudienceBuild,
  waitForAudienceBuild,
} from "./api/audiences";
import type { AudienceBuildProgress } from "./api/audiences";
import type {
  AudienceDatabaseSelection,
  AudienceSource,
} from "@/types/campaign";

async function handleApiResponse<T>(res: Response): Promise<T> {
  const payload = await handleResponse<T | { data: T }>(res);
  return payload && typeof payload === "object" && "data" in payload
    ? payload.data
    : (payload as T);
}

/* -------- Auth -------- */

export async function login(
  username: string,
  password: string,
): Promise<
  { access: string; refresh: string } | { must_change_password: true }
> {
  const res = await fetch(`${API_V1_BASE}/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  return handleResponse(res);
}

const ADMIN_API_BASE = `${(import.meta.env.VITE_ADMIN_API_BASE_URL || "http://localhost:8002").replace(/\/+$/, "")}/api/v1`;

async function adminAuthRequest<T>(
  path: string,
  body: Record<string, string>,
): Promise<T> {
  const response = await fetch(`${ADMIN_API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

export function changeTemporaryPassword(
  username: string,
  currentPassword: string,
  newPassword: string,
) {
  return fetch(`${API_V1_BASE}/auth/initial-password/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      current_password: currentPassword,
      new_password: newPassword,
    }),
  }).then((response) => handleResponse<{ success: true }>(response));
}

export function requestPasswordResetLink(email: string) {
  return adminAuthRequest<{ detail: string }>(
    "/admin/auth/password-reset/request/",
    { email },
  );
}

export function confirmPasswordResetToken(
  challenge: number,
  token: string,
  newPassword: string,
) {
  return adminAuthRequest<{ success: true }>(
    "/admin/auth/password-reset/confirm/",
    {
      challenge: String(challenge),
      token,
      new_password: newPassword,
    },
  );
}

export async function refreshToken(
  refresh: string,
): Promise<{ access: string }> {
  const res = await fetch(`${API_V1_BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  return handleResponse(res);
}

/* -------- Campaigns -------- */

export interface ApiProgress {
  total_messages: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  failed_delivery_count: number;
  pending_count: number;
  progress_percent: number;
  status: string;
}

export interface ApiCampaign {
  id: number;
  name: string;
  status: string;
  status_display?: string;
  execution_status: string;
  execution_status_display?: string;
  is_ready_to_execute: boolean;
  sender_id: string;
  owner_emails: string[];
  channels_id?: number[];
  channels: string[];
  progress_percent: number;
  total_messages: number;
  total_processed: number;
  success_sent_count: number;
  failed_sent_count: number;
  success_delivery_count: number;
  failed_delivery_count: number;
  next_run: string | null;
  has_schedule: boolean;
  has_audience: boolean;
  has_content: boolean;
  audience_id?: number | null;
  message_content_id?: number | null;
  schedule_id?: number | null;
  channels: Record<string, string> | string[];
  created_by: number;
  created_at: string;
  updated_at: string;
  schedule: {
    id: number;
    campaign_name: string;
    schedule_type: string;
    schedule_type_display: string;
    campaign_status: string;
    campaign_status_display: string;
    current_window_status_display: string;
    upcoming_windows: string;
    schedule_summary: string;
    start_date: string;
    end_date: string | null;
    run_days: Record<string, string> | number[];
    time_windows: Record<string, string> | { start: string; end: string }[];
    timezone: string;
    current_round: number;
    current_window_date: string | null;
    current_window_index: number;
    current_window_status: string;
    next_run_date: string | null;
    next_run_window: number;
    completed_windows: Record<string, string>;
    total_windows_completed: number;
    is_active: boolean;
    auto_reset: boolean;
    created_at: string;
    updated_at: string;
    last_processed_at: string | null;
  } | null;
  message_content: {
    id: number;
    languages_available: string[] | string;
    preview: string | { language: string; preview: string } | null;
    content: Record<string, string>;
    default_language: string;
    created_at: string;
    updated_at: string;
  } | null;
  audience: {
    id: number;
    source_type?: string;
    summary: string | { total: number; valid: number; invalid: number };
    database_info: string | { table: string; id_field: string; filter: string };
    valid_percentage: string | number;
    total_count: number;
    valid_count: number;
    invalid_count: number;
    database_table: string;
    id_field: string;
    filter_condition: string;
    created_at: string;
    updated_at: string;
  } | null;
  progress: ApiProgress | string;
  checkpoint_info: Record<string, unknown> | string;
  provider_stats: Record<string, unknown> | string;
  last_processed_id: number;
  total_processed: number;
  can_start: boolean;
  can_pause: boolean;
  can_resume: boolean;
  can_stop: boolean;
  can_complete: boolean;
  is_deleted: boolean;
}

export interface FetchCampaignsParams {
  page?: number;
  pageSize?: number;
  status?: string;
  execution_status?: string;
  search?: string;
  ordering?: string;
}

export async function fetchCampaigns(params: FetchCampaignsParams = {}) {
  const {
    page = 1,
    pageSize = 10,
    status,
    execution_status,
    search,
    ordering,
  } = params;
  const qp = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (status) qp.set("status", status);
  if (execution_status) qp.set("execution_status", execution_status);
  if (search) qp.set("search", search);
  if (ordering) qp.set("ordering", ordering);
  const res = await authFetch(`${API_V1_BASE}/campaigns/?${qp.toString()}`, {
    headers: authHeaders(),
  });
  return handleResponse<import("./api/base").PaginatedResponse<ApiCampaign>>(
    res,
  );
}

export async function fetchCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/`, {
    headers: authHeaders(),
  });
  return handleApiResponse<ApiCampaign>(res);
}

export interface CreateCampaignPayload {
  name: string;
  owner_emails?: string[];
  sender_id: string;
  channels: string[];
}

export async function createCampaign(data: CreateCampaignPayload) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleApiResponse<{ id: number; [key: string]: unknown }>(res);
}

export async function updateCampaignApi(
  id: number,
  data: Partial<CreateCampaignPayload>,
) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleApiResponse<ApiCampaign>(res);
}

export async function deleteCampaignApi(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function softDeleteCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<{ message: string; campaign_id: number }>(res);
}

/* -------- Campaign Actions -------- */

export async function startCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/send-now/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    success: boolean;
    status?: string;
    message: string;
    campaign_id?: number;
  }>(res);
}

export async function activateCampaign(id: number): Promise<{
  success: boolean;
  message: string;
  data: {
    campaign_id: number;
    status: string;
    messages_built: number;
    owner_notification_sent: boolean | null;
  };
  warnings: string[];
}> {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/activate/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function pauseCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/pause/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    status: string;
    execution_status: string;
    message: string;
    campaign_id: number;
  }>(res);
}

export async function resumeCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/send-now/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    success: boolean;
    status?: string;
    message: string;
    campaign_id?: number;
  }>(res);
}

export async function stopCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/cancel/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    status: string;
    message: string;
    campaign_id: number;
  }>(res);
}

export async function completeCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/complete/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    status: string;
    execution_status: string;
    message: string;
    campaign_id: number;
  }>(res);
}

export async function archiveCampaign(id: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${id}/archive/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<{
    status: string;
    message: string;
    campaign_id: number;
  }>(res);
}

/* -------- Schedule (campaign-nested) -------- */

export interface SchedulePayload {
  schedule_type: string;
  start_date: string;
  end_date?: string | null;
  run_days?: number[];
  time_windows: { start: string; end: string }[];
  timezone: string;
  auto_reset?: boolean;
}

export async function fetchSchedule(campaignId: number) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/schedule/`,
    { headers: authHeaders() },
  );
  return handleApiResponse(res);
}

export async function createSchedule(
  campaignId: number,
  data: SchedulePayload,
) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/schedule/`,
    {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(data),
    },
  );
  return handleApiResponse(res);
}

export async function updateSchedule(
  campaignId: number,
  data: Partial<SchedulePayload>,
) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/schedule/`,
    {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(data),
    },
  );
  return handleApiResponse(res);
}

export async function deleteSchedule(campaignId: number) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/schedule/`,
    {
      method: "DELETE",
      headers: authHeaders(),
    },
  );
  return handleResponse<void>(res);
}

/* -------- Message Content (campaign-nested) -------- */

export interface MessageContentPayload {
  content: Record<string, string>;
  default_language: string;
}

function serializeMessageContent(data: MessageContentPayload) {
  return {
    ...data.content,
    default_language: data.default_language,
  };
}

export async function createCampaignMessageContent(
  campaignId: number,
  data: MessageContentPayload,
) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/content/`,
    {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(serializeMessageContent(data)),
    },
  );
  return handleApiResponse(res);
}

export async function fetchMessageContent(campaignId: number) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/content/`,
    { headers: authHeaders() },
  );
  return handleApiResponse(res);
}

export async function updateMessageContent(
  campaignId: number,
  data: MessageContentPayload,
) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/content/`,
    {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify(serializeMessageContent(data)),
    },
  );
  return handleApiResponse(res);
}

export async function patchMessageContent(
  campaignId: number,
  data: Partial<MessageContentPayload>,
) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/content/`,
    {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify({
        ...(data.content ?? {}),
        ...(data.default_language !== undefined
          ? { default_language: data.default_language }
          : {}),
      }),
    },
  );
  return handleApiResponse(res);
}

/* -------- Audience (campaign-nested) -------- */

export interface AudiencePayload {
  recipients: {
    msisdn: string;
    lang: string;
    variables?: Record<string, string>;
  }[];
  default_language: string;
  source_type: AudienceSource;
  database_config?: AudienceDatabaseSelection | null;
  source_file?: File | null;
}

export async function fetchAudience(campaignId: number) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/audience/`,
    { headers: authHeaders() },
  );
  return handleApiResponse(res);
}

export async function saveCampaignAudience(
  campaignId: number,
  data: AudiencePayload,
  onProgress?: (progress: AudienceBuildProgress) => void,
) {
  const languages = await fetchLanguages();
  const defaultLanguage = languages.results.find(
    (language) => language.code === data.default_language,
  );
  if (!defaultLanguage)
    throw new Error(
      `Default language '${data.default_language}' is not configured`,
    );

  let configId: number;
  if (data.source_type === "database") {
    if (!data.database_config)
      throw new Error(
        "Choose and preview a database source before building the audience",
      );
    const response = await configureDatabaseAudience(campaignId, {
      ...data.database_config,
      default_language_id: defaultLanguage.id,
      mapper_enabled: false,
      rebuild_before_each_run: false,
      rebuild_minutes_before: 10,
      rebuild_timeout_minutes: 30,
    });
    configId = response.data.id;
  } else if (data.source_type === "file") {
    if (data.source_file) {
      const response = await configureFileAudience(campaignId, {
        file: data.source_file,
        source_file_msisdn_column: "msisdn",
        source_file_language_column: "language",
        default_language_id: defaultLanguage.id,
      });
      configId = response.data.id;
    } else {
      const existingConfig = await fetchCampaignAudienceConfig(campaignId);
      if (!existingConfig || existingConfig.source_type !== "file_import") {
        throw new Error(
          "Upload a CSV or spreadsheet and select its MSISDN column",
        );
      }
      configId = existingConfig.id;
    }
  } else {
    const res = await authFetch(
      `${API_V1_BASE}/campaigns/${campaignId}/audience-config/`,
      {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          source_type: "manual",
          manual_msisdns: data.recipients.map((recipient) => recipient.msisdn),
          manual_languages: data.recipients.map(
            (recipient) => recipient.lang ?? "",
          ),
          default_language_id: defaultLanguage.id,
          mapper_enabled: false,
        }),
      },
    );
    const config = await handleApiResponse<{ id: number }>(res);
    configId = config.id;
  }

  const build = await startAudienceBuild(configId);
  const result = await waitForAudienceBuild(
    build.job_id,
    configId,
    30,
    onProgress,
  );
  const buildResult = result.result as {
    data?: { total_count?: number };
  } | null;
  return {
    campaign_id: campaignId,
    audience_id: configId,
    total_count: buildResult?.data?.total_count ?? result.valid_rows,
    valid_count: result.valid_rows,
    invalid_count: result.invalid_rows,
  };
}

export async function deleteAudience(campaignId: number) {
  const res = await authFetch(
    `${API_BASE}/api/campaigns/${campaignId}/audience/`,
    {
      method: "DELETE",
      headers: authHeaders(),
    },
  );
  return handleResponse<void>(res);
}

/* -------- Progress & Batches -------- */

export async function fetchCampaignProgress(campaignId: number) {
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/progress/`,
    { headers: authHeaders() },
  );
  return handleResponse<{
    campaign_id: number;
    campaign_name: string;
    progress: ApiProgress;
    batches: {
      total_batches: number;
      completed_batches: number;
      failed_batches: number;
      in_progress_batches: number;
    };
  }>(res);
}

export async function fetchCampaignBatches(
  campaignId: number,
  status?: string,
) {
  const params = status ? `?status=${status}` : "";
  const res = await authFetch(
    `${API_V1_BASE}/campaigns/${campaignId}/messages/batches/${params}`,
    { headers: authHeaders() },
  );
  return handleResponse(res);
}

export async function fetchCampaignCheckpoint(campaignId: number) {
  const res = await authFetch(
    `${API_BASE}/api/campaigns/${campaignId}/checkpoint/`,
    { headers: authHeaders() },
  );
  return handleResponse(res);
}

/* -------- Utility -------- */

export async function fetchChannelChoices() {
  const res = await authFetch(`${API_BASE}/api/campaigns/channel-choices/`, {
    headers: authHeaders(),
  });
  return handleResponse<{ value: string; display: string }[]>(res);
}

export async function fetchExecutionStatusChoices() {
  const res = await authFetch(
    `${API_BASE}/api/campaigns/execution-status-choices/`,
    { headers: authHeaders() },
  );
  return handleResponse<{ value: string; display: string }[]>(res);
}

export async function fetchCampaignSummary() {
  const res = await authFetch(`${API_BASE}/api/campaigns/summary/`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}
