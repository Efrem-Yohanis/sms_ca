import { API_V1_BASE, authFetch, authHeaders, handleResponse } from "./base";

const ADMIN_API_V1_BASE = (
  import.meta.env.VITE_ADMIN_API_BASE_URL || "http://localhost:8002"
).replace(/\/+$/, "") + "/api/v1";

/* -------- Types -------- */

export interface SupportedLanguage {
  id: number;
  code: string;
  name: string;
  native_name?: string;
  is_active: boolean;
  created_at?: string;
}

export interface SupportedChannel {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  created_at?: string;
}

export interface DataSource {
  id: number;
  name: string;
  database_type: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  password?: string;
  is_active: boolean;
  created_at?: string;
}

export interface DatabaseConnectionInput {
  database_type: string;
  host: string;
  port: number;
  database_name: string;
  username: string;
  password: string;
  ssl_required?: boolean;
}

export interface SenderIdConfig {
  id: number;
  sender_id: string;
  name: string;
  description: string;
  is_active: boolean;
  is_default: boolean;
  created_at?: string;
}

export interface EmailService {
  id: number;
  name: string;
  description?: string;
  host: string;
  port: number;
  username: string;
  password?: string;
  default_from_email: string;
  use_tls: boolean;
  use_ssl: boolean;
  is_default: boolean;
  is_active: boolean;
  last_tested_at?: string | null;
  last_test_status?: string;
  last_test_message?: string;
  created_at?: string;
}

export interface SMSCConfig {
  id: number;
  name: string;
  description?: string;
  base_url: string;
  send_endpoint: string;
  http_method: "POST" | "GET" | "PUT";
  auth_type: "none" | "api_key" | "bearer" | "basic";
  api_key?: string;
  api_secret?: string;
  username?: string;
  password?: string;
  extra_headers: Record<string, string>;
  extra_params: Record<string, unknown>;
  rate_limit_per_second: number;
  rate_limit_per_minute: number;
  max_retries: number;
  retry_backoff_seconds: number;
  request_timeout_seconds: number;
  connect_timeout_seconds: number;
  is_default: boolean;
  is_active: boolean;
  last_tested_at?: string | null;
  last_test_status?: string;
  last_test_message?: string;
}

