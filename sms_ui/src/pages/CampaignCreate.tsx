import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { WizardData } from "@/types/campaign";
import { EMPTY_WIZARD, SUPPORTED_LANGUAGES } from "@/types/campaign";
import StepBasics from "@/components/wizard/StepBasics";
import StepAudience from "@/components/wizard/StepAudience";
import StepMessages from "@/components/wizard/StepMessages";
import StepSchedule from "@/components/wizard/StepSchedule";
import StepReview from "@/components/wizard/StepReview";
import { Check, ClipboardList, Users, MessageSquare, CalendarClock, Eye, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  createCampaign, updateCampaignApi, fetchCampaign,
  saveCampaignAudience, createCampaignMessageContent, updateMessageContent,
  createSchedule, updateSchedule, fetchMessageContent, fetchSchedule,
} from "@/lib/api";
import { fetchCampaignAudienceConfig, fetchCampaignAudienceMembers } from "@/lib/api/audiences";
import type { AudienceBuildProgress } from "@/lib/api/audiences";
import { fetchAssignedConfigurations, fetchLanguages } from "@/lib/api/configurations";
import type { Channel, Language, ScheduleType } from "@/types/campaign";

const STEPS = [
  { label: "Campaign Info", icon: ClipboardList },
  { label: "Audience", icon: Users },
  { label: "Message", icon: MessageSquare },
  { label: "Schedule", icon: CalendarClock },
  { label: "Review", icon: Eye },
];

interface WizardIds {
  campaignId: number | null;
  audienceId: number | null;
  messageId: number | null;
  scheduleId: number | null;
}

