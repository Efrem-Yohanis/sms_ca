export { default } from "./StepAudienceExact";
// @ts-nocheck
import { useState, useRef } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WizardData, Recipient, Language, AudienceSource } from "@/types/campaign";
import { SUPPORTED_LANGUAGES, LANGUAGE_LABELS } from "@/types/campaign";
import { Plus, Trash2, Upload, FileSpreadsheet, Database, UserPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import * as XLSX from "xlsx";

interface Props {
  data: WizardData;
  errors: Record<string, string>;
  update: (partial: Partial<WizardData>) => void;
}

// Mock DB tables for demonstration
const MOCK_DB_TABLES = [
  { name: "subscribers", count: 12450, description: "All active subscribers" },
  { name: "vip_customers", count: 842, description: "VIP tier customers" },
  { name: "new_signups_2024", count: 3210, description: "New signups this year" },
  { name: "inactive_users", count: 5600, description: "Users inactive 30+ days" },
];

function LegacyStepAudience({ data, errors, update }: Props) {
  const [bulkInput, setBulkInput] = useState("");
  const [bulkError, setBulkError] = useState("");
  const [fileError, setFileError] = useState("");
  const [fileName, setFileName] = useState("");
  const [selectedTable, setSelectedTable] = useState("");
  const [dbLoading, setDbLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [records, setRecords] = useState<AudienceRecord[]>(() => toAudienceRecords(data));
  const source = data.audience_source === "manual" ? "manual" : data.audience_source as AudienceSourceType;

  function updateRecords(next: AudienceRecord[]) {
    setRecords(next);
    update({
      recipients: next.map((record) => ({
        msisdn: record.msisdn,
        lang: (record.lang || "en") as WizardData["default_language"],
      })),
    });
  }

  function switchSource(next: AudienceSourceType) {
    setRecords([]);
    update({ audience_source: next === "file" ? "file" : next, recipients: [], db_query: "" });
  }

  const SOURCES: { value: AudienceSourceType; label: string; desc: string; icon: typeof Keyboard }[] = [
    { value: "manual", label: "Manual Entry", desc: "Type MSISDNs one by one", icon: Keyboard },
    { value: "file", label: "Import from File", desc: "Upload CSV or Excel", icon: Upload },
    { value: "database", label: "Database Source", desc: "Query an existing table", icon: Database },
  ];

  function toAudienceRecords(data: WizardData): AudienceRecord[] {
    return data.recipients.map((recipient) => ({
      msisdn: recipient.msisdn,
      lang: recipient.lang || null,
      source: data.audience_source === "manual" ? "manual" : data.audience_source,
    }));
  }

  return (
    <div className="space-y-5">
      <Card className="p-5 shadow-card space-y-3">
        <Label className="text-base font-medium">Audience Source</Label>
        <RadioGroup
          value={source}
          onValueChange={(value) => switchSource(value as AudienceSourceType)}
          className="grid gap-3 sm:grid-cols-3"
        >
          {SOURCES.map((item) => (
            <label
              key={item.value}
              htmlFor={`wizard-src-${item.value}`}
              className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                source === item.value ? "border-primary bg-primary/5" : "hover:bg-muted/40"
              }`}
            >
              <RadioGroupItem value={item.value} id={`wizard-src-${item.value}`} className="mt-0.5" />
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <item.icon className="h-3.5 w-3.5" /> {item.label}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
              </div>
            </label>
          ))}
        </RadioGroup>
      </Card>

      <Card className="p-5 shadow-card">
        {source === "manual" && <ManualInsertTab records={records} onChange={updateRecords} />}
        {source === "file" && <CsvUploadTab records={records} onChange={updateRecords} />}
        {source === "database" && <DatabaseTab records={records} onChange={updateRecords} />}
      </Card>

      {errors.recipients && <p className="text-sm text-destructive">{errors.recipients}</p>}
    </div>
  );

  const phonePattern = /^\+?[1-9]\d{1,14}$/;

  function setSource(source: AudienceSource) {
    update({ audience_source: source });
  }

  function addRecipient() {
    update({
      recipients: [...data.recipients, { msisdn: "", lang: "en" }],
    });
  }

  function removeRecipient(index: number) {
    update({
      recipients: data.recipients.filter((_, i) => i !== index),
    });
  }

  function updateRecipient(index: number, field: keyof Recipient, value: string) {
    const updated = [...data.recipients];
    updated[index] = { ...updated[index], [field]: value };
    update({ recipients: updated });
  }

  function parseRows(rows: string[][]): { parsed: Recipient[]; errors: string[] } {
    const parsed: Recipient[] = [];
    const errs: string[] = [];

    for (let i = 0; i < rows.length; i++) {
      const [msisdn, lang] = rows[i].map((s) => s?.toString().trim() ?? "");
      if (!msisdn) continue;
      if (!phonePattern.test(msisdn)) {
        errs.push(`Row ${i + 1}: invalid phone "${msisdn}"`);
        continue;
      }
      const normalizedLang = lang?.toLowerCase() || "en";
      if (!SUPPORTED_LANGUAGES.includes(normalizedLang as Language)) {
        errs.push(`Row ${i + 1}: unsupported language "${lang}"`);
        continue;
      }
      parsed.push({ msisdn, lang: normalizedLang as Language });
    }
    return { parsed, errors: errs };
  }

  function parseBulk() {
    setBulkError("");
    const lines = bulkInput.trim().split("\n").filter((l) => l.trim());
    if (!lines.length) {
      setBulkError("No data to parse");
      return;
    }

    const rows = lines.map((l) => l.split(/[,\t]/).map((s) => s.trim()));
    const { parsed, errors: errs } = parseRows(rows);

    if (errs.length > 0) {
      setBulkError(errs.slice(0, 5).join("\n") + (errs.length > 5 ? `\n...and ${errs.length - 5} more` : ""));
      return;
    }

    if (parsed.length === 0) {
      setBulkError("No valid recipients found");
      return;
    }

    update({ recipients: [...data.recipients, ...parsed] });
    setBulkInput("");
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    setFileError("");
    setFileName("");
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["csv", "xlsx", "xls"].includes(ext || "")) {
      setFileError("Unsupported file type. Use .csv, .xlsx, or .xls");
      return;
    }

    setFileName(file.name);

    try {
      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: "array" });
      const sheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData: string[][] = XLSX.utils.sheet_to_json(sheet, { header: 1 });

      let startRow = 0;
      if (jsonData.length > 0) {
        const firstCell = jsonData[0][0]?.toString().toLowerCase() ?? "";
        if (["phone", "msisdn", "number", "mobile", "tel"].some((h) => firstCell.includes(h))) {
          startRow = 1;
        }
      }

      const rows = jsonData.slice(startRow).filter((r) => r.length >= 1);
      const { parsed, errors: errs } = parseRows(rows);

      if (errs.length > 0) {
        setFileError(
          `${parsed.length} valid, ${errs.length} invalid:\n` +
          errs.slice(0, 5).join("\n") +
          (errs.length > 5 ? `\n...and ${errs.length - 5} more` : "")
        );
      }

      if (parsed.length > 0) {
        update({ recipients: [...data.recipients, ...parsed] });
      } else if (errs.length === 0) {
        setFileError("No recipients found in file");
      }
    } catch {
      setFileError("Failed to read file. Please check the format.");
    }

    if (fileRef.current) fileRef.current.value = "";
  }

  function loadFromTable(tableName: string) {
    setSelectedTable(tableName);
    setDbLoading(true);
    const table = MOCK_DB_TABLES.find((t) => t.name === tableName);

    // Simulate DB query with mock data
    setTimeout(() => {
      const mockRecipients: Recipient[] = Array.from({ length: Math.min(table?.count ?? 10, 20) }, (_, i) => ({
        msisdn: `+2519${String(10000000 + Math.floor(Math.random() * 89999999))}`,
        lang: SUPPORTED_LANGUAGES[i % SUPPORTED_LANGUAGES.length],
      }));
      update({
        recipients: mockRecipients,
        db_query: `SELECT msisdn, lang FROM ${tableName}`,
      });
      setDbLoading(false);
    }, 800);
  }

  function clearAll() {
    update({ recipients: [], db_query: "" });
    setSelectedTable("");
  }

  return (
    <div className="space-y-5">
      {/* Source toggle */}
      <div className="space-y-1.5">
        <Label>Audience source</Label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setSource("manual")}
            className={cn(
              "flex items-center gap-3 border rounded-sm p-4 transition-colors text-left",
              data.audience_source === "manual"
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border hover:border-muted-foreground"
            )}
          >
            <UserPlus className={cn("h-5 w-5", data.audience_source === "manual" ? "text-primary" : "text-muted-foreground")} />
            <div>
              <p className={cn("font-medium text-sm", data.audience_source === "manual" ? "text-primary" : "text-foreground")}>Import / Manual</p>
              <p className="text-xs text-muted-foreground">Upload CSV/Excel, paste, or add manually</p>
            </div>
          </button>
          <button
            type="button"
            onClick={() => setSource("database")}
            className={cn(
              "flex items-center gap-3 border rounded-sm p-4 transition-colors text-left",
              data.audience_source === "database"
                ? "border-primary bg-primary/5 ring-1 ring-primary"
                : "border-border hover:border-muted-foreground"
            )}
          >
            <Database className={cn("h-5 w-5", data.audience_source === "database" ? "text-primary" : "text-muted-foreground")} />
            <div>
              <p className={cn("font-medium text-sm", data.audience_source === "database" ? "text-primary" : "text-foreground")}>From Database</p>
              <p className="text-xs text-muted-foreground">Query an existing audience table</p>
            </div>
          </button>
        </div>
      </div>

      {/* Manual / Import mode */}
      {data.audience_source === "manual" && (
        <>
          <p className="text-sm text-muted-foreground">
            Add recipients by importing a file (CSV/Excel), pasting in bulk, or adding individually.
          </p>

          {/* File upload */}
          <div className="space-y-2">
            <Label>Import from file</Label>
            <div className="flex items-center gap-3">
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={handleFileUpload}
                className="hidden"
              />
              <Button type="button" variant="outline" onClick={() => fileRef.current?.click()} className="gap-2">
                <Upload className="h-4 w-4" /> Upload CSV / Excel
              </Button>
              {fileName && (
                <span className="text-sm text-muted-foreground flex items-center gap-1">
                  <FileSpreadsheet className="h-4 w-4" /> {fileName}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Columns: <code className="text-xs bg-muted px-1 rounded">phone</code>,{" "}
              <code className="text-xs bg-muted px-1 rounded">language</code> (en, am, ti, om, so)
            </p>
            {fileError && <pre className="text-sm text-destructive whitespace-pre-wrap">{fileError}</pre>}
          </div>

          {/* Bulk paste */}
          <div className="space-y-1.5 pt-2 border-t">
            <Label>Bulk paste (CSV format)</Label>
            <Textarea
              value={bulkInput}
              onChange={(e) => setBulkInput(e.target.value)}
              placeholder={"+251912345678, en\n+251911111111, am"}
              rows={4}
              className="font-mono text-sm"
            />
            {bulkError && <pre className="text-sm text-destructive whitespace-pre-wrap">{bulkError}</pre>}
            <Button type="button" variant="outline" size="sm" onClick={parseBulk} disabled={!bulkInput.trim()}>
              Parse & add
            </Button>
          </div>

          {/* Manual add */}
          <div className="pt-2 border-t">
            <Button type="button" variant="outline" size="sm" onClick={addRecipient}>
              <Plus className="h-3.5 w-3.5 mr-1" /> Add recipient manually
            </Button>
          </div>
        </>
      )}

      {/* Database mode */}
      {data.audience_source === "database" && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Select an existing audience table to query recipients from your database.
          </p>

          <div className="space-y-1.5">
            <Label>Select audience table</Label>
            <Select value={selectedTable} onValueChange={loadFromTable}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a table..." />
              </SelectTrigger>
              <SelectContent>
                {MOCK_DB_TABLES.map((t) => (
                  <SelectItem key={t.name} value={t.name}>
                    <span className="flex items-center gap-2">
                      <Database className="h-3.5 w-3.5 text-muted-foreground" />
                      {t.name}
                      <span className="text-muted-foreground text-xs">({t.count.toLocaleString()} rows)</span>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedTable && (
            <div className="border rounded-sm p-3 bg-muted/30 space-y-2">
              <p className="text-sm font-medium text-foreground">
                {MOCK_DB_TABLES.find((t) => t.name === selectedTable)?.description}
              </p>
              {data.db_query && (
                <code className="block text-xs bg-background border rounded px-2 py-1.5 font-mono text-muted-foreground">
                  {data.db_query}
                </code>
              )}
              {dbLoading && <p className="text-sm text-muted-foreground animate-pulse">Loading recipients...</p>}
            </div>
          )}
        </div>
      )}

      {/* Recipients list */}
      {data.recipients.length > 0 && (
        <div className="space-y-2 pt-2 border-t">
          <div className="flex items-center justify-between">
            <Label>Recipients ({data.recipients.length.toLocaleString()})</Label>
            <Button type="button" variant="ghost" size="sm" className="text-destructive text-xs" onClick={clearAll}>
              Clear all
            </Button>
          </div>
          <div className="max-h-60 overflow-y-auto space-y-2 border rounded-sm p-3">
            {data.recipients.slice(0, 50).map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  value={r.msisdn}
                  onChange={(e) => updateRecipient(i, "msisdn", e.target.value)}
                  placeholder="+251912345678"
                  className="flex-1"
                />
                <Select value={r.lang} onValueChange={(v) => updateRecipient(i, "lang", v)}>
                  <SelectTrigger className="w-36">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUPPORTED_LANGUAGES.map((l) => (
                      <SelectItem key={l} value={l}>{LANGUAGE_LABELS[l]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <button onClick={() => removeRecipient(i)} className="text-destructive hover:text-destructive/80">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            {data.recipients.length > 50 && (
              <p className="text-xs text-muted-foreground text-center py-2">
                Showing first 50 of {data.recipients.length.toLocaleString()} recipients
              </p>
            )}
          </div>
        </div>
      )}

      {errors.recipients && <p className="text-sm text-destructive">{errors.recipients}</p>}
    </div>
  );
}
