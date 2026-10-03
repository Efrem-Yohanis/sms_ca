const API_BASE = (
  import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8002/api/v1"
).replace(/\/+$/, "");
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

export type ApiConfig = {
  id: number;
  [key: string]: unknown;
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

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (error) {
    throw new AdminApiError(
      error instanceof Error
        ? `Could not reach the admin backend: ${error.message}`
        : "Could not reach the admin backend.",
      0,
    );
  }

  if (response.status === 401 && authenticated) {
    clearAdminTokens();
    window.dispatchEvent(new Event("admin-session-expired"));
  }
  if (response.status === 204) return undefined as T;

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new AdminApiError(errorMessage(payload, response.statusText), response.status);
  }
  return payload as T;
}

export async function adminLogin(username: string, password: string) {
  const tokens = await adminRequest<{ access: string; refresh: string }>(
    "/admin/auth/login/",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    false,
  );
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
  return adminRequest<ApiUser>("/admin/me/");
}

export function listUsers() {
  return adminRequest<ApiUser[]>("/admin/users/");
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
