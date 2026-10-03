import { API_V1_BASE, authFetch, authHeaders } from "./base";
import { fetchAssignedConfigurations } from "./configurations";

export interface TestMessage {
  id: number;
  sender_id: string;
  recipient: string;
  channel_code: string;
  message_content: string;
  test_campaign_id: number;
  provider_message_id: string;
  provider_status: string;
  http_status: number | null;
  accepted: boolean;
  duration_ms: number;
  error_message: string;
  created_at: string;
  request_url: string;
  request_method: string;
  request_payload: Record<string, unknown>;
  response_payload: unknown;
}

export interface TestMessageInput {
  sender_id: string;
  recipient: string;
  channel_code: string;
  message_content: string;
  test_campaign_id: number;
}

export interface TestSmsOption {
  id: number;
  code?: string;
  name: string;
  sender_id?: string;
  is_active: boolean;
  is_default?: boolean;
}

export class TestSmsApiError extends Error {
  fields: Record<string, string[]>;

  constructor(message: string, fields: Record<string, string[]> = {}) {
    super(message);
    this.name = "TestSmsApiError";
    this.fields = fields;
  }
}

async function readJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const errors = body.errors && typeof body.errors === "object" ? body.errors as Record<string, string[]> : {};
    const message = body.error || body.detail || "Request failed";
    throw new TestSmsApiError(message, errors);
  }
  return body as T;
}

export async function fetchTestSmsOptions() {
  const assigned = await fetchAssignedConfigurations();
  return {
    senderIds: assigned.sender_ids.filter((row) => row.is_active),
    channels: assigned.channels.filter((row) => row.is_active),
  };
}

export async function fetchTestMessages(limit = 10) {
  const response = await authFetch(`${API_V1_BASE}/test-sms/?limit=${limit}&offset=0`, {
    headers: authHeaders(),
  });
  return readJson<{ success: boolean; count: number; results: TestMessage[] }>(response);
}

export async function fetchTestMessage(id: number) {
  const response = await authFetch(`${API_V1_BASE}/test-sms/${id}/`, { headers: authHeaders() });
  const result = await readJson<{ success: boolean; data: TestMessage }>(response);
  return result.data;
}

export async function createTestMessage(input: TestMessageInput) {
  const response = await authFetch(`${API_V1_BASE}/test-sms/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(input),
  });
  const result = await readJson<{ success: boolean; data: TestMessage }>(response);
  return result.data;
}

export async function resendTestMessage(id: number) {
  const response = await authFetch(`${API_V1_BASE}/test-sms/${id}/resend/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({}),
  });
  const result = await readJson<{ success: boolean; data: TestMessage }>(response);
  return result.data;
}

export async function deleteTestMessage(id: number) {
  const response = await authFetch(`${API_V1_BASE}/test-sms/${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new TestSmsApiError(body.error || body.detail || "Unable to delete test message", body.errors ?? {});
  }
}