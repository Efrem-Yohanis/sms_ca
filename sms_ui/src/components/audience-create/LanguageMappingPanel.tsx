import { useMemo, useState } from "react";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Database, Loader2, Play, Check } from "lucide-react";
import type { AudienceRecord, ReferenceMappingConfig } from "@/types/audience";
import { EMPTY_REFERENCE_CONFIG } from "@/types/audience";
import { SUPPORTED_LANGUAGES } from "@/types/campaign";
import { useConnections, useTables, useColumns } from "./useDbSchema";

interface Props {
  /** Records with (possibly) missing language, used for preview & apply */
  records: AudienceRecord[];
  /** Called with enriched records when the user applies the mapping */
  onApply: (records: AudienceRecord[]) => void;
  /** Columns available in the source (file/db) — used for the source join column */
  sourceColumns?: string[];
  defaultSourceColumn?: string;
}

/** Deterministic simulated lookup so previews are stable between runs. */
function simulateLookup(msisdn: string): string | null {
  let hash = 0;
  for (let i = 0; i < msisdn.length; i++) hash = (hash * 31 + msisdn.charCodeAt(i)) % 100000;
  if (hash % 100 < 15) return null; // ~15% unmatched
  return SUPPORTED_LANGUAGES[hash % SUPPORTED_LANGUAGES.length];
}

