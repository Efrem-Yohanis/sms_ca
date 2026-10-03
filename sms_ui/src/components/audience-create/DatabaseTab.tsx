import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2, Table2 } from "lucide-react";
import type { AudienceDatabaseSelection } from "@/types/campaign";
import type { AudienceRecord } from "@/types/audience";
import LanguageMappingPanel from "./LanguageMappingPanel";
import { useConnections, useTables, useColumns } from "./useDbSchema";
import { previewTableRows } from "@/lib/api/schema";

interface Props {
  records: AudienceRecord[];
  onChange: (r: AudienceRecord[]) => void;
  initialConfig?: AudienceDatabaseSelection | null;
  onConfigChange?: (config: AudienceDatabaseSelection | null) => void;
}

const NONE = "__none__";

export default function DatabaseTab({ records, onChange, initialConfig, onConfigChange }: Props) {
  const [connection, setConnection] = useState(initialConfig?.source_database_id ? String(initialConfig.source_database_id) : "");
  const [table, setTable] = useState(initialConfig?.source_table ?? "");
  const [msisdnCol, setMsisdnCol] = useState(initialConfig?.source_msisdn_column ?? "");
  const [langCol, setLangCol] = useState(initialConfig?.source_language_column || NONE);
  const [whereClause, setWhereClause] = useState(initialConfig?.source_filter_clause ?? "");
  const [loading, setLoading] = useState(false);

  const { connections, loading: loadingConns } = useConnections();
  const { tables, loading: loadingTables } = useTables(connection);
  const { columns, loading: loadingCols } = useColumns(connection, table);

  useEffect(() => {
    if (!connection || !table || !msisdnCol) {
      onConfigChange?.(null);
      return;
    }
    onConfigChange?.({
      source_database_id: Number(connection),
      source_table: table,
      source_msisdn_column: msisdnCol,
      source_language_column: langCol === NONE ? "" : langCol,
      source_filter_clause: whereClause,
    });
  }, [connection, table, msisdnCol, langCol, whereClause, onConfigChange]);

  async function handleFetch() {
    if (!connection || !table || !msisdnCol) return;
    setLoading(true);
    try {
      const preview = await previewTableRows(connection, table, 100);
      const msisdnIndex = preview.columns.indexOf(msisdnCol);
      const languageIndex = langCol === NONE ? -1 : preview.columns.indexOf(langCol);
      if (msisdnIndex < 0) throw new Error(`Column '${msisdnCol}' was not returned by the selected table`);
      const fetched: AudienceRecord[] = preview.rows
        .map((row) => ({
          msisdn: String(row[msisdnIndex] ?? "").trim(),
          lang: languageIndex < 0 ? null : String(row[languageIndex] ?? "").trim().toLowerCase() || null,
          source: "database" as const,
          lang_source: languageIndex < 0 ? null : ("input" as const),
          mapping_status: languageIndex < 0 ? ("Not applicable" as const) : ("Matched" as const),
        }))
        .filter((row) => row.msisdn.length > 0);
      if (fetched.length === 0) throw new Error("The selected table preview contains no recipient rows");
      onChange(fetched);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to preview database recipients");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <Label className="text-base font-medium">Select MSISDNs from a Database</Label>
        <p className="text-xs text-muted-foreground mt-0.5">
          Pick a connection, then a table, then the MSISDN column. Language is optional.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label className="text-xs">1. Database Connection *</Label>
          <Select
            value={connection}
            onValueChange={(v) => { setConnection(v); setTable(""); setMsisdnCol(""); setLangCol(NONE); }}
          >
            <SelectTrigger>
              <SelectValue placeholder={loadingConns ? "Loading..." : "Select connection"} />
            </SelectTrigger>
            <SelectContent>
              {connections.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name} ({c.type})</SelectItem>
              ))}
              {!loadingConns && connections.length === 0 && (
                <div className="px-2 py-2 text-xs text-muted-foreground">
                  No data sources configured — add one in Configurations
                </div>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">2. Source Table *</Label>
          <Select
            value={table}
            onValueChange={(v) => { setTable(v); setMsisdnCol(""); setLangCol(NONE); }}
            disabled={!connection}
          >
            <SelectTrigger>
              <SelectValue placeholder={loadingTables ? "Loading..." : "Select table"} />
            </SelectTrigger>
            <SelectContent>
              {tables.map((t) => (
                <SelectItem key={t.name} value={t.name}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">3. MSISDN Column *</Label>
          <Select value={msisdnCol} onValueChange={setMsisdnCol} disabled={!table}>
            <SelectTrigger>
              <SelectValue placeholder={loadingCols ? "Loading..." : "Select column"} />
            </SelectTrigger>
            <SelectContent>
              {columns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">4. Language Column (optional)</Label>
          <Select value={langCol} onValueChange={setLangCol} disabled={!table}>
            <SelectTrigger>
              <SelectValue placeholder="Select column" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>None — map from reference table</SelectItem>
              {columns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Filter Condition (optional WHERE clause)</Label>
        <Textarea
          value={whereClause}
          onChange={(e) => setWhereClause(e.target.value)}
          placeholder="status = 'active' AND region = 'Addis'"
          rows={2}
          className="font-mono text-xs"
        />
      </div>

      <Button
        type="button"
        onClick={handleFetch}
        disabled={!connection || !table || !msisdnCol || loading}
        className="gap-1.5"
      >
        {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Table2 className="h-3.5 w-3.5" />}
        Fetch MSISDNs
      </Button>

      {records.length > 0 && (
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">
            Preview ({records.length} records)
          </Label>
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/40 border-b">
                  <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">MSISDN</th>
                  <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Language</th>
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 5).map((r, i) => (
                  <tr key={i} className="border-b last:border-b-0">
                    <td className="px-3 py-2 font-mono text-xs">{r.msisdn}</td>
                    <td className="px-3 py-2">
                      {r.lang ? (
                        <Badge variant="secondary" className="text-[11px] uppercase">{r.lang}</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">NULL</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <LanguageMappingPanel
        records={records}
        sourceColumns={columns}
        defaultSourceColumn={msisdnCol || "MSISDN"}
        onApply={(mapped) => onChange(mapped)}
      />
    </div>
  );
}
