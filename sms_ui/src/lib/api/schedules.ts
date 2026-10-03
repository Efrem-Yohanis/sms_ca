import { authFetch, handleResponse, API_V1_BASE, authHeaders } from "./base";
import type { PaginatedResponse } from "./base";

export interface ApiScheduleListItem {
  id: number;
  campaign: number;
  campaign_name: string;
  campaign_info?: {
    id: number;
    name: string;
    status: string;
    execution_status: string;
  };
  schedule_type: string;
  schedule_type_display: string;
  campaign_status: string;
  campaign_status_display: string;
  current_window_status: string;
  current_window_status_display: string;
  schedule_summary: string;
  upcoming_windows: { date: string; windows: number[]; type: string; day_name?: string }[];
  start_date: string;
  end_date: string | null;
  run_days: number[];
  time_windows: { start: string; end: string }[];
  timezone: string;
  current_round: number;
  current_window_date: string | null;
  current_window_index: number;
  next_run_date: string | null;
  next_run_window: number;
  completed_windows: unknown[];
  total_windows_completed: number;
  is_active: boolean;
  auto_reset: boolean;
  created_at: string;
  updated_at: string;
  last_processed_at: string | null;
}

export interface ApiScheduleDetail extends ApiScheduleListItem {
  next_execution?: { date: string; window_index: number; window_time: { start: string; end: string } };
  execution_progress?: { current_round: number; total_windows_completed: number; current_window_status: string; current_window_date: string };
}

export interface ScheduleSummary {
  total_schedules: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  by_window_status: Record<string, number>;
  active_schedules: number;
  inactive_schedules: number;
  running_today: number;
}

export interface ScheduleTypeOption {
  value: string;
  display: string;
}

export interface ScheduleCreatePayload {
  schedule_type: string;
  start_date: string;
  end_date?: string | null;
  run_days?: number[];
  time_windows: { start: string; end: string }[];
  timezone: string;
  auto_reset: boolean;
}

export async function fetchSchedules(page = 1, pageSize = 10, filters?: Record<string, string>) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (filters) Object.entries(filters).forEach(([k, v]) => v && params.set(k, v));
  const res = await authFetch(`${API_V1_BASE}/schedules/?${params}`, { headers: authHeaders() });
  return handleResponse<PaginatedResponse<ApiScheduleListItem>>(res);
}

export async function fetchScheduleDetail(id: number) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/`, { headers: authHeaders() });
  return handleScheduleResponse<ApiScheduleDetail>(res);
}

export async function fetchScheduleSummary() {
  const res = await authFetch(`${API_V1_BASE}/schedules/summary/`, { headers: authHeaders() });
  return handleResponse<ScheduleSummary>(res);
}

export async function fetchScheduleTypes() {
  return [
    { value: "once", display: "One Time" },
    { value: "daily", display: "Daily" },
    { value: "weekly", display: "Weekly" },
    { value: "monthly", display: "Monthly" },
  ];
}

async function handleScheduleResponse<T>(res: Response): Promise<T> {
  const payload = await handleResponse<T | { data: T }>(res);
  return payload && typeof payload === "object" && "data" in payload
    ? payload.data
    : payload as T;
}

export async function fetchSchedule(campaignId: number) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/schedule/`, { headers: authHeaders() });
  return handleScheduleResponse<ApiScheduleDetail>(res);
}

export async function createSchedule(campaignId: number, data: ScheduleCreatePayload) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/schedule/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleScheduleResponse<ApiScheduleDetail>(res);
}

export async function updateSchedule(campaignId: number, data: ScheduleCreatePayload) {
  const res = await authFetch(`${API_V1_BASE}/campaigns/${campaignId}/schedule/`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleScheduleResponse<ApiScheduleDetail>(res);
}

export async function fetchUpcomingWindows(id: number, limit = 5) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/upcoming_windows/?limit=${limit}`, { headers: authHeaders() });
  return handleResponse<{ date: string; windows: number[]; type: string; day_name?: string }[]>(res);
}

export async function updateScheduleById(id: number, data: Record<string, unknown>) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleScheduleResponse<ApiScheduleDetail>(res);
}

export async function deleteScheduleById(id: number) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/`, { method: "DELETE", headers: authHeaders() });
  return handleResponse<void>(res);
}

export async function activateSchedule(id: number) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/activate/`, { method: "POST", headers: authHeaders() });
  return handleResponse<{ detail: string; is_active: boolean }>(res);
}

export async function deactivateSchedule(id: number) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/deactivate/`, { method: "POST", headers: authHeaders() });
  return handleResponse<{ detail: string; is_active: boolean }>(res);
}

export async function resetSchedule(id: number) {
  const res = await authFetch(`${API_V1_BASE}/schedules/${id}/reset/`, { method: "POST", headers: authHeaders() });
  return handleResponse(res);
}
