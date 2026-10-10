const API_BASE = (import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8002/api/v1").replace(
  /\/+$/,
  "",
);
const ACCESS_TOKEN_KEY = "sms-admin-access-token";
const REFRESH_TOKEN_KEY = "sms-admin-refresh-token";

export type ApiUser = {
  id: number;
  user_id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  department: string;
  role: "ADMIN" | "CAMPAIGN_MANAGER";
  is_active: boolean;
  is_locked: boolean;
  require_password_change: boolean;
  last_login: string | null;
  notes: string;
  tps_limit: number | null;
  assigned_smscs: number[];
  assigned_sender_ids: number[];
  assigned_channels: number[];
  assigned_tps_configs: number[];
  assigned_n_address_configs: number[];
  assigned_n_addresses: number[];
  assigned_config_counts: {
    smsc: number;
    sender_ids: number;
    channels: number;
    tps: number;
    n_address_configs: number;
    n_addresses: number;
  };
};

export type ApiUserCampaign = {
  id: number;
  name: string;
  sender_id: string;
  owner_emails: string[];
  channels_id: number[];
  channel_names: string[];
  status: string;
  is_ready_to_execute: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
};

export type ApiConfig = {
  id: number;
  [key: string]: unknown;
};

export type AdminEmailConfig = {
  configured?: boolean;
  id?: number;
  name?: string;
  host?: string;
  port?: number;
  username?: string;
  has_password?: boolean;
  use_tls?: boolean;
  use_ssl?: boolean;
  from_email?: string;
  default_from_email?: string;
  is_default?: boolean;
  is_active?: boolean;
  last_tested_at?: string | null;
  last_test_status?: string;
  last_test_message?: string;
  created_at?: string;
  updated_at?: string;
};

export type AdminEmailServiceInput = {
  name: string;
  host: string;
  port: number;
  username: string;
  password?: string;
  default_from_email: string;
  use_tls: boolean;
  use_ssl: boolean;
  is_default: boolean;
  is_active: boolean;
};

export type UserInput = {
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  department: string;
  role: "ADMIN" | "CAMPAIGN_MANAGER";
  password?: string;
  is_active: boolean;
  is_locked: boolean;
  notes: string;
  tps_limit: number | null;
  assigned_smscs: number[];
  assigned_sender_ids: number[];
  assigned_channels: number[];
  assigned_tps_configs: number[];
  assigned_n_address_configs: number[];
  assigned_n_addresses: number[];
};

export class AdminApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
  }
}

export function getAccessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAdminTokens() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.dispatchEvent(new Event("admin-workspace-invalidated"));
}