export interface GlobalTPSConfig {
  id: number;
  name: string;
  description: string;
  global_tps: number;
  is_default: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface NAddressesConfig {
  id: number;
  name: string;
  description: string;
  max_addresses_per_request: number;
  is_default: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface NAddress {
  id: number;
  value: string;
  address_type: "MSISDN" | "ALPHANUMERIC" | "POOL";
  smsc: number;
  channel: number | null;
  sender_id: number | null;
  is_active: boolean;
  tps_cap: number | null;
  notes: string;
  created_at?: string;
  updated_at?: string;
}

export interface AssignedConfigurations {
  smsc: SMSCConfig[];
  sender_ids: SenderIdConfig[];
  channels: SupportedChannel[];
  tps_configs: GlobalTPSConfig[];
  n_address_configs: NAddressesConfig[];
  n_addresses: NAddress[];
  tps_limit: number | null;
}

export async function fetchAssignedConfigurations(): Promise<AssignedConfigurations> {
  const response = await authFetch(`${ADMIN_API_V1_BASE}/configurations/assigned/`, {
    headers: authHeaders(),
  });
  return handleResponse<AssignedConfigurations>(response);
}

export interface CustomerProfileConfig {
  id: number;
  name: string;
  database_config: number;
  database_name?: string;
  table_name: string;
  msisdn_column: string;
  language_column: string;
  default_language: number;
  is_active: boolean;
  created_at?: string;
}

export interface CustomerProfilePreview {
  success: boolean;
  data: {
    profile_id: number;
    profile_name: string;
    total: number;
    matched: number;
    unmatched: number;
    default_language: number;
    rows: { msisdn: string; language: string | null; matched: boolean }[];
  };
}

/* -------- Generic CRUD helpers -------- */

type ApiListResponse<T> = T[] | { results?: T[]; data?: T[] };
type ApiEnvelope<T> = { success: boolean; data: T };
function unwrapApiData<T>(value: T | ApiEnvelope<T>): T {
  if (value && typeof value === "object" && "success" in value && "data" in value) {
    return value.data;
  }
  return value as T;
}

async function crudList<T>(path: string) {
  const res = await authFetch(`${API_V1_BASE}${path}`, { headers: authHeaders() });
  const data = await handleResponse<ApiListResponse<T>>(res);
  const results = Array.isArray(data) ? data : data.results ?? data.data ?? [];
  return { results };
}

async function crudRetrieve<T>(path: string, id: number) {
  const res = await authFetch(`${API_V1_BASE}${path}${id}/`, { headers: authHeaders() });
  return unwrapApiData(await handleResponse<T | ApiEnvelope<T>>(res));
}

async function crudCreate<T>(path: string, data: Partial<T>) {
  const res = await authFetch(`${API_V1_BASE}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return unwrapApiData(await handleResponse<T | ApiEnvelope<T>>(res));
}

async function crudUpdate<T>(path: string, id: number, data: Partial<T>) {
  const res = await authFetch(`${API_V1_BASE}${path}${id}/`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return unwrapApiData(await handleResponse<T | ApiEnvelope<T>>(res));
}

async function crudPatch<T>(path: string, id: number, data: Partial<T>) {
  const res = await authFetch(`${API_V1_BASE}${path}${id}/`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return unwrapApiData(await handleResponse<T | ApiEnvelope<T>>(res));
}

async function crudDelete(path: string, id: number) {
  const res = await authFetch(`${API_V1_BASE}${path}${id}/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

async function crudAction<T>(path: string, id: number, action: string) {
  const res = await authFetch(`${API_V1_BASE}${path}${id}/${action}/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<T>(res);
}

export interface TestConnectionResult {
  success?: boolean;
  status?: string;
  message?: string;
  detail?: string;
}

/* -------- 6.1 Languages -------- */
const LANG_PATH = "/languages/";
export const fetchLanguages = () => crudList<SupportedLanguage>(LANG_PATH);
export const getLanguage = (id: number) => crudRetrieve<SupportedLanguage>(LANG_PATH, id);
export const createLanguage = (d: Partial<SupportedLanguage>) => crudCreate<SupportedLanguage>(LANG_PATH, d);
export const updateLanguage = (id: number, d: Partial<SupportedLanguage>) => crudUpdate<SupportedLanguage>(LANG_PATH, id, d);
export const patchLanguage = (id: number, d: Partial<SupportedLanguage>) => crudPatch<SupportedLanguage>(LANG_PATH, id, d);
export const deleteLanguage = (id: number) => crudDelete(LANG_PATH, id);
export const toggleLanguageStatus = (id: number) => crudAction<SupportedLanguage>(LANG_PATH, id, "toggle-status");

/* -------- 6.2 Channels -------- */
const CHAN_PATH = "/channels/";
export const fetchChannels = () => crudList<SupportedChannel>(CHAN_PATH);
export const getChannel = (id: number) => crudRetrieve<SupportedChannel>(CHAN_PATH, id);
export const createChannel = (d: Partial<SupportedChannel>) => crudCreate<SupportedChannel>(CHAN_PATH, d);
export const updateChannel = (id: number, d: Partial<SupportedChannel>) => crudUpdate<SupportedChannel>(CHAN_PATH, id, d);
export const patchChannel = (id: number, d: Partial<SupportedChannel>) => crudPatch<SupportedChannel>(CHAN_PATH, id, d);
export const deleteChannel = (id: number) => crudDelete(CHAN_PATH, id);
export const toggleChannelStatus = (id: number) => crudAction<SupportedChannel>(CHAN_PATH, id, "toggle-status");

/* -------- 6.3 Data Sources -------- */
const DS_PATH = "/databases/";
export const fetchDataSources = () => crudList<DataSource>(DS_PATH);
export const getDataSource = (id: number) => crudRetrieve<DataSource>(DS_PATH, id);
export const createDataSource = (d: Partial<DataSource>) => crudCreate<DataSource>(DS_PATH, d);
export const updateDataSource = (id: number, d: Partial<DataSource>) => crudUpdate<DataSource>(DS_PATH, id, d);
export const patchDataSource = (id: number, d: Partial<DataSource>) => crudPatch<DataSource>(DS_PATH, id, d);
export const deleteDataSource = (id: number) => crudDelete(DS_PATH, id);
export async function testDataSourceConnection(id: number) {
  const res = await authFetch(`${API_V1_BASE}${DS_PATH}${id}/test/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return handleResponse<TestConnectionResult>(res);
}

export async function testDatabaseConnection(data: DatabaseConnectionInput) {
  const res = await authFetch(`${API_V1_BASE}/databases/test-params/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(data),
  });
  return handleResponse<TestConnectionResult>(res);
}

export async function previewCustomerProfile(id: number, msisdns: string[]) {
  const res = await authFetch(`${API_V1_BASE}/databases/customer-profiles/${id}/preview/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ msisdns }),
  });
  return handleResponse<CustomerProfilePreview>(res);
}

/* -------- 6.4 Sender IDs -------- */
const SENDER_PATH = "/sender-ids/";
export const fetchSenderIds = () => crudList<SenderIdConfig>(SENDER_PATH);
export const getSenderId = (id: number) => crudRetrieve<SenderIdConfig>(SENDER_PATH, id);
export const createSenderId = (d: Partial<SenderIdConfig>) => crudCreate<SenderIdConfig>(SENDER_PATH, d);
export const updateSenderId = (id: number, d: Partial<SenderIdConfig>) => crudUpdate<SenderIdConfig>(SENDER_PATH, id, d);
export const patchSenderId = (id: number, d: Partial<SenderIdConfig>) => crudPatch<SenderIdConfig>(SENDER_PATH, id, d);
export const deleteSenderId = (id: number) => crudDelete(SENDER_PATH, id);
export const testSenderIdConnection = (id: number) => crudAction<TestConnectionResult>(SENDER_PATH, id, "test-connection");

/* -------- 6.5 Email Services -------- */
const EMAIL_PATH = "/email-config/";
export const fetchEmailServices = () => crudList<EmailService>(EMAIL_PATH);
export const getEmailService = (id: number) => crudRetrieve<EmailService>(EMAIL_PATH, id);
export const createEmailService = (d: Partial<EmailService>) => crudCreate<EmailService>(EMAIL_PATH, d);
export const updateEmailService = (id: number, d: Partial<EmailService>) => crudUpdate<EmailService>(EMAIL_PATH, id, d);
export const patchEmailService = (id: number, d: Partial<EmailService>) => crudPatch<EmailService>(EMAIL_PATH, id, d);
export const deleteEmailService = (id: number) => crudDelete(EMAIL_PATH, id);
export async function testEmailServiceConnection(id: number, testEmail: string) {
  const res = await authFetch(`${API_V1_BASE}${EMAIL_PATH}${id}/test/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ test_email: testEmail }),
  });
  return handleResponse<TestConnectionResult>(res);
}

export async function testEmailServiceSettings(data: Partial<EmailService>, testEmail: string) {
  const res = await authFetch(`${API_V1_BASE}${EMAIL_PATH}test/`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ ...data, test_email: testEmail }),
  });
  return handleResponse<TestConnectionResult>(res);
}

/* -------- 6.6 SMSC Configurations -------- */
const SMSC_PATH = "/smsc-configs/";
export const fetchSMSCConfigs = () => crudList<SMSCConfig>(SMSC_PATH);
export const getSMSCConfig = (id: number) => crudRetrieve<SMSCConfig>(SMSC_PATH, id);
export const createSMSCConfig = (d: Partial<SMSCConfig>) => crudCreate<SMSCConfig>(SMSC_PATH, d);
export const updateSMSCConfig = (id: number, d: Partial<SMSCConfig>) => crudUpdate<SMSCConfig>(SMSC_PATH, id, d);
export const patchSMSCConfig = (id: number, d: Partial<SMSCConfig>) => crudPatch<SMSCConfig>(SMSC_PATH, id, d);
export const deleteSMSCConfig = (id: number) => crudDelete(SMSC_PATH, id);

/* -------- Global TPS and N-address settings -------- */
const GLOBAL_TPS_PATH = "/global-tps-config/";
export const fetchGlobalTPSConfigs = () => crudList<GlobalTPSConfig>(GLOBAL_TPS_PATH);
export const createGlobalTPSConfig = (data: Partial<GlobalTPSConfig>) => crudCreate<GlobalTPSConfig>(GLOBAL_TPS_PATH, data);
export const patchGlobalTPSConfig = (id: number, data: Partial<GlobalTPSConfig>) => crudPatch<GlobalTPSConfig>(GLOBAL_TPS_PATH, id, data);
export const deleteGlobalTPSConfig = (id: number) => crudDelete(GLOBAL_TPS_PATH, id);
export const fetchActiveGlobalTPSConfig = async () => {
  const response = await authFetch(`${API_V1_BASE}${GLOBAL_TPS_PATH}active/`, { headers: authHeaders() });
  return unwrapApiData(await handleResponse<GlobalTPSConfig | ApiEnvelope<GlobalTPSConfig>>(response));
};

const N_ADDRESSES_PATH = "/n-addresses-config/";
export const fetchNAddressesConfigs = () => crudList<NAddressesConfig>(N_ADDRESSES_PATH);
export const createNAddressesConfig = (data: Partial<NAddressesConfig>) => crudCreate<NAddressesConfig>(N_ADDRESSES_PATH, data);
export const patchNAddressesConfig = (id: number, data: Partial<NAddressesConfig>) => crudPatch<NAddressesConfig>(N_ADDRESSES_PATH, id, data);
export const deleteNAddressesConfig = (id: number) => crudDelete(N_ADDRESSES_PATH, id);
export const fetchActiveNAddressesConfig = async () => {
  const response = await authFetch(`${API_V1_BASE}${N_ADDRESSES_PATH}active/`, { headers: authHeaders() });
  return unwrapApiData(await handleResponse<NAddressesConfig | ApiEnvelope<NAddressesConfig>>(response));
};

/* -------- 6.6 Customer Profile Configs -------- */
const CPC_PATH = "/databases/customer-profiles/";
export const fetchCustomerProfileConfigs = () => crudList<CustomerProfileConfig>(CPC_PATH);
export const getCustomerProfileConfig = (id: number) => crudRetrieve<CustomerProfileConfig>(CPC_PATH, id);
export const createCustomerProfileConfig = (d: Partial<CustomerProfileConfig>) => crudCreate<CustomerProfileConfig>(CPC_PATH, d);
export const updateCustomerProfileConfig = (id: number, d: Partial<CustomerProfileConfig>) => crudUpdate<CustomerProfileConfig>(CPC_PATH, id, d);
export const patchCustomerProfileConfig = (id: number, d: Partial<CustomerProfileConfig>) => crudPatch<CustomerProfileConfig>(CPC_PATH, id, d);
export const deleteCustomerProfileConfig = (id: number) => crudDelete(CPC_PATH, id);
