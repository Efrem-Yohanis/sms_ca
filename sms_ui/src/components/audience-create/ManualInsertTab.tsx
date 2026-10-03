import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2 } from "lucide-react";
import { SUPPORTED_LANGUAGES, LANGUAGE_LABELS } from "@/types/campaign";
import type { AudienceRecord } from "@/types/audience";
import { isValidMsisdn, normalizeMsisdn } from "@/types/audience";
import LanguageMappingPanel from "./LanguageMappingPanel";

interface Props {
  records: AudienceRecord[];
  onChange: (r: AudienceRecord[]) => void;
}

const NONE = "__none__";

export default function ManualInsertTab({ records, onChange }: Props) {
  function addRow() {
    onChange([...records, { msisdn: "", lang: null, source: "manual" }]);
  }

  function removeRow(i: number) {
    onChange(records.filter((_, idx) => idx !== i));
  }

  function updateRow(i: number, field: "msisdn" | "lang", value: string | null) {
    const updated = [...records];
    updated[i] = { ...updated[i], [field]: value, lang_source: field === "lang" && value ? "input" : updated[i].lang_source };
    onChange(updated);
  }

  function getError(msisdn: string) {
    if (!msisdn) return null;
    return isValidMsisdn(msisdn) ? null : "Invalid MSISDN (use +2517XXXXXXXX or 7XXXXXXXX)";
  }

  function normalizeAll() {
    onChange(
      records.map((r) => ({ ...r, msisdn: normalizeMsisdn(r.msisdn) || r.msisdn })),
    );
  }

  const validRecords = records.filter((r) => isValidMsisdn(r.msisdn));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-base font-medium">Manual MSISDN Entry</Label>
          <p className="text-xs text-muted-foreground mt-0.5">
            Format: +2517XXXXXXXX. Numeric-only values (7XXXXXXXX / 07XXXXXXXX) are also accepted.
            Language is optional.
          </p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={normalizeAll} disabled={!records.length}>
            Normalize
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={addRow} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" /> Add Row
          </Button>
        </div>
      </div>

      {records.length === 0 && (
        <div className="text-center py-8 border border-dashed rounded-md">
          <p className="text-sm text-muted-foreground mb-3">No MSISDNs added yet</p>
          <Button type="button" variant="outline" size="sm" onClick={addRow} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" /> Add First MSISDN
          </Button>
        </div>
      )}

      {records.length > 0 && (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          <div className="grid grid-cols-[1fr_170px_40px] gap-2 text-xs font-medium text-muted-foreground px-1">
            <span>MSISDN</span>
            <span>Language (optional)</span>
            <span></span>
          </div>
          {records.map((r, i) => {
            const err = getError(r.msisdn);
            return (
              <div key={i} className="grid grid-cols-[1fr_170px_40px] gap-2 items-start">
                <div>
                  <Input
                    value={r.msisdn}
                    onChange={(e) => updateRow(i, "msisdn", e.target.value)}
                    placeholder="+251712345678"
                    className={err ? "border-destructive" : ""}
                  />
                  {err && <p className="text-[11px] text-destructive mt-0.5">{err}</p>}
                </div>
                <Select
                  value={r.lang || NONE}
                  onValueChange={(v) => updateRow(i, "lang", v === NONE ? null : v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select language" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>None (optional)</SelectItem>
                    {SUPPORTED_LANGUAGES.map((l) => (
                      <SelectItem key={l} value={l}>{LANGUAGE_LABELS[l]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 text-destructive hover:text-destructive"
                  onClick={() => removeRow(i)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <LanguageMappingPanel
        records={validRecords}
        defaultSourceColumn="MSISDN"
        onApply={(mapped) => onChange(mapped)}
      />
    </div>
  );
}