export default function CampaignCreate() {
  const navigate = useNavigate();
  const { id: routeId } = useParams<{ id: string }>();
  const editingCampaignId = routeId ? Number(routeId) : null;
  const [loadingExisting, setLoadingExisting] = useState(Boolean(editingCampaignId));
  const [step, setStep] = useState(0);
  const [data, setData] = useState<WizardData>({
    ...EMPTY_WIZARD,
    content: { ...EMPTY_WIZARD.content },
    time_windows: [...EMPTY_WIZARD.time_windows],
  });
  const [ids, setIds] = useState<WizardIds>({
    campaignId: null, audienceId: null, messageId: null, scheduleId: null,
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [audienceBuildProgress, setAudienceBuildProgress] = useState<AudienceBuildProgress | null>(null);

  useEffect(() => {
    if (!editingCampaignId) return;
    let active = true;

    async function loadDraft() {
      try {
        const campaign = await fetchCampaign(editingCampaignId!);
        if (campaign.status !== "draft") {
          toast.error("Only draft campaigns can be edited");
          navigate(`/campaigns/${editingCampaignId}`);
          return;
        }

        const [assigned, languageResponse] = await Promise.all([fetchAssignedConfigurations(), fetchLanguages()]);
        const channelCodes = new Map(assigned.channels.map((channel) => [channel.id, channel.code as Channel]));
        const defaultLanguageForValue = (languageValue: unknown) =>
          languageResponse.results.find((language) =>
            String(language.id) === String(languageValue) || language.code === String(languageValue),
          )?.code;

        const [audienceConfig, messageContent, schedule] = await Promise.all([
          campaign.audience_id ? fetchCampaignAudienceConfig(editingCampaignId!).catch(() => null) : Promise.resolve(null),
          campaign.message_content_id ? fetchMessageContent(editingCampaignId!).catch(() => null) : Promise.resolve(null),
          campaign.schedule_id ? fetchSchedule(editingCampaignId!).catch(() => null) : Promise.resolve(null),
        ]);

        let audienceRecipients: WizardData["recipients"] = [];
        let databaseConfig: WizardData["audience_database_config"] = null;
        let audienceSource: WizardData["audience_source"] = "manual";
        if (audienceConfig) {
          audienceSource = audienceConfig.source_type === "database"
            ? "database"
            : audienceConfig.source_type === "file_import" ? "file" : "manual";
          databaseConfig = audienceConfig.source_type === "database" ? {
            source_database_id: audienceConfig.source_database_id ?? 0,
            source_table: audienceConfig.source_table,
            source_msisdn_column: audienceConfig.source_msisdn_column,
            source_language_column: audienceConfig.source_language_column,
            source_filter_clause: audienceConfig.source_filter_clause,
          } : null;
          const manualRecipients = (audienceConfig.manual_msisdns ?? []).map((msisdn, index) => ({
            msisdn,
            lang: (audienceConfig.manual_languages?.[index] || defaultLanguageForValue(audienceConfig.default_language_id) || "en") as Language,
          }));
          audienceRecipients = manualRecipients;
        }
        if (campaign.audience_id && audienceRecipients.length === 0) {
          const members = await fetchCampaignAudienceMembers(editingCampaignId!, 1000).catch(() => []);
          audienceRecipients = members.map((member) => ({
            msisdn: member.msisdn,
            lang: (defaultLanguageForValue(member.language) || "en") as Language,
          }));
        }

        const contentObject = messageContent as Record<string, unknown> | null;
        const contentMap = (contentObject?.content && typeof contentObject.content === "object"
          ? contentObject.content
          : contentObject) as Record<string, string> | null;
        const scheduleObject = schedule as Record<string, unknown> | null;
        const scheduleType = String(scheduleObject?.schedule_type || "once") as ScheduleType;
        if (!active) return;

        setData({
          ...EMPTY_WIZARD,
          name: campaign.name,
          owner_emails: campaign.owner_emails ?? [],
          sender_id: campaign.sender_id,
          channels: (campaign.channels_id ?? []).map((channelId) => channelCodes.get(channelId)).filter((channel): channel is Channel => Boolean(channel)),
          audience_source: audienceSource,
          audience_database_config: databaseConfig,
          recipients: audienceRecipients,
          default_language: (defaultLanguageForValue(audienceConfig?.default_language_id ?? contentObject?.default_language) || "en") as Language,
          content: {
            en: contentMap?.en ?? "",
            am: contentMap?.am ?? "",
            ti: contentMap?.ti ?? "",
            om: contentMap?.om ?? "",
            so: contentMap?.so ?? "",
          },
          schedule_type: scheduleType,
          start_date: String(scheduleObject?.start_date ?? ""),
          end_date: String(scheduleObject?.end_date ?? ""),
          run_days: Array.isArray(scheduleObject?.run_days) ? scheduleObject.run_days as number[] : [],
          time_windows: Array.isArray(scheduleObject?.time_windows)
            ? scheduleObject.time_windows as WizardData["time_windows"]
            : [...EMPTY_WIZARD.time_windows],
          timezone: String(scheduleObject?.timezone ?? "UTC"),
          auto_reset: Boolean(scheduleObject?.auto_reset ?? true),
        });
        setIds({
          campaignId: editingCampaignId,
          audienceId: audienceConfig?.id ?? null,
          messageId: typeof contentObject?.id === "number" ? contentObject.id : null,
          scheduleId: typeof scheduleObject?.id === "number" ? scheduleObject.id : null,
        });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "Unable to load draft campaign");
        navigate("/campaigns");
      } finally {
        if (active) setLoadingExisting(false);
      }
    }

    void loadDraft();
    return () => { active = false; };
  }, [editingCampaignId, navigate]);

  function update(partial: Partial<WizardData>) {
    setData((prev) => ({ ...prev, ...partial }));
    setErrors({});
  }

  function validateStep(): boolean {
    const errs: Record<string, string> = {};

    if (step === 0) {
      if (!data.name.trim()) errs.name = "Name is required";
      if (data.channels.length === 0) errs.channels = "Select at least one channel";
      if (!data.sender_id) errs.sender_id = "Select a sender ID";
    }

    if (step === 1) {
      if (data.audience_source === "database" && !data.audience_database_config) {
        errs.recipients = "Choose and preview a database source";
      } else if (data.audience_source !== "database" && data.recipients.length === 0) {
        errs.recipients = "Add at least one recipient";
      }
      const phonePattern = /^\+?[1-9]\d{1,14}$/;
      const invalid = data.recipients.findIndex((r) => !phonePattern.test(r.msisdn));
      if (invalid >= 0) errs.recipients = `Recipient ${invalid + 1} has an invalid phone number`;
    }

    if (step === 2) {
      const hasContent = SUPPORTED_LANGUAGES.some((l) => data.content[l].trim().length > 0);
      if (!hasContent) errs.content = "At least one language message is required";
    }

    if (step === 3) {
      if (!data.start_date) errs.start_date = "Start date is required";
      if (data.time_windows.length === 0) {
        errs.time_windows = "At least one time window is required";
      } else if (data.time_windows.some((tw) => !tw.start.trim() || !tw.end.trim() || tw.start >= tw.end)) {
        errs.time_windows = "Each time window needs a start time earlier than its end time";
      } else {
        const windows = [...data.time_windows].sort((left, right) => left.start.localeCompare(right.start));
        if (windows.some((window, index) => index > 0 && window.start < windows[index - 1].end)) {
          errs.time_windows = "Time windows cannot overlap";
        }
      }
      if (data.schedule_type === "weekly" && data.run_days.length === 0) {
        errs.run_days = "Select at least one run day";
      }
      if (data.schedule_type !== "once" && data.end_date && data.start_date && data.start_date >= data.end_date) {
        errs.end_date = "End date must be after start date";
      }
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  if (loadingExisting) {
    return <div className="flex min-h-64 items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;
  }

  async function saveAndNext() {
    if (!validateStep()) return;
    setSaving(true);

    try {
      if (step === 0) {
        // Create or update campaign
        if (ids.campaignId) {
          await updateCampaignApi(ids.campaignId, {
            name: data.name,
            owner_emails: data.owner_emails,
            sender_id: data.sender_id,
            channels: data.channels,
          });
        } else {
          const result = await createCampaign({
            name: data.name,
            owner_emails: data.owner_emails,
            sender_id: data.sender_id,
            channels: data.channels,
          });
          setIds((prev) => ({ ...prev, campaignId: result.id }));
        }
        toast.success("Campaign info saved");
      }

      if (step === 1 && ids.campaignId) {
        // Create or update audience
        setAudienceBuildProgress(null);
        const payload = {
          recipients: data.recipients.map((r) => ({ msisdn: r.msisdn, lang: r.lang })),
          default_language: data.default_language,
          source_type: data.audience_source,
          database_config: data.audience_database_config,
          source_file: data.source_file,
        };
        const result = await saveCampaignAudience(
          ids.campaignId,
          payload,
          (progress) => setAudienceBuildProgress(progress),
        );
        setIds((prev) => ({ ...prev, audienceId: result.audience_id }));
        toast.success(`Audience built: ${result.valid_count} valid, ${result.invalid_count} invalid`);
      }

      if (step === 2 && ids.campaignId) {
        // Create or update message content
        const contentEntries = Object.entries(data.content).filter(([, v]) => v.trim());
        const payload = {
          content: Object.fromEntries(contentEntries),
          default_language: data.default_language,
        };
        if (ids.messageId) {
          await updateMessageContent(ids.campaignId, payload);
        } else {
          await createCampaignMessageContent(ids.campaignId, payload);
          setIds((prev) => ({ ...prev, messageId: ids.campaignId }));
        }
        toast.success("Message content saved");
      }

      if (step === 3 && ids.campaignId) {
        // Create schedule
        const schedulePayload = {
          schedule_type: data.schedule_type,
          start_date: data.start_date,
          end_date: data.end_date || null,
          ...(data.run_days.length > 0 ? { run_days: data.run_days } : {}),
          time_windows: data.time_windows,
          timezone: data.timezone,
          auto_reset: data.auto_reset,
        };
        if (ids.scheduleId) {
          await updateSchedule(ids.campaignId, schedulePayload);
        } else {
          const schedule = await createSchedule(ids.campaignId, schedulePayload);
          setIds((prev) => ({ ...prev, scheduleId: schedule.id }));
        }
        toast.success("Schedule saved");
      }

      setStep(step + 1);
    } catch (err: any) {
      toast.error(`Failed to save: ${err.message || "Unknown error"}`);
    } finally {
      setSaving(false);
    }
  }

  function goBack() {
    if (step > 0) setStep(step - 1);
  }

  async function handleFinish() {
    if (!ids.campaignId) return;
    toast.success(`Campaign "${data.name}" created successfully!`);
    navigate(`/campaigns/${ids.campaignId}`);
  }

  return (
    <div className="w-full">
      {/* Stepper */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          {STEPS.map((s, i) => {
            const Icon = s.icon;
            const isCompleted = i < step;
            const isCurrent = i === step;
            return (
              <div key={i} className="flex-1 flex flex-col items-center relative">
                {i > 0 && (
                  <div
                    className={cn(
                      "absolute top-5 -left-1/2 w-full h-0.5",
                      isCompleted ? "bg-primary" : "bg-border"
                    )}
                    style={{ zIndex: 0 }}
                  />
                )}
                <div
                  className={cn(
                    "relative z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors",
                    isCompleted
                      ? "bg-primary border-primary text-primary-foreground"
                      : isCurrent
                      ? "border-primary bg-background text-primary"
                      : "border-muted bg-muted text-muted-foreground"
                  )}
                >
                  {isCompleted ? <Check className="h-5 w-5" /> : <Icon className="h-5 w-5" />}
                </div>
                <span
                  className={cn(
                    "mt-2 text-xs font-medium text-center",
                    isCurrent ? "text-primary" : isCompleted ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Step content */}
      <div className="bg-card border rounded-sm">
        <div className="px-6 py-4 border-b">
          <h2 className="text-lg font-semibold">{STEPS[step].label}</h2>
          <span className="text-sm text-muted-foreground">Step {step + 1} of 5</span>
          {ids.campaignId && (
            <span className="text-xs text-muted-foreground ml-3">Campaign ID: {ids.campaignId}</span>
          )}
        </div>

        <div className="px-6 py-6 min-h-[320px]">
          {step === 0 && <StepBasics data={data} errors={errors} update={update} />}
          {step === 1 && <StepAudience data={data} errors={errors} update={update} />}
          {step === 2 && (
            <StepMessages
              data={data}
              errors={errors}
              update={update}
              messageId={ids.messageId}
            />
          )}
          {step === 3 && <StepSchedule data={data} errors={errors} update={update} />}
          {step === 4 && (
            <StepReview
              data={data}
              campaignId={ids.campaignId}
            />
          )}
        </div>

        {step === 1 && saving && (
          <div className="mx-6 mb-5 space-y-2" role="status" aria-live="polite">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Building audience</span>
              <span className="text-muted-foreground">
                {audienceBuildProgress?.total
                  ? `${Math.round(audienceBuildProgress.percent)}%`
                  : audienceBuildProgress?.phase || "Starting"}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-secondary" role="progressbar" aria-label="Audience build progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={audienceBuildProgress?.total ? Math.round(audienceBuildProgress.percent) : undefined}>
              <div
                className={`h-full bg-primary transition-all ${audienceBuildProgress?.total ? "" : "w-1/3 animate-progress-indeterminate"}`}
                style={audienceBuildProgress?.total ? { width: `${Math.min(audienceBuildProgress.percent, 100)}%` } : undefined}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {audienceBuildProgress
                ? `${audienceBuildProgress.phase}: ${audienceBuildProgress.processed.toLocaleString()}${audienceBuildProgress.total ? ` / ${audienceBuildProgress.total.toLocaleString()}` : " rows processed"}`
                : "Saving source and starting build..."}
            </p>
          </div>
        )}

        <div className="px-6 py-4 border-t flex justify-between">
          <Button
            variant="outline"
            onClick={step === 0 ? () => navigate("/campaigns") : goBack}
            disabled={saving}
          >
            {step === 0 ? "Cancel" : "← Back"}
          </Button>

          {step === 4 ? (
            <Button onClick={handleFinish} disabled={saving} className="gap-1.5">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Save Draft
            </Button>
          ) : (
            <Button onClick={saveAndNext} disabled={saving} className="gap-1.5">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {saving ? "Saving…" : "Save & Next →"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
