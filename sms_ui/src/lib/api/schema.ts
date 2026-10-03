import { API_V1_BASE, authFetch, authHeaders, handleResponse } from "./base";
import { fetchDataSources, type DataSource } from "./configurations";

export interface DbConnection {
  id: string;
  name: string;
  type: string;
}

export interface DbTable {
  name: string;
  rowCount?: number;
}

export interface DbColumn {
  name: string;
  type: string;
  nullable: boolean;
}

export interface DbTablePreview {
  columns: string[];
  rows: unknown[][];
  row_count: number;
}

/** Database connections come from the Configurations → Data Sources module. */
export async function listConnections(): Promise<DbConnection[]> {
  try {
    const res = await fetchDataSources();
    return (res.results || []).map((d: DataSource) => ({
      id: String(d.id),
      name: d.name,
      type: d.database_type,
    }));
  } catch {
    return [];
  }
}

export async function listTables(connectionId: string): Promise<DbTable[]> {
  if (!connectionId) return [];
  const res = await authFetch(
    `${API_V1_BASE}/databases/${connectionId}/tables/`,
    { headers: authHeaders() },
  );
  const data = await handleResponse<{ tables?: string[] } | string[]>(res);
  const tables = Array.isArray(data) ? data : data.tables ?? [];
  return tables.map((table) => typeof table === "string" ? { name: table } : table);
}

export async function getTableColumns(connectionId: string, table: string): Promise<DbColumn[]> {
  if (!connectionId || !table) return [];
  const res = await authFetch(
    `${API_V1_BASE}/databases/${connectionId}/tables/${encodeURIComponent(table)}/schema/`,
    { headers: authHeaders() },
  );
  const data = await handleResponse<{ columns?: DbColumn[] } | DbColumn[]>(res);
  return Array.isArray(data) ? data : data.columns ?? [];
}

export async function listColumns(connectionId: string, table: string): Promise<string[]> {
  return (await getTableColumns(connectionId, table)).map((column) => column.name);
}

export async function previewTableRows(connectionId: string, table: string, limit = 10): Promise<DbTablePreview> {
  const res = await authFetch(
    `${API_V1_BASE}/databases/${connectionId}/tables/${encodeURIComponent(table)}/preview/?limit=${limit}`,
    { headers: authHeaders() },
  );
  return handleResponse<DbTablePreview & { success: boolean }>(res);
}
