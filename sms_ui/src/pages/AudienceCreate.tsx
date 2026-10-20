import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { ArrowLeft, Users, Keyboard, Upload, Database, Code2 } from "lucide-react";
import { toast } from "sonner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AudienceBuildProgress } from "@/lib/api/audiences";
import { fetchCampaigns, saveCampaignAudience, type ApiCampaign } from "@/lib/api";
import type { AudienceRecord, AudienceSourceType } from "@/types/audience";
import type { AudienceDatabaseSelection } from "@/types/campaign";
import type { Language } from "@/types/campaign";
import ManualInsertTab from "@/components/audience-create/ManualInsertTab";
import CsvUploadTab from "@/components/audience-create/CsvUploadTab";
import DatabaseTab from "@/components/audience-create/DatabaseTab";
import SqlQueryTab from "@/components/audience-create/SqlQueryTab";
import { isValidMsisdn } from "@/types/audience";

const SOURCES: { value: AudienceSourceType; label: string; desc: string; icon: typeof Keyboard }[] = [
  { value: "manual", label: "Manual Entry", desc: "Type MSISDNs one by one", icon: Keyboard },
  { value: "file", label: "Import from File", desc: "Upload CSV or Excel", icon: Upload },
  { value: "database", label: "Database Source", desc: "Query an existing table", icon: Database },
  { value: "sql", label: "SQL Query", desc: "Write a SELECT query", icon: Code2 },
];

