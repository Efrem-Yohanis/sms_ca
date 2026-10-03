import { useState } from "react";
import { Database, Keyboard, Upload } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { WizardData } from "@/types/campaign";
import type { AudienceRecord, AudienceSourceType } from "@/types/audience";
import ManualInsertTab from "@/components/audience-create/ManualInsertTab";
import CsvUploadTab from "@/components/audience-create/CsvUploadTab";
import DatabaseTab from "@/components/audience-create/DatabaseTab";

interface Props {
  data: WizardData;
  errors: Record<string, string>;
  update: (partial: Partial<WizardData>) => void;
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

export default function StepAudienceExact({ data, errors, update }: Props) {
  const [records, setRecords] = useState<AudienceRecord[]>(() => toAudienceRecords(data));
  const source = data.audience_source as AudienceSourceType;

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
    update({ audience_source: next, recipients: [], db_query: "", audience_database_config: null, source_file: null });
  }

  return (
    <div className="space-y-5">
      <Card className="p-5 shadow-card space-y-3">
        <Label className="text-base font-medium">Audience Source</Label>
        <RadioGroup value={source} onValueChange={(value) => switchSource(value as AudienceSourceType)} className="grid gap-3 sm:grid-cols-3">
          {SOURCES.map((item) => (
            <label key={item.value} htmlFor={`wizard-src-${item.value}`} className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${source === item.value ? "border-primary bg-primary/5" : "hover:bg-muted/40"}`}>
              <RadioGroupItem value={item.value} id={`wizard-src-${item.value}`} className="mt-0.5" />
              <div>
                <div className="flex items-center gap-1.5 text-sm font-medium"><item.icon className="h-3.5 w-3.5" /> {item.label}</div>
                <p className="text-xs text-muted-foreground mt-0.5">{item.desc}</p>
              </div>
            </label>
          ))}
        </RadioGroup>
      </Card>
      <Card className="p-5 shadow-card">
        {source === "manual" && <ManualInsertTab records={records} onChange={updateRecords} />}
        {source === "file" && (
          <CsvUploadTab
            records={records}
            onChange={updateRecords}
            onSourceFileChange={(source_file) => update({ source_file })}
          />
        )}
        {source === "database" && (
          <DatabaseTab
            records={records}
            onChange={updateRecords}
            initialConfig={data.audience_database_config}
            onConfigChange={(audience_database_config) => update({ audience_database_config })}
          />
        )}
      </Card>
      {errors.recipients && <p className="text-sm text-destructive">{errors.recipients}</p>}
    </div>
  );
}
