import { useState, useEffect } from "react";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WizardData, Language } from "@/types/campaign";
import { SUPPORTED_LANGUAGES, LANGUAGE_LABELS } from "@/types/campaign";
import { fetchSupportedLanguages } from "@/lib/api/messages";

interface Props {
  data: WizardData;
  errors: Record<string, string>;
  update: (partial: Partial<WizardData>) => void;
  messageId?: number | null;
}

export default function StepMessages({ data, errors, update, messageId }: Props) {
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);

  // Load supported languages from API
  useEffect(() => {
    fetchSupportedLanguages()
      .then((res) => {
        setLanguages(res.languages);
      })
      .catch(() => {
        // Fallback to local constants
        setLanguages(SUPPORTED_LANGUAGES.map((l) => ({ code: l, name: LANGUAGE_LABELS[l] })));
      });
  }, []);

  const displayLanguages = languages.length > 0
    ? languages
    : SUPPORTED_LANGUAGES.map((l) => ({ code: l, name: LANGUAGE_LABELS[l] }));

  function updateContent(lang: Language, text: string) {
    update({ content: { ...data.content, [lang]: text } });
  }

  return (
    <div className="space-y-5">
      {/* Default language */}
      <div className="space-y-1.5">
        <Label>Default language</Label>
        <Select
          value={data.default_language}
          onValueChange={(v) => update({ default_language: v as Language })}
        >
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {displayLanguages.map((l) => (
              <SelectItem key={l.code} value={l.code}>{l.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Language message inputs */}
      {displayLanguages.map((lang) => {
        const code = lang.code as Language;
        const charCount = (data.content[code] || "").length;
        const segments = Math.ceil(charCount / 160) || 0;
        return (
          <div key={code} className="space-y-1.5">
            <Label className="flex items-center gap-2">
              {lang.name}
              {code === data.default_language && (
                <Badge variant="secondary" className="text-xs">default</Badge>
              )}
            </Label>
            <Textarea
              value={data.content[code] || ""}
              onChange={(e) => updateContent(code, e.target.value)}
              placeholder={`Message in ${lang.name}. Use {name} for variables.`}
              rows={3}
              maxLength={1600}
            />
            <div className="flex gap-3 text-xs text-muted-foreground">
              <span>{charCount}/1600 characters</span>
              {charCount > 0 && <span>{segments} SMS segment{segments !== 1 ? "s" : ""}</span>}
            </div>
          </div>
        );
      })}

      {errors.content && <p className="text-sm text-destructive">{errors.content}</p>}
    </div>
  );
}