export default function LanguageMappingPanel({
  records,
  onApply,
  sourceColumns,
  defaultSourceColumn = "MSISDN",
}: Props) {
  const [cfg, setCfg] = useState<ReferenceMappingConfig>({
    ...EMPTY_REFERENCE_CONFIG,
    sourceJoinColumn: defaultSourceColumn,
  });
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<AudienceRecord[] | null>(null);

  const { connections, loading: loadingConns } = useConnections();
  const { tables, loading: loadingTables } = useTables(cfg.connectionId);
  const { columns, loading: loadingCols } = useColumns(cfg.connectionId, cfg.table);

  const set = (patch: Partial<ReferenceMappingConfig>) => setCfg((c) => ({ ...c, ...patch }));

  const configComplete =
    !!cfg.connectionId && !!cfg.table && !!cfg.referenceJoinColumn && !!cfg.languageColumn && !!cfg.sourceJoinColumn;

  const summary = useMemo(() => {
    if (!preview) return null;
    const matched = preview.filter((r) => r.mapping_status === "Matched").length;
    return { total: preview.length, matched, unmatched: preview.length - matched };
  }, [preview]);

  function runPreview() {
    if (!configComplete) return;
    setPreviewing(true);
    setTimeout(() => {
      const mapped: AudienceRecord[] = records.map((r) => {
        if (r.lang) return { ...r, lang_source: "input", mapping_status: "Matched" };
        const found = simulateLookup(r.msisdn);
        return {
          ...r,
          lang: found,
          lang_source: found ? "reference" : null,
          mapping_status: found ? "Matched" : "No Match",
        };
      });
      setPreview(mapped);
      setPreviewing(false);
    }, 500);
  }

  return (
    <Card className="p-4 space-y-4 bg-muted/20">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-primary" />
          <div>
            <Label className="text-sm font-medium">Use Reference Table for Language</Label>
            <p className="text-xs text-muted-foreground mt-0.5">
              Optional — enrich records with a language from another table
            </p>
          </div>
        </div>
        <Switch checked={cfg.enabled} onCheckedChange={(v) => set({ enabled: v })} />
      </div>

      {cfg.enabled && (
        <div className="space-y-4 pt-2 border-t">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Reference Database Connection</Label>
              <Select
                value={cfg.connectionId}
                onValueChange={(v) => set({ connectionId: v, table: "", referenceJoinColumn: "", languageColumn: "" })}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingConns ? "Loading..." : "Select connection"} />
                </SelectTrigger>
                <SelectContent>
                  {connections.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} <span className="text-muted-foreground">({c.type})</span>
                    </SelectItem>
                  ))}
                  {!loadingConns && connections.length === 0 && (
                    <div className="px-2 py-2 text-xs text-muted-foreground">
                      No data sources configured
                    </div>
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Reference Table</Label>
              <Select
                value={cfg.table}
                onValueChange={(v) => set({ table: v, referenceJoinColumn: "", languageColumn: "" })}
                disabled={!cfg.connectionId}
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
              <Label className="text-xs">Source Join Column</Label>
              {sourceColumns && sourceColumns.length > 0 ? (
                <Select value={cfg.sourceJoinColumn} onValueChange={(v) => set({ sourceJoinColumn: v })}>
                  <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
                  <SelectContent>
                    {sourceColumns.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <div className="h-10 flex items-center px-3 rounded-md border bg-background text-sm font-mono">
                  {cfg.sourceJoinColumn}
                </div>
              )}
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Reference Join Column</Label>
              <Select
                value={cfg.referenceJoinColumn}
                onValueChange={(v) => set({ referenceJoinColumn: v })}
                disabled={!cfg.table}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingCols ? "Loading..." : "Select column"} />
                </SelectTrigger>
                <SelectContent>
                  {columns.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Language Column</Label>
              <Select
                value={cfg.languageColumn}
                onValueChange={(v) => set({ languageColumn: v })}
                disabled={!cfg.table}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingCols ? "Loading..." : "Select column"} />
                </SelectTrigger>
                <SelectContent>
                  {columns.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Join Type</Label>
              <Select value={cfg.joinType} onValueChange={(v) => set({ joinType: v as ReferenceMappingConfig["joinType"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="LEFT JOIN">LEFT JOIN (keeps unmatched)</SelectItem>
                  <SelectItem value="INNER JOIN">INNER JOIN</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {configComplete && (
            <div className="rounded-md border bg-background p-3 font-mono text-[11px] text-muted-foreground overflow-x-auto">
              audience.{cfg.sourceJoinColumn} &nbsp;{cfg.joinType}&nbsp; {cfg.table}.{cfg.referenceJoinColumn} → {cfg.table}.{cfg.languageColumn}
            </div>
          )}

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={runPreview}
              disabled={!configComplete || previewing || records.length === 0}
              className="gap-1.5"
            >
              {previewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              Preview Mapping
            </Button>
            {records.length === 0 && (
              <span className="text-xs text-muted-foreground">Add MSISDNs first</span>
            )}
          </div>

          {preview && summary && (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <div className="rounded-md border bg-background p-2.5">
                  <p className="text-[11px] text-muted-foreground">Total MSISDNs</p>
                  <p className="text-lg font-semibold">{summary.total.toLocaleString()}</p>
                </div>
                <div className="rounded-md border bg-background p-2.5">
                  <p className="text-[11px] text-muted-foreground">Language Matched</p>
                  <p className="text-lg font-semibold text-emerald-600">{summary.matched.toLocaleString()}</p>
                </div>
                <div className="rounded-md border bg-background p-2.5">
                  <p className="text-[11px] text-muted-foreground">Language Not Found</p>
                  <p className="text-lg font-semibold text-amber-600">{summary.unmatched.toLocaleString()}</p>
                </div>
              </div>

              <div className="border rounded-md overflow-hidden bg-background">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/40 border-b">
                      <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">MSISDN</th>
                      <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Language</th>
                      <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Mapping Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.slice(0, 8).map((r, i) => (
                      <tr key={i} className="border-b last:border-b-0">
                        <td className="px-3 py-2 font-mono text-xs">{r.msisdn}</td>
                        <td className="px-3 py-2 uppercase text-xs">
                          {r.lang || <span className="text-muted-foreground normal-case">NULL</span>}
                        </td>
                        <td className="px-3 py-2">
                          <Badge
                            variant="secondary"
                            className={
                              r.mapping_status === "Matched"
                                ? "bg-emerald-100 text-emerald-700 text-[11px]"
                                : "bg-amber-100 text-amber-700 text-[11px]"
                            }
                          >
                            {r.mapping_status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.length > 8 && (
                <p className="text-xs text-muted-foreground text-center">
                  ...and {preview.length - 8} more records
                </p>
              )}

              <Button type="button" size="sm" className="gap-1.5" onClick={() => onApply(preview)}>
                <Check className="h-3.5 w-3.5" /> Apply Mapping
              </Button>
              <p className="text-[11px] text-muted-foreground">
                Records without a language match are kept — language is optional.
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
