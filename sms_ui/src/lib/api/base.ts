export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
export const API_V1_BASE = `${API_BASE}/api/v1`;

function getToken(): string | null {
  return localStorage.getItem("auth_token");
}

function getRefreshToken(): string | null {
  return localStorage.getItem("auth_refresh_token");
}

function setToken(token: string) {
  localStorage.setItem("auth_token", token);
}

function clearAuth() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_refresh_token");
  localStorage.removeItem("auth_username");
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/* -------- Auto-refresh wrapper -------- */

let refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("No refresh token available");
  }
  const res = await fetch(`${API_V1_BASE}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) {
    clearAuth();
    window.location.href = "/login";
    throw new Error("Session expired. Please log in again.");
  }
  const data = await res.json();
  setToken(data.access);
  return data.access;
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const requestHeaders = () => {
    const headers = authHeaders();
    if (typeof FormData !== "undefined" && options.body instanceof FormData) {
      delete headers["Content-Type"];
    }
    return headers;
  };
  const res = await fetch(url, { ...options, headers: requestHeaders() });
  if (res.status !== 401) return res;

  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => { refreshPromise = null; });
  }
  await refreshPromise;

  return fetch(url, { ...options, headers: requestHeaders() });
}
