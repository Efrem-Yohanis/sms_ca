import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Upload, FileSpreadsheet, AlertCircle, CheckCircle2 } from "lucide-react";
import * as XLSX from "xlsx";
import type { AudienceRecord } from "@/types/audience";
import { isValidMsisdn, normalizeMsisdn } from "@/types/audience";
import LanguageMappingPanel from "./LanguageMappingPanel";

interface Props {
  records: AudienceRecord[];
  onChange: (r: AudienceRecord[]) => void;
  onSourceFileChange: (file: File | null) => void;
}

const NONE = "__none__";

export default function CsvUploadTab({ records, onChange, onSourceFileChange }: Props) {
  const [fileName, setFileName] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, string>[]>([]);
  const [msisdnCol, setMsisdnCol] = useState("");
  const [langCol, setLangCol] = useState(NONE);
  const [errors, setErrors] = useState<string[]>([]);
  const [stats, setStats] = useState<{ total: number; valid: number; invalid: number } | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    setErrors([]);
    setStats(null);
    setHeaders([]);
    setRows([]);
    setMsisdnCol("");
    setLangCol(NONE);
    setSourceFile(null);
    onSourceFileChange(null);
    onChange([]);

    const file = e.target.files?.[0];
    if (!file) return;
    setSourceFile(file);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["csv", "xlsx", "xls"].includes(ext || "")) {
      setErrors(["Unsupported file type. Use .csv, .xlsx, or .xls"]);
      return;
    }
    setFileName(file.name);

    try {
      const buffer = await file.arrayBuffer();
      const wb = XLSX.read(buffer, { type: "array" });
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const json: Record<string, any>[] = XLSX.utils.sheet_to_json(sheet, { defval: "" });
      if (!json.length) {
        setErrors(["The file contains no data rows"]);
        return;
      }
      const cols = Object.keys(json[0]);
      setHeaders(cols);
      setRows(json.map((r) => {
        const o: Record<string, string> = {};
        cols.forEach((c) => (o[c] = r[c]?.toString().trim() ?? ""));
        return o;
      }));

      // Auto-detect
      const guessMsisdn = cols.find((c) => /msisdn|phone|mobile|number|tel/i.test(c));
      if (guessMsisdn) setMsisdnCol(guessMsisdn);
      const guessLang = cols.find((c) => /lang/i.test(c));
      if (guessLang) setLangCol(guessLang);
      if (guessMsisdn) build(json, guessMsisdn, guessLang || NONE, file);
    } catch {
      setErrors(["Failed to read file. Please check the format."]);
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  function build(source: Record<string, any>[], mCol: string, lCol: string, originalFile = sourceFile) {
    const parsed: AudienceRecord[] = [];
    const errs: string[] = [];
    source.forEach((row, i) => {
      const raw = row[mCol]?.toString().trim() ?? "";
      if (!raw) return;
      if (!isValidMsisdn(raw)) {
        errs.push(`Row ${i + 2}: invalid MSISDN "${raw}"`);
        return;
      }
      const lang = lCol && lCol !== NONE ? (row[lCol]?.toString().trim().toLowerCase() || null) : null;
      parsed.push({
        msisdn: normalizeMsisdn(raw)!,
        lang: lang || null,
        source: "file",
        lang_source: lang ? "input" : null,
        mapping_status: lang ? "Matched" : "Not applicable",
      });
    });
    setStats({ total: source.length, valid: parsed.length, invalid: errs.length });
    setErrors(errs.slice(0, 10));
    onChange(parsed);

    if (originalFile && mCol) {
      const csvRows = [
        ["msisdn", "language"],
        ...source.map((row) => [
          row[mCol]?.toString().trim() ?? "",
          lCol && lCol !== NONE ? row[lCol]?.toString().trim() ?? "" : "",
        ]),
      ];
      const csv = XLSX.utils.sheet_to_csv(XLSX.utils.aoa_to_sheet(csvRows));
      onSourceFileChange(new File(
        [csv],
        `${originalFile.name.replace(/\.[^.]+$/, "")}.csv`,
        { type: "text/csv" },
      ));
    } else {
      onSourceFileChange(null);
    }
  }

  function onMsisdnColChange(v: string) {
    setMsisdnCol(v);
    build(rows, v, langCol);
  }

  function onLangColChange(v: string) {
    setLangCol(v);
    if (msisdnCol) build(rows, msisdnCol, v);
  }

  return (
    <div className="space-y-5">
      <div>
        <Label className="text-base font-medium">Import MSISDNs from a File</Label>
        <p className="text-xs text-muted-foreground mt-0.5">
          Upload a .csv/.xlsx file containing at least an MSISDN column. Language column is optional.
        </p>
      </div>

      <div
        className="border-2 border-dashed rounded-lg p-8 text-center hover:border-primary/50 transition-colors cursor-pointer"
        onClick={() => fileRef.current?.click()}
      >
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleFile} className="hidden" />
        <Upload className="h-8 w-8 mx-auto text-muted-foreground mb-3" />
        <p className="text-sm font-medium">Click to upload or drag & drop</p>
        <p className="text-xs text-muted-foreground mt-1">.csv, .xlsx, .xls supported</p>
        {fileName && (
          <div className="flex items-center justify-center gap-1.5 mt-3 text-sm text-muted-foreground">
            <FileSpreadsheet className="h-4 w-4" /> {fileName}
          </div>
        )}
      </div>

      {headers.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">MSISDN Column *</Label>
            <Select value={msisdnCol} onValueChange={onMsisdnColChange}>
              <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
              <SelectContent>
                {headers.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Language Column (optional)</Label>
            <Select value={langCol} onValueChange={onLangColChange}>
              <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>None — map from reference table</SelectItem>
                {headers.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {stats && (
        <div className="flex gap-4 p-3 rounded-md bg-muted/50">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Rows:</span>
            <span className="text-sm font-medium">{stats.total}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            <span className="text-sm font-medium text-emerald-600">{stats.valid} valid</span>
          </div>
          {stats.invalid > 0 && (
            <div className="flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5 text-destructive" />
              <span className="text-sm font-medium text-destructive">{stats.invalid} invalid</span>
            </div>
          )}
        </div>
      )}

      {records.length > 0 && (
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground uppercase tracking-wider">Preview (first 5 rows)</Label>
          <div className="border rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/40 border-b">
                  <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">#</th>
                  <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">MSISDN</th>
                  <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">Language</th>
                </tr>
              </thead>
              <tbody>
                {records.slice(0, 5).map((r, i) => (
                  <tr key={i} className="border-b last:border-b-0">
                    <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
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

      {errors.length > 0 && (
        <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20">
          <p className="text-sm font-medium text-destructive mb-1">Validation Errors</p>
          <ul className="text-xs text-destructive space-y-0.5">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      <LanguageMappingPanel
        records={records}
        sourceColumns={headers}
        defaultSourceColumn={msisdnCol || "MSISDN"}
        onApply={(mapped) => onChange(mapped)}
      />
    </div>
  );
}
