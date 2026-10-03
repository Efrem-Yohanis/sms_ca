import { API_V1_BASE, authFetch, authHeaders, handleResponse } from "./base";

export interface DashboardCampaign {
  id: number;
  name: string;
  owner: string;
  schedule_type: string | null;
  sender_id: string;
  channels: string[];
  status: string;
  execution_status: string;
  target_audience: number | null;
  success_sent: number | null;
  failed_sent: number | null;
  success_delivery: number | null;
  failed_delivery: number | null;
}

export interface DashboardData {
  viewer: { first_name: string; is_superuser: boolean };
  kpis: {
    total_campaigns: number;
    active_campaigns: number;
    draft_campaigns: number;
    paused_campaigns: number;
    completed_campaigns: number;
  };
  sent_vs_delivery: {
    success_sent: number;
    failed_sent: number;
    success_delivery: number;
    failed_delivery: number;
  };
  status_distribution: Record<string, number>;
  campaign_options: { id: number; name: string }[];
  campaigns: {
    count: number;
    page: number;
    page_size?: number;
    next: number | null;
    previous: number | null;
    results: DashboardCampaign[];
  };
}

interface DashboardResponse {
  success: boolean;
  data: DashboardData;
  error?: string;
}

export async function fetchDashboard(params: URLSearchParams): Promise<DashboardData> {
  const query = params.toString();
  const url = `${API_V1_BASE}/dashboard/${query ? `?${query}` : ""}`;
  const response = await authFetch(url, { headers: authHeaders() });
  const body = await handleResponse<DashboardResponse>(response);
  if (!body.success) throw new Error(body.error || "Could not load dashboard");
  return body.data;
}
