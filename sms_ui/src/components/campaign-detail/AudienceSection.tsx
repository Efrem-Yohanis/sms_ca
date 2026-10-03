import { Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Section, StatCard } from "./Section";
import type { Audience } from "@/types/campaign";
import { LANGUAGE_LABELS } from "@/types/campaign";

export function AudienceSection({ audience }: { audience: Audience }) {
  const langCounts: Record<string, number> = {};
  audience.recipients.forEach((r) => {
    const label = LANGUAGE_LABELS[r.lang] || r.lang;
    langCounts[label] = (langCounts[label] || 0) + 1;
  });

  return (
    <Section icon={Users} title="Audience">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <StatCard label="Total Recipients" value={audience.total_count.toLocaleString()} />
        <StatCard label="Valid" value={audience.valid_count.toLocaleString()} color="text-green-600" />
        <StatCard label="Invalid" value={audience.invalid_count.toLocaleString()} color="text-destructive" />
      </div>
      {Object.keys(langCounts).length > 0 && (
        <div className="mt-4">
          <span className="text-sm text-muted-foreground">By Language</span>
          <div className="flex flex-wrap gap-2 mt-1">
            {Object.entries(langCounts).map(([lang, count]) => (
              <Badge key={lang} variant="secondary">
                {lang}: {count}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}