export default function AudienceCreate() {
  const navigate = useNavigate();
  const [campaignId, setCampaignId] = useState("");
  const [source, setSource] = useState<AudienceSourceType>("manual");
  const [defaultLanguage, setDefaultLanguage] = useState<Language>("en");
  const [records, setRecords] = useState<AudienceRecord[]>([]);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [databaseConfig, setDatabaseConfig] = useState<AudienceDatabaseSelection | null>(null);
  const [sqlConfig, setSqlConfig] = useState<{ source_database_id: number; source_sql: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [buildProgress, setBuildProgress] = useState<AudienceBuildProgress | null>(null);
  const [campaigns, setCampaigns] = useState<ApiCampaign[]>([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [campaignLoadError, setCampaignLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadCampaigns() {
      setLoadingCampaigns(true);
      setCampaignLoadError("");
      try {
        const loadByStatus = async (status: string) => {
          const results: ApiCampaign[] = [];
          let page = 1;
          let hasNextPage = true;

          while (hasNextPage) {
            const response = await fetchCampaigns({ status, page, pageSize: 200 });
            results.push(...response.results);
            hasNextPage = Boolean(response.next);
            page += 1;
          }

          return results;
        };

        const draftCampaigns = await loadByStatus("draft");
        if (!cancelled) {
          setCampaigns(draftCampaigns.sort((a, b) => a.name.localeCompare(b.name)));
        }
      } catch (error) {
        if (!cancelled) {
          setCampaignLoadError(error instanceof Error ? error.message : "Failed to load draft campaigns");
        }
      } finally {
        if (!cancelled) setLoadingCampaigns(false);
      }
    }

    void loadCampaigns();
    return () => { cancelled = true; };
  }, []);

  const campaignIdNum = parseInt(campaignId, 10);
  const validRecords = records.filter((r) => isValidMsisdn(r.msisdn));
  const isValid = !isNaN(campaignIdNum) && campaignIdNum > 0 && (
    source === "database" ? databaseConfig !== null : source === "sql" ? sqlConfig !== null : validRecords.length > 0 && (source !== "file" || sourceFile !== null)
  );
  const withLang = validRecords.filter((r) => !!r.lang).length;

  function switchSource(v: AudienceSourceType) {
    setSource(v);
    setRecords([]);
    setDatabaseConfig(null);
    setSqlConfig(null);
    setSourceFile(null);
  }

  async function handleSubmit() {
    if (!isValid) return;
    setSubmitting(true);
    setBuildProgress(null);
    try {
      const result = await saveCampaignAudience(campaignIdNum, {
        recipients: validRecords.map((r) => ({ msisdn: r.msisdn, lang: r.lang || "" })),
        default_language: defaultLanguage,
        source_type: source,
        database_config: databaseConfig,
        source_file: sourceFile,
        sql_config: sqlConfig,
      }, (progress) => setBuildProgress(progress));
      toast.success(`Audience built: ${result.valid_count} valid, ${result.invalid_count} invalid`);
      navigate(`/campaigns/${campaignIdNum}`);
    } catch (e: any) {
      toast.error(e?.message || "Failed to create audience");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate("/audiences")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audience Management</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Define your audience manually, from a file, or from a database — language is optional
          </p>
        </div>
      </div>

      {/* Campaign selection */}
      <Card className="p-5 shadow-card">
        <div className="space-y-1.5">
          <Label htmlFor="campaign-id" className="flex items-center gap-1.5">
            Draft campaign <span className="text-destructive">*</span>
          </Label>
          <Select value={campaignId} onValueChange={setCampaignId} disabled={loadingCampaigns || campaigns.length === 0}>
            <SelectTrigger id="campaign-id" className="max-w-lg">
              <SelectValue placeholder={loadingCampaigns ? "Loading campaigns..." : "Select a campaign"} />
            </SelectTrigger>
            <SelectContent>
              {campaigns.map((campaign) => (
                <SelectItem key={campaign.id} value={String(campaign.id)}>
                  {campaign.name} (ID: {campaign.id}) · {campaign.status.replace(/_/g, " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {campaignLoadError && <p role="alert" className="text-xs text-destructive">{campaignLoadError}</p>}
          {!loadingCampaigns && !campaignLoadError && campaigns.length === 0 && (
            <p className="text-xs text-muted-foreground">No draft campaigns are available.</p>
          )}
        </div>
      </Card>

      {/* Audience source */}
      <Card className="p-5 shadow-card space-y-3">
        <Label className="text-base font-medium">Audience Source</Label>
        <RadioGroup
          value={source}
          onValueChange={(v) => switchSource(v as AudienceSourceType)}
          className="grid gap-3 sm:grid-cols-4"
        >
          {SOURCES.map((s) => (
            <label
              key={s.value}
              htmlFor={`src-${s.value}`}
              className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                source === s.value ? "border-primary bg-primary/5" : "hover:bg-muted/40"
              }`}
            >
              <RadioGroupItem value={s.value} id={`src-${s.value}`} className="mt-0.5" />
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  <s.icon className="h-3.5 w-3.5" /> {s.label}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">{s.desc}</p>
              </div>
            </label>
          ))}
        </RadioGroup>
      </Card>

      {/* Source panel */}
      <Card className="p-5 shadow-card">
        {source === "manual" && <ManualInsertTab records={records} onChange={setRecords} />}
        {source === "file" && (
          <CsvUploadTab
            records={records}
            onChange={setRecords}
            onSourceFileChange={setSourceFile}
          />
        )}
        {source === "database" && (
          <DatabaseTab
            records={records}
            onChange={setRecords}
            initialConfig={databaseConfig}
            onConfigChange={setDatabaseConfig}
          />
        )}
        {source === "sql" && <SqlQueryTab onConfigChange={setSqlConfig} defaultLanguage={defaultLanguage} onDefaultLanguageChange={setDefaultLanguage} />}
      </Card>

      {/* Summary & Submit */}
      <Card className="p-5 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <Users className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="font-medium">
                {source === "database"
                  ? databaseConfig ? "Database audience ready to build" : "Select a database, table, and MSISDN column"
                  : source === "sql" ? sqlConfig ? "SQL audience ready to build" : "Choose a database and enter a query"
                  : isValid ? `${validRecords.length.toLocaleString()} MSISDNs ready` : "Add valid recipients to continue"}
              </p>
              <p className="text-xs text-muted-foreground">
                {source === "database"
                  ? databaseConfig
                    ? records.length > 0
                      ? `${records.length.toLocaleString()} preview rows · Build reads the complete selected source table`
                      : "Build reads the complete selected source table and saves recipients to this campaign"
                    : "Choose the source details above to enable the build"
                  : source === "sql" ? "Query results are read during the build; language can be returned as `language` or defaulted."
                  : `${withLang.toLocaleString()} with language · ${(validRecords.length - withLang).toLocaleString()} without (kept) · Source: ${source}`}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            {source !== "database" && source !== "sql" && (
              <Button variant="outline" onClick={() => setRecords([])} disabled={records.length === 0}>Clear All</Button>
            )}
            <Button onClick={handleSubmit} disabled={!isValid || submitting}>
              {submitting ? "Building audience..." : source === "database" || source === "sql" ? "Save & Build Audience" : "Save Audience"}
            </Button>
          </div>
        </div>
      </Card>
      {submitting && (
        <div className="space-y-2" role="status" aria-live="polite">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Building audience</span>
            <span className="text-muted-foreground">
              {buildProgress?.total ? `${Math.round(buildProgress.percent)}%` : buildProgress?.phase || "Starting"}
            </span>
          </div>
          <div
            className="h-2 overflow-hidden rounded-full bg-secondary"
            role="progressbar"
            aria-label="Audience build progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={buildProgress?.total ? Math.round(buildProgress.percent) : undefined}
          >
            <div
              className={`h-full bg-primary transition-all ${buildProgress?.total ? "" : "w-1/3 animate-progress-indeterminate"}`}
              style={buildProgress?.total ? { width: `${Math.min(buildProgress.percent, 100)}%` } : undefined}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {buildProgress
              ? `${buildProgress.phase}: ${buildProgress.processed.toLocaleString()}${buildProgress.total ? ` / ${buildProgress.total.toLocaleString()}` : " rows processed"}`
              : "Uploading source and starting build..."}
          </p>
        </div>
      )}
    </div>
  );
}
