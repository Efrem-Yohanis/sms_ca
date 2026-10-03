import { useEffect, useState } from "react";
import { listConnections, listTables, listColumns, type DbConnection, type DbTable } from "@/lib/api/schema";

export function useConnections() {
  const [connections, setConnections] = useState<DbConnection[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    listConnections()
      .then((c) => alive && setConnections(c))
      .catch(() => alive && setConnections([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);
  return { connections, loading };
}

export function useTables(connectionId: string) {
  const [tables, setTables] = useState<DbTable[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!connectionId) {
      setTables([]);
      return;
    }
    let alive = true;
    setLoading(true);
    listTables(connectionId)
      .then((t) => alive && setTables(t))
      .catch(() => alive && setTables([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [connectionId]);
  return { tables, loading };
}

export function useColumns(connectionId: string, table: string) {
  const [columns, setColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!connectionId || !table) {
      setColumns([]);
      return;
    }
    let alive = true;
    setLoading(true);
    listColumns(connectionId, table)
      .then((c) => alive && setColumns(c))
      .catch(() => alive && setColumns([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [connectionId, table]);
  return { columns, loading };
}
