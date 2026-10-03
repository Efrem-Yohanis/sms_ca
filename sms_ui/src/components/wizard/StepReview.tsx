import { useEffect, useState } from "react";
import type { WizardData } from "@/types/campaign";
import { LANGUAGE_LABELS, SCHEDULE_TYPE_LABELS, DAY_LABELS, CHANNEL_LABELS } from "@/types/campaign";
import type { Language } from "@/types/campaign";
import { Users, CalendarClock, MessageSquare, ClipboardList, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { fetchCampaign, type ApiCampaign } from "@/lib/api";

interface Props {
  data: WizardData;
  campaignId?: number | null;
}

export default function StepReview({ data, campaignId }: Props) {
  const [apiCampaign, setApiCampaign] = useState<ApiCampaign | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!campaignId) return;
    setLoading(true);
    fetchCampaign(campaignId)
      .then(setApiCampaign)
      .catch(() => setApiCampaign(null))
      .finally(() => setLoading(false));
  }, [campaignId]);

  const filledLangs = (Object.entries(data.content) as [Language, string][]).filter(([, t]) => t.trim());
  const langCounts: Record<string, number> = {};
  data.recipients.forEach((r) => {
    const label = LANGUAGE_LABELS[r.lang] || r.lang;
    langCounts[label] = (langCounts[label] || 0) + 1;
  });

  // Readiness from API
  const hasSchedule = !!apiCampaign?.schedule;
  const hasAudience = !!apiCampaign?.audience;
  const hasContent = !!apiCampaign?.message_content;
  const canStart = apiCampaign?.can_start ?? false;

  return (
    <div className="space-y-6">
      {/* Readiness Banner */}
      {campaignId && (
        <div className="border rounded-sm p-4 space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Campaign Readiness
          </h3>
          {!loading && apiCampaign && (
            <div className="flex gap-4 text-sm">
              <ReadinessItem ok={hasAudience} label="Audience" />
              <ReadinessItem ok={hasContent} label="Message Content" />
              <ReadinessItem ok={hasSchedule} label="Schedule" />
            </div>
          )}
          {!loading && canStart && (
            <p className="text-sm text-green-600 font-medium mt-1">
              ✓ All components ready — you can start this campaign!
            </p>
          )}
        </div>
      )}

      {/* Campaign Info */}
      <ReviewSection icon={ClipboardList} title="Campaign Info">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ReviewField label="Name" value={data.name || "—"} />
          <ReviewField label="Sender ID" value={data.sender_id || "—"} />
          <div>
            <p className="text-xs text-muted-foreground mb-1">Channels</p>
            <div className="flex gap-1.5 flex-wrap">
              {(data.channels || []).map((ch) => (
                <Badge key={ch} variant="secondary">{CHANNEL_LABELS[ch] || ch}</Badge>
              ))}
              {(!data.channels || data.channels.length === 0) && <span className="text-muted-foreground">—</span>}
            </div>
          </div>
        </div>
      </ReviewSection>

      {/* Audience */}
      <ReviewSection icon={Users} title="Audience">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <div className="border rounded-sm p-3 text-center">
            <p className="text-2xl font-semibold text-foreground">{data.recipients.length.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground mt-1">Total Recipients</p>
          </div>
          <div className="border rounded-sm p-3 text-center">
            <p className="text-2xl font-semibold text-foreground">{Object.keys(langCounts).length}</p>
            <p className="text-xs text-muted-foreground mt-1">Languages</p>
          </div>
          <div className="border rounded-sm p-3 text-center">
            <p className="text-2xl font-semibold text-foreground">{filledLangs.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Message Translations</p>
          </div>
        </div>
        {Object.keys(langCounts).length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-2">Recipients by Language</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(langCounts).map(([label, count]) => (
                <Badge key={label} variant="outline" className="text-xs">
                  {label}: {count.toLocaleString()}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </ReviewSection>

      {/* Message Content */}
      <ReviewSection icon={MessageSquare} title="Message Content">
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Default Language</p>
            <Badge variant="secondary">{LANGUAGE_LABELS[data.default_language]}</Badge>
          </div>
          {filledLangs.length === 0 && <p className="text-muted-foreground text-sm">No messages added.</p>}
          {filledLangs.map(([lang, text]) => (
            <div key={lang} className="border rounded-sm p-3 bg-muted/30">
              <p className="text-xs text-muted-foreground mb-1">
                {LANGUAGE_LABELS[lang]}
                {lang === data.default_language && " (default)"}
                <span className="ml-2">{text.length} chars · {Math.ceil(text.length / 160)} SMS</span>
              </p>
              <p className="text-sm text-foreground whitespace-pre-wrap">{text}</p>
            </div>
          ))}
        </div>
      </ReviewSection>

      {/* Schedule */}
      <ReviewSection icon={CalendarClock} title="Schedule">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Type</p>
            <Badge variant="secondary">{SCHEDULE_TYPE_LABELS[data.schedule_type]}</Badge>
          </div>
          <ReviewField
            label={data.schedule_type === "once" ? "Send Date" : "Start Date"}
            value={data.start_date || "—"}
          />
          {data.schedule_type !== "once" && data.end_date && (
            <ReviewField label="End Date" value={data.end_date} />
          )}
          {data.schedule_type === "weekly" && data.run_days.length > 0 && (
            <div>
              <p className="text-xs text-muted-foreground mb-1">Run Days</p>
              <div className="flex flex-wrap gap-1">
                {data.run_days.map((d) => (
                  <Badge key={d} variant="secondary" className="text-xs">
                    {DAY_LABELS[d] || `Day ${d}`}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <div>
            <p className="text-xs text-muted-foreground mb-1">Time Windows</p>
            <div className="flex flex-wrap gap-2">
              {data.time_windows.filter((tw) => tw.start || tw.end).length > 0
                ? data.time_windows.map((tw, i) => (
                    <Badge key={i} variant="outline" className="text-xs font-mono">
                      {tw.start || "??"} – {tw.end || "??"}
                    </Badge>
                  ))
                : <span className="text-foreground">—</span>}
            </div>
          </div>
          <ReviewField label="Timezone" value={data.timezone} />
        </div>
      </ReviewSection>
    </div>
  );
}

function ReviewSection({ icon: Icon, title, children }: {
  icon: React.ElementType; title: string; children: React.ReactNode;
}) {
  return (
    <section className="border rounded-sm overflow-hidden">
      <div className="px-4 py-3 bg-secondary/50 border-b flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">{title}</span>
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}

function ReviewField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      <p className="font-medium text-foreground">{value}</p>
    </div>
  );
}

function ReadinessItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={ok ? "text-green-600" : "text-destructive"}>
      {ok ? <CheckCircle2 className="h-4 w-4 inline mr-1" /> : <XCircle className="h-4 w-4 inline mr-1" />}
      {label}
    </span>
  );
}
