import { authFetch, handleResponse, API_V1_BASE, authHeaders } from "./base";
import type { PaginatedResponse } from "./base";

const MESSAGE_CONTENT_PATH = "/message-content/";

// =============== RESPONSE INTERFACES ===============

export interface ApiMessageContentListItem {
  id: number;
  campaign: number;
  campaign_name?: string;
  content: Record<string, string>;
  default_language: string;
  languages_available: string[];
  preview: { language: string; preview: string } | null;
  created_at: string;
  updated_at: string;
}

export interface MessageContentSummary {
  total_message_contents: number;
  by_default_language: Record<string, number>;
  total_languages_used: Record<string, number>;
  content_completeness: Record<string, number>;
}

export interface SupportedLanguage {
  code: string;
  name: string;
}

export interface SupportedLanguagesResponse {
  languages: SupportedLanguage[];
  default: string;
}

export interface CampaignMessageBuildResponse {
  success: boolean;
  message: string;
  data: {
    campaign_id: number;
    round_number: number;
    batch_id: string;
    cleared: number;
    total_audience: number;
    built: number;
    skipped: number;
    failed: number;
    errors: { msisdn: string; error: string }[];
    duration_seconds: number;
  };
}

export interface CampaignMessageQueueItem {
  id: number;
  message_id: string;
  recipient: string;
  sender_id: string;
  language_code: string | null;
  message_content: string;
  message_parts: number;
  status: string;
  batch_id: string;
  built_at: string;
}

export interface CampaignMessageQueueStats {
  success: boolean;
  data: {
    campaign_id: number;
    total: number;
    pending: number;
    processing: number;
    language_breakdown: Record<string, number>;
  };
}

export interface CampaignMessageBuildProgress {
  id: number;
  campaign_id: number;
  batch_id: string;
  round_number: number;
  status: "RUNNING" | "SUCCEEDED" | "FAILED";
  phase: string;
  processed: number;
  total: number;
  built: number;
  skipped: number;
  failed: number;
  percent: number;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

// =============== API FUNCTIONS ===============

/** GET /api/v1/message-content/ */
export async function fetchMessageContents(
  page = 1,
  pageSize = 20,
  filters?: Record<string, string>
): Promise<PaginatedResponse<ApiMessageContentListItem>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters) Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}?${params}`, { headers: authHeaders() });
  return handleResponse<PaginatedResponse<ApiMessageContentListItem>>(res);
}

/** GET /api/v1/message-content/{id}/ */
export async function fetchMessageContentDetail(id: number): Promise<ApiMessageContentListItem> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}${id}/`, { headers: authHeaders() });
  return handleResponse<ApiMessageContentListItem>(res);
}

/** GET /api/v1/message-content/summary/ */
export async function fetchMessageContentSummary(): Promise<MessageContentSummary> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}summary/`, { headers: authHeaders() });
  return handleResponse<MessageContentSummary>(res);
}

/** GET /api/v1/message-content/languages/ */
export async function fetchSupportedLanguages(): Promise<SupportedLanguagesResponse> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}languages/`, { headers: authHeaders() });
  const data = await handleResponse<SupportedLanguagesResponse | { data?: SupportedLanguage[]; languages?: SupportedLanguage[]; default?: string }>(res);
  const languages = Array.isArray((data as SupportedLanguagesResponse).languages)
    ? (data as SupportedLanguagesResponse).languages
    : (data as { data?: SupportedLanguage[] }).data ?? [];
  return {
    languages,
    default: (data as SupportedLanguagesResponse).default ?? languages[0]?.code ?? "en",
  };
}

/** POST /api/v1/message-content/ */
export async function createMessageContent(data: {
  campaign: number;
  content: Record<string, string>;
  default_language: string;
}): Promise<ApiMessageContentListItem> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<ApiMessageContentListItem>(res);
}

/** PATCH /api/v1/message-content/{id}/ */
export async function updateMessageContentById(
  id: number,
  data: { content?: Record<string, string>; default_language?: string }
): Promise<ApiMessageContentListItem> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<ApiMessageContentListItem>(res);
}

/** PUT /api/v1/message-content/{id}/ */
export async function updateMessageContentFull(
  id: number,
  data: { campaign: number; content: Record<string, string>; default_language: string }
): Promise<ApiMessageContentListItem> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}${id}/`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<ApiMessageContentListItem>(res);
}

/** DELETE /api/v1/message-content/{id}/ */
export async function deleteMessageContentById(id: number): Promise<void> {
  const res = await authFetch(`${API_V1_BASE}${MESSAGE_CONTENT_PATH}${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (res.status === 204) return;
  return handleResponse<void>(res);
}

/** POST /api/v1/campaigns/{id}/messages/build/ */
export async function buildCampaignMessages(
  campaignId: number,
  options: { round_number?: number; batch_id?: string } = {}
): Promise<CampaignMessageBuildResponse> {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/messages/build/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(options),
  });
  return handleResponse<CampaignMessageBuildResponse>(res);
}

export async function fetchCampaignMessageBuildProgress(campaignId: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/messages/build-progress/`, {
    headers: authHeaders(),
  });
  return handleResponse<{ success: boolean; data: CampaignMessageBuildProgress | null }>(res);
}

/** GET /api/v1/campaigns/{id}/messages/ */
export async function fetchCampaignMessages(
  campaignId: number,
  page = 1,
  pageSize = 10
): Promise<PaginatedResponse<CampaignMessageQueueItem>> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/messages/?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<PaginatedResponse<CampaignMessageQueueItem>>(res);
}

/** GET /api/v1/campaigns/{id}/messages/stats/ */
export async function fetchCampaignMessageStats(campaignId: number): Promise<CampaignMessageQueueStats> {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/messages/stats/`, {
    headers: authHeaders(),
  });
  return handleResponse<CampaignMessageQueueStats>(res);
}

/** DELETE /api/v1/campaigns/{id}/messages/clear/ */
export async function clearCampaignMessages(campaignId: number): Promise<{ success: boolean; message: string }> {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/messages/clear/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<{ success: boolean; message: string }>(res);
}