export async function adminRequest<T>(
  path: string,
  init: RequestInit = {},
  authenticated = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = authenticated ? getAccessToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const request = (accessToken: string | null) => {
    const requestHeaders = new Headers(headers);
    if (authenticated && accessToken) requestHeaders.set("Authorization", `Bearer ${accessToken}`);
    return fetch(`${API_BASE}${path}`, { ...init, headers: requestHeaders });
  };
  let response: Response;
  try {
    response = await request(token);
  } catch (error) {
    throw new AdminApiError(
      error instanceof Error
        ? `Could not reach the admin backend: ${error.message}`
        : "Could not reach the admin backend.",
      0,
    );
  }

  if (response.status === 401 && authenticated) {
    const refresh = window.localStorage.getItem(REFRESH_TOKEN_KEY);
    if (refresh && !path.startsWith("/admin/auth/")) {
      try {
        const refreshed = await fetch(`${API_BASE}/admin/auth/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (refreshed.ok) {
          const tokens = await refreshed.json() as { access: string; refresh?: string };
          window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
          if (tokens.refresh) window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
          response = await request(tokens.access);
          if (response.status === 401) {
            clearAdminTokens();
            window.dispatchEvent(new Event("admin-session-expired"));
          }
        } else {
          clearAdminTokens();
          window.dispatchEvent(new Event("admin-session-expired"));
        }
      } catch {
        clearAdminTokens();
        window.dispatchEvent(new Event("admin-session-expired"));
      }
    } else {
      clearAdminTokens();
      window.dispatchEvent(new Event("admin-session-expired"));
    }
  }
  const invalidatesWorkspace =
    /^\/admin\/(users|smsc-configs|sender-ids|channels|tps-configs|n-address-configs|n-addresses)(?:\/|$)/.test(
      path,
    );
  if (response.ok && (init.method ?? "GET").toUpperCase() !== "GET" && invalidatesWorkspace) {
    window.dispatchEvent(new Event("admin-workspace-invalidated"));
  }
  if (response.status === 204) return undefined as T;

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminApiError(errorMessage(payload, response.statusText), response.status);
  }
  return payload as T;
}

export async function adminLogin(username: string, password: string) {
  const result = await adminRequest<
    { must_change_password: true } | { access: string; refresh: string }
  >(
    "/admin/auth/login/",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    false,
  );
  if ("must_change_password" in result) return result;
  const tokens = result;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
  return { user: await adminRequest<ApiUser>("/admin/me/") };
}

export function changeInitialAdminPassword(
  username: string,
  currentPassword: string,
  newPassword: string,
) {
  return adminRequest<{ success: true }>(
    "/admin/auth/initial-password/",
    {
      method: "POST",
      body: JSON.stringify({
        username,
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
    false,
  );
}

export function requestAdminPasswordResetLink(email: string) {
  return adminRequest<{ detail: string }>(
    "/admin/auth/password-reset/request/",
    { method: "POST", body: JSON.stringify({ email }) },
    false,
  );
}

export function confirmAdminPasswordResetToken(
  challenge: number,
  token: string,
  newPassword: string,
) {
  return adminRequest<{ success: true }>(
    "/admin/auth/password-reset/confirm/",
    {
      method: "POST",
      body: JSON.stringify({ challenge, token, new_password: newPassword }),
    },
    false,
  );
}

export function getAdminEmailConfig() {
  return adminRequest<AdminEmailConfig>("/admin/email-config/");
}

export function saveAdminEmailConfig(config: {
  name: string;
  host: string;
  port: number;
  username: string;
  password?: string;
  use_tls: boolean;
  use_ssl: boolean;
  from_email: string;
}) {
  return adminRequest<AdminEmailConfig>("/admin/email-config/", {
    method: "PATCH",
    body: JSON.stringify(config),
  });
}

export function testAdminEmailConfig(recipient: string) {
  return adminRequest<{ success: true }>("/admin/email-config/", {
    method: "POST",
    body: JSON.stringify({ recipient }),
  });
}

export function listAdminEmailServices() {
  return adminRequest<{ results: AdminEmailConfig[] }>("/admin/email-services/");
}

export function createAdminEmailService(config: AdminEmailServiceInput) {
  return adminRequest<AdminEmailConfig>("/admin/email-services/", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function updateAdminEmailService(id: number, config: Partial<AdminEmailServiceInput>) {
  return adminRequest<AdminEmailConfig>(`/admin/email-services/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(config),
  });
}

export function deleteAdminEmailService(id: number) {
  return adminRequest<void>(`/admin/email-services/${id}/`, { method: "DELETE" });
}

export function testAdminEmailService(id: number, testEmail: string) {
  return adminRequest<{ success: boolean; message: string }>(`/admin/email-services/${id}/test/`, {
    method: "POST",
    body: JSON.stringify({ test_email: testEmail }),
  });
}

export function listUsers() {
  return adminRequest<ApiUser[]>("/admin/users/");
}

export function listUserCampaigns(profileId: number) {
  return adminRequest<ApiUserCampaign[]>(`/admin/users/${profileId}/campaigns/`);
}

export function saveUser(profileId: number | null, user: UserInput) {
  const path = profileId === null ? "/admin/users/" : `/admin/users/${profileId}/`;
  return adminRequest<ApiUser>(path, {
    method: profileId === null ? "POST" : "PATCH",
    body: JSON.stringify(user),
  });
}

export function deleteUser(profileId: number) {
  return adminRequest<void>(`/admin/users/${profileId}/`, { method: "DELETE" });
}

export function resetUserPassword(profileId: number, password: string) {
  return adminRequest<void>(`/admin/users/${profileId}/password-reset/`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function listConfig(endpoint: string) {
  return adminRequest<ApiConfig[]>(`/admin/${endpoint}/`);
}

export function saveConfig(endpoint: string, id: number | null, payload: Record<string, unknown>) {
  return adminRequest<ApiConfig>(
    id === null ? `/admin/${endpoint}/` : `/admin/${endpoint}/${id}/`,
    {
      method: id === null ? "POST" : "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteConfig(endpoint: string, id: number) {
  return adminRequest<void>(`/admin/${endpoint}/${id}/`, { method: "DELETE" });
}

function errorMessage(payload: unknown, fallback: string) {
  if (typeof payload === "string") return payload;
  if (payload && typeof payload === "object") {
    const values = Object.values(payload as Record<string, unknown>).flatMap((value) =>
      Array.isArray(value) ? value : [value],
    );
    const messages = values.filter((value): value is string => typeof value === "string");
    if (messages.length > 0) return messages.join(" ");
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback || "The request failed.";
}
