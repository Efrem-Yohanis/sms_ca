import { API_V1_BASE, authFetch, authHeaders, handleResponse } from "./base";

const PATH = "/report-subscriptions/";

export type ReportFrequency = "10min" | "1hr" | "1day" | "manual";
export type ReportFormat = "html" | "text" | "csv";

export interface ReportCampaign {
  id: number;
  name: string;
}

export interface Report {
  id: number;
  name: string;
  campaigns: ReportCampaign[];
  recipients: string[];
  include_campaign_owners: boolean;
  email_config: number | null;
  email_config_name: string | null;
  frequency: ReportFrequency;
  format: ReportFormat;
  is_active: boolean;
  next_run_at: string | null;
  last_sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportSubscriptionInput {
  name: string;
  campaign_ids: number[];
  recipients: string[];
  include_campaign_owners: boolean;
  email_config_id: number | null;
  frequency: ReportFrequency;
  format: ReportFormat;
  is_active: true;
}

type ListResponse<T> = T[] | { results?: T[]; count?: number; success?: boolean };

export async function fetchReports() {
  const res = await authFetch(`${API_V1_BASE}${PATH}?limit=100&offset=0`, { headers: authHeaders() });
  const data = await handleResponse<ListResponse<Report>>(res);
  return {
    count: Array.isArray(data) ? data.length : data.count ?? data.results?.length ?? 0,
    results: Array.isArray(data) ? data : data.results ?? [],
  };
}

export async function createReport(data: ReportSubscriptionInput) {
  const res = await authFetch(`${API_V1_BASE}${PATH}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<Report>(res);
}

export async function patchReport(id: number, data: Partial<ReportSubscriptionInput>) {
  const res = await authFetch(`${API_V1_BASE}${PATH}${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<Report>(res);
}

export interface SendReportResult {
  success: boolean;
  skipped?: boolean;
  log_id: number | null;
  recipients_count: number;
  sent_at?: string;
  message?: string;
  next_run_at?: string | null;
  error?: string;
}

export async function sendReportNow(id: number) {
  const res = await authFetch(`${API_V1_BASE}${PATH}${id}/send-now/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({}),
  });
  return handleResponse<SendReportResult>(res);
}

export async function deleteReport(id: number) {
  const res = await authFetch(`${API_V1_BASE}${PATH}${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export interface ReportDeliveryLog {
  id: number;
  campaign: number | null;
  subscription: number | null;
  email_config_id: number | null;
  format: ReportFormat;
  subject: string;
  recipients: string[];
  status: "sent" | "failed";
  sent_at: string | null;
  error_message: string;
  attachment_names: string[];
  report_data: Record<string, unknown>;
  created_at: string;
}

export interface SendCampaignReportPayload {
  recipients?: string[];
  subject?: string;
  email_config_id?: number;
  format?: ReportFormat;
  include_sent_stats?: boolean;
  include_delivery_stats?: boolean;
  include_message_stats?: boolean;
}

type Envelope<T> = { success: boolean; data: T };

function unwrapEnvelope<T>(value: T | Envelope<T>): T {
  return value && typeof value === "object" && "data" in value
    ? value.data
    : value as T;
}

export async function fetchCampaignReportHistory(campaignId: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/report-history/`, { headers: authHeaders() });
  const data = await handleResponse<ReportDeliveryLog[] | { results?: ReportDeliveryLog[] }>(res);
  return Array.isArray(data) ? data : data.results ?? [];
}

export async function sendCampaignReport(campaignId: number, payload: SendCampaignReportPayload) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/reports/email/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });
  return unwrapEnvelope(await handleResponse<ReportDeliveryLog | Envelope<ReportDeliveryLog>>(res));
}

export async function resendCampaignReport(logId: number) {
  const res = await authFetch(`${API_V1_BASE}/report-delivery-logs/${logId}/resend/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return unwrapEnvelope(await handleResponse<ReportDeliveryLog | Envelope<ReportDeliveryLog>>(res));
}
