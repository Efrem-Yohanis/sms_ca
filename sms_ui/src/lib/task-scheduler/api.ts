import { authFetch, API_V1_BASE, authHeaders, handleResponse } from "@/lib/api/base";
import type { Run, Schedule } from "@/lib/task-scheduler/store";

const BASE = `${API_V1_BASE}/task-scheduler`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(`${BASE}/${path.replace(/^\/+/, "")}`, {
    ...init,
    headers: { ...authHeaders(), ...init?.headers },
  });
  return handleResponse<T>(response);
}

export const schedulerApi = {
  async listSchedules(): Promise<Schedule[]> {
    const schedules: Schedule[] = [];
    let offset = 0;
    let count = Number.POSITIVE_INFINITY;
    while (schedules.length < count) {
      const page = await request<{ count: number; results: Schedule[] }>(
        `schedules/?limit=200&offset=${offset}`,
      );
      schedules.push(...page.results);
      count = page.count;
      offset += page.results.length;
      if (!page.results.length) break;
    }
    return schedules;
  },
  listRuns: (scheduleId?: string) =>
    request<Run[]>(scheduleId
      ? `schedules/${encodeURIComponent(scheduleId)}/runs/`
      : "runs/"),
  getLogs: (scheduleId: string, runId: string) =>
    request<Run["logs"]>(
      `schedules/${encodeURIComponent(scheduleId)}/runs/${encodeURIComponent(runId)}/logs/`,
    ),
  async saveSchedule(schedule: Schedule, isNew: boolean): Promise<Schedule> {
    const path = isNew ? "schedules/" : `schedules/${encodeURIComponent(schedule.id)}/`;
    const response = await authFetch(`${BASE}/${path}`, {
      method: isNew ? "POST" : "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(schedule),
    });
    const body = await handleResponse<Schedule | { id?: string; airflowSyncError?: string }>(response);
    if (response.status === 202 && body && "id" in body && body.id) {
      const saved = await request<Schedule>(`schedules/${encodeURIComponent(body.id)}/`);
      return { ...saved, airflowSyncError: body.airflowSyncError ?? saved.airflowSyncError };
    }
    return body as Schedule;
  },
  deleteSchedule: (scheduleId: string) =>
    request<void>(`schedules/${encodeURIComponent(scheduleId)}/`, { method: "DELETE" }),
  setPaused: (scheduleId: string, paused: boolean) =>
    request<Schedule>(`schedules/${encodeURIComponent(scheduleId)}/pause/`, {
      method: "POST",
      body: JSON.stringify({ paused }),
    }),
  runNow: (scheduleId: string) =>
    request<Run>(`schedules/${encodeURIComponent(scheduleId)}/runs/trigger/`, { method: "POST" }),
};
