import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  ArrowLeft, Radio, Loader2, Play, Pause, Square,
  Trash2, Edit, BarChart3, Layers, Clock, Send, CheckCircle2,
  XCircle, Mail, Users, MessageSquare, CalendarClock, AlertTriangle, RefreshCw
} from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle
} from "@/components/ui/alert-dialog";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { useState, useCallback } from "react";
import {
  fetchCampaign, fetchCampaignProgress, fetchCampaignBatches,
  activateCampaign, startCampaign, pauseCampaign, resumeCampaign, stopCampaign,
  completeCampaign, archiveCampaign, softDeleteCampaign,
  type ApiCampaign
} from "@/lib/api";
import {
  buildCampaignMessages, clearCampaignMessages, fetchCampaignMessages,
  fetchCampaignMessageStats, fetchCampaignMessageBuildProgress, fetchMessageContentDetail,
} from "@/lib/api/messages";
import type { CampaignMessageQueueItem } from "@/lib/api/messages";
import type { CampaignStatus, Channel } from "@/types/campaign";
import { CHANNEL_LABELS, SCHEDULE_TYPE_LABELS, LANGUAGE_LABELS, DAY_LABELS } from "@/types/campaign";
import { Section, Field } from "@/components/campaign-detail/Section";
import CampaignReports from "@/components/campaign-detail/CampaignReports";

/* ─── Status colors ─── */
const STATUS_COLORS: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  active: "bg-green-100 text-green-800",
  in_progress: "bg-green-100 text-green-800",
  paused: "bg-yellow-100 text-yellow-800",
  completed: "bg-blue-100 text-blue-800",
  archived: "bg-secondary text-secondary-foreground",
};

const EXEC_STATUS_COLORS: Record<string, string> = {
  PENDING: "bg-muted text-muted-foreground",
  PROCESSING: "bg-green-100 text-green-800",
  PAUSED: "bg-yellow-100 text-yellow-800",
  COMPLETED: "bg-blue-100 text-blue-800",
  FAILED: "bg-destructive/10 text-destructive",
  STOPPED: "bg-yellow-100 text-yellow-800",
};

/* ─── Helpers ─── */
function pct(v: number, t: number) {
  return t === 0 ? "0%" : `${((v / t) * 100).toFixed(1)}%`;
}

/* ─── Main Component ─── */
export default function CampaignDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const numId = Number(id);

  const [confirmAction, setConfirmAction] = useState<{
    label: string; description: string; variant: "default" | "destructive";
    action: () => Promise<any>;
  } | null>(null);
  const [acting, setActing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [batchPage, setBatchPage] = useState(1);

  // Campaign detail
  const { data: campaign, isLoading, error } = useQuery({
    queryKey: ["campaign", numId],
    queryFn: () => fetchCampaign(numId),
    enabled: !!numId,
    refetchInterval: 300000,
  });

  const { data: linkedMessageContent } = useQuery({
    queryKey: ["campaign-message-content", numId, campaign?.message_content_id],
    queryFn: () => fetchMessageContentDetail(Number(campaign?.message_content_id)),
    enabled: Boolean(campaign && !campaign.message_content && campaign.message_content_id),
  });

  // Progress
  const { data: progressData } = useQuery({
    queryKey: ["campaign-progress", numId],
    queryFn: () => fetchCampaignProgress(numId),
    enabled: !!numId,
    refetchInterval: 300000,
  });

  // Batches
  const { data: batchesData } = useQuery({
    queryKey: ["campaign-batches", numId, batchPage],
    queryFn: () => fetchCampaignBatches(numId),
    enabled: !!numId,
    refetchInterval: 300000,
  });

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["campaign", numId] });
    queryClient.invalidateQueries({ queryKey: ["campaign-progress", numId] });
    queryClient.invalidateQueries({ queryKey: ["campaign-batches", numId] });
    queryClient.invalidateQueries({ queryKey: ["campaign-message-stats", numId] });
    queryClient.invalidateQueries({ queryKey: ["campaign-messages", numId] });
    queryClient.invalidateQueries({ queryKey: ["campaign-message-build-progress", numId] });
  }, [queryClient, numId]);

  async function refreshCampaign() {
    setRefreshing(true);
    try {
      await Promise.all([
        queryClient.refetchQueries({ queryKey: ["campaign", numId] }),
        queryClient.refetchQueries({ queryKey: ["campaign-progress", numId] }),
        queryClient.refetchQueries({ queryKey: ["campaign-batches", numId] }),
        queryClient.refetchQueries({ queryKey: ["campaign-message-stats", numId] }),
        queryClient.refetchQueries({ queryKey: ["campaign-messages", numId] }),
        queryClient.refetchQueries({ queryKey: ["campaign-message-build-progress", numId] }),
      ]);
    } catch (err) {
      toast.error(`Failed to refresh campaign: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setRefreshing(false);
    }
  }

  async function execAction(action: () => Promise<any>, label: string) {
    setActing(true);
    try {
      const res = await action();
      if (label === "Activate Campaign" && res?.data?.owner_notification_sent === false) {
        toast.warning("Campaign activated, but the owner email was not sent. Check the active email configuration.");
      } else {
        toast.success(res?.message || `${label} successful`);
      }
      invalidate();
    } catch (err: any) {
      toast.error(`Failed to ${label.toLowerCase()}: ${err.message}`);
    } finally {
      setActing(false);
      setConfirmAction(null);
    }
  }

  function confirmAndExec(label: string, description: string, action: () => Promise<any>, variant: "default" | "destructive" = "default") {
    setConfirmAction({ label, description, variant, action });
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <div className="text-center py-20 text-muted-foreground">
        <p>Campaign not found.</p>
        <Link to="/campaigns" className="text-primary hover:underline mt-2 inline-block">Back to campaigns</Link>
      </div>
    );
  }

  const c = campaign;
  const messageContent = c.message_content ?? linkedMessageContent;
  const p = progressData?.progress;
  const batches = progressData?.batches;
  const recentBatches = (progressData as any)?.recent_batches || [];
  const batchList = Array.isArray(batchesData) ? batchesData : (batchesData as any)?.results || recentBatches;

  const channels: string[] = Array.isArray(c.channels)
    ? c.channels
    : Object.values(c.channels || {});

  return (
    <div className="space-y-6 w-full">
      {/* ─── Header ─── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate("/campaigns")}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-xl font-semibold">{c.name}</h1>
            <p className="text-sm text-muted-foreground">
              Created {new Date(c.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => void refreshCampaign()}
            disabled={refreshing}
            aria-label="Refresh campaign details"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Badge className={STATUS_COLORS[c.status] || "bg-muted"}>{c.status}</Badge>
          {c.execution_status_display && (
            <Badge className={EXEC_STATUS_COLORS[c.execution_status] || ""} variant="outline">
              {c.execution_status_display}
            </Badge>
          )}
        </div>
      </div>

      {/* ─── Action Buttons ─── */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" disabled={acting || c.status !== "draft" || !c.is_ready_to_execute} onClick={() => confirmAndExec(
          "Activate Campaign",
          "This builds the message queue, confirms the campaign is ready to execute, and activates it. It will not start sending until you choose Start.",
          () => activateCampaign(numId),
        )} className="gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5" /> Activate
        </Button>
        <Button size="sm" disabled={acting || !["active", "in_progress", "paused", "stopped"].includes(c.status)} onClick={() => confirmAndExec(
          "Start Campaign",
          "Start the SMS sender immediately for queued messages, regardless of the schedule window.",
          () => startCampaign(numId),
        )} className="gap-1.5">
          <Play className="h-3.5 w-3.5" /> Start
        </Button>
        <Button size="sm" variant="outline" disabled={acting || c.status !== "in_progress"} onClick={() => confirmAndExec(
          "Stop Campaign",
          "Stop the running campaign and mark it completed. This does not cancel or delete it.",
          () => completeCampaign(numId),
        )} className="gap-1.5">
          <Square className="h-3.5 w-3.5" /> Stop
        </Button>
        <Button size="sm" variant="outline" disabled={acting || c.status !== "in_progress"} onClick={() => confirmAndExec(
          "Pause Campaign",
          "Temporarily suspend sending. You can resume this campaign later.",
          () => pauseCampaign(numId),
        )} className="gap-1.5">
          <Pause className="h-3.5 w-3.5" /> Pause
        </Button>
        <Button size="sm" disabled={acting || c.status !== "paused"} onClick={() => confirmAndExec(
          "Resume Campaign",
          "Continue sending queued messages from where this campaign paused.",
          () => resumeCampaign(numId),
        )} className="gap-1.5">
          <Play className="h-3.5 w-3.5" /> Resume
        </Button>
        <Button size="sm" variant="destructive" disabled={acting || !["active", "in_progress", "paused"].includes(c.status)} onClick={() => confirmAndExec(
          "Cancel Campaign",
          "Abort this campaign. It will not resume sending.",
          () => stopCampaign(numId),
          "destructive",
        )} className="gap-1.5">
          <Square className="h-3.5 w-3.5" /> Cancel
        </Button>
        <Button size="sm" variant="outline" disabled={acting || c.status !== "draft"} onClick={() => navigate(`/campaigns/${c.id}/edit`)} className="gap-1.5">
          <Edit className="h-3.5 w-3.5" /> Edit
        </Button>
        <Button size="sm" variant="outline" disabled={acting} onClick={() => confirmAndExec(
          "Delete Campaign",
          "Move this campaign to trash. This does not permanently erase its records.",
          async () => { await softDeleteCampaign(numId); navigate("/campaigns"); },
          "destructive",
        )} className="gap-1.5">
          <Trash2 className="h-3.5 w-3.5" /> Delete
        </Button>
      </div>

      {/* ─── Readiness Check ─── */}
      {c.status === "draft" && (
        <div className="bg-muted/50 border rounded-lg p-4 space-y-2">
          <h3 className="text-sm font-medium flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-600" /> Campaign Readiness
          </h3>
          <div className="flex gap-4 text-sm">
            <span className={c.schedule ? "text-green-600" : "text-destructive"}>
              {c.schedule ? "✓" : "✗"} Schedule
            </span>
            <span className={(c.audience?.valid_count ?? 0) > 0 ? "text-green-600" : "text-destructive"}>
              {(c.audience?.valid_count ?? 0) > 0 ? "✓" : "✗"} Audience
              {c.audience && (
                <span className="ml-1 text-muted-foreground">
                  ({c.audience.valid_count.toLocaleString()} / {c.audience.total_count.toLocaleString()} valid)
                </span>
              )}
            </span>
            <span className={c.message_content ? "text-green-600" : "text-destructive"}>
              {c.message_content ? "✓" : "✗"} Message Content
            </span>
          </div>
        </div>
      )}

      {/* ─── Progress Section ─── */}
      {p && (
        <Section icon={BarChart3} title="Execution Progress">
          <div className="space-y-5">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Overall Progress</span>
                <span className="font-semibold">{Number(p.progress_percent ?? 0).toFixed(1)}%</span>
              </div>
              <Progress value={p.progress_percent ?? 0} className="h-3" />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
              <StatBox icon={Mail} label="Total" value={p.total_messages} color="text-foreground" />
              <StatBox icon={Send} label="Success Sent" value={p.sent_count} color="text-green-600" />
              <StatBox icon={XCircle} label="Failed Sent" value={p.failed_count} color="text-destructive" />
              <StatBox icon={CheckCircle2} label="Delivered" value={p.delivered_count} color="text-blue-600" />
              <StatBox icon={XCircle} label="Failed Delivery" value={p.failed_delivery_count} color="text-destructive" />
              <StatBox icon={Clock} label="Pending" value={p.pending_count} color="text-muted-foreground" />
            </div>

            {p.total_messages > 0 && (
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground border-t pt-3">
                <span>Delivery Rate: <strong className="text-foreground">{pct(p.delivered_count, p.total_messages)}</strong></span>
                <span>Send Rate: <strong className="text-foreground">{pct(p.sent_count, p.total_messages)}</strong></span>
                <span>Failure Rate: <strong className="text-foreground">{pct(p.failed_count, p.total_messages)}</strong></span>
              </div>
            )}

            {/* Batch summary */}
            {batches && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 border-t pt-4">
                <StatBox icon={Layers} label="Total Batches" value={batches.total_batches} color="text-foreground" />
                <StatBox icon={CheckCircle2} label="Completed" value={batches.completed_batches} color="text-green-600" />
                <StatBox icon={Loader2} label="In Progress" value={batches.in_progress_batches} color="text-yellow-600" />
                <StatBox icon={XCircle} label="Failed" value={batches.failed_batches} color="text-destructive" />
              </div>
            )}
          </div>
        </Section>
      )}

      {/* ─── Batches Table ─── */}
      {batchList.length > 0 && (
        <Section icon={Layers} title="Recent Batches">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Batch ID</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Success</TableHead>
                  <TableHead className="text-right">Failed</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {batchList.map((b: any, i: number) => (
                  <TableRow key={b.batch_id || i}>
                    <TableCell className="font-mono text-xs">{b.batch_id || `#${i + 1}`}</TableCell>
                    <TableCell className="text-right">{b.total_messages?.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-green-600">{b.success_count?.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-destructive">{b.failed_count?.toLocaleString()}</TableCell>
                    <TableCell>
                      <Badge className={`text-xs ${EXEC_STATUS_COLORS[b.status] || "bg-muted"}`}>
                        {b.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {b.created_at ? new Date(b.created_at).toLocaleString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}

      {/* ─── Campaign Info ─── */}
      <Section icon={Radio} title="Campaign Info">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <Field label="Campaign Name" value={c.name} />
          <Field label="Sender ID" value={c.sender_id || "—"} />
          <Field label="Owner Emails" value={c.owner_emails?.length ? c.owner_emails.join(", ") : "None configured"} />
          <Field label="Status" value={c.status} className="capitalize" />
          <Field label="Execution Status" value={c.execution_status_display || c.execution_status || "—"} />
          <div>
            <span className="text-muted-foreground text-xs uppercase tracking-wider">Channels</span>
            <div className="mt-1 flex gap-1 flex-wrap">
              {channels.map((ch) => (
                <Badge key={ch} variant="secondary" className="text-xs">
                  {CHANNEL_LABELS[ch as Channel] || ch}
                </Badge>
              ))}
            </div>
          </div>
          <Field label="Created" value={new Date(c.created_at).toLocaleString()} />
          <Field label="Last Updated" value={new Date(c.updated_at).toLocaleString()} />
          {(c as any).execution_started_at && (
            <Field label="Execution Started" value={new Date((c as any).execution_started_at).toLocaleString()} />
          )}
          <Field label="Total Processed" value={String(c.total_processed ?? 0)} />
          <Field label="Last Processed ID" value={String(c.last_processed_id ?? 0)} />
        </div>
      </Section>

      {/* ─── Schedule ─── */}
      {c.schedule && <ScheduleInfo schedule={c.schedule} />}

      {/* ─── Message Content ─── */}
      {messageContent && <MessageInfo mc={messageContent} />}

      {/* ─── Audience ─── */}
      {c.audience && <AudienceInfo audience={c.audience} />}

      <CampaignReports campaignId={numId} campaignName={c.name} ownerEmails={c.owner_emails ?? []} />

      {/* ─── Message Queue ─── */}
      {(messageContent || c.message_content_id) && <CampaignMessageQueue campaignId={numId} activationWorking={acting} />}

      {/* ─── Confirm Dialog ─── */}
      <AlertDialog open={!!confirmAction} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmAction?.label}</AlertDialogTitle>
            <AlertDialogDescription>{confirmAction?.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={acting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={acting}
              className={confirmAction?.variant === "destructive" ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" : ""}
              onClick={() => confirmAction && execAction(confirmAction.action, confirmAction.label)}
            >
              {acting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function AudienceInfo({ audience }: { audience: NonNullable<ApiCampaign["audience"]> }) {
    const total = audience.total_count ?? 0;
    const valid = audience.valid_count ?? 0;
    const invalid = audience.invalid_count ?? 0;
    const validPercentage = typeof audience.valid_percentage === "number"
      ? audience.valid_percentage
      : Number.parseFloat(String(audience.valid_percentage)) || 0;

    return (
      <Section icon={Users} title="Audience">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatBox icon={Users} label="Recipients" value={total} color="text-foreground" />
            <StatBox icon={CheckCircle2} label="Valid" value={valid} color="text-emerald-600" />
            <StatBox icon={XCircle} label="Invalid" value={invalid} color="text-destructive" />
            <div className="border px-4 py-3">
              <p className="text-xs text-muted-foreground">Valid rate</p>
              <p className="mt-1 text-xl font-semibold">{validPercentage.toFixed(1)}%</p>
            </div>
          </div>
          {audience.source_type && <p className="text-sm text-muted-foreground">Source: {audience.source_type.replaceAll("_", " ")}</p>}
          {audience.database_table && <p className="text-sm text-muted-foreground">Source table: {audience.database_table}</p>}
        </div>
      </Section>
    );
  }

/* ─── Sub-components ─── */

function StatBox({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: number; color: string }) {
  return (
    <div className="bg-card border rounded-sm px-4 py-3 space-y-1">
      <div className="flex items-center gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${color}`} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <p className={`text-xl font-semibold ${color}`}>{(value ?? 0).toLocaleString()}</p>
    </div>
  );
}

function ScheduleInfo({ schedule: s }: { schedule: NonNullable<ApiCampaign["schedule"]> }) {
  const isOneTime = s.schedule_type === "once";
  const tw = s.time_windows;
  const windows = Array.isArray(tw) ? tw : Object.values(tw || {});

  return (
    <Section icon={CalendarClock} title="Schedule">
      <div className="space-y-4 text-sm">
        <div className="flex items-center gap-3 pb-3 border-b">
          <span className="font-medium">
            {s.schedule_type_display || (isOneTime ? "One-time" : s.schedule_type)}
          </span>
          {s.schedule_summary && (
            <span className="text-muted-foreground">— {s.schedule_summary}</span>
          )}
          <Badge className={`ml-auto ${s.is_active ? "bg-green-100 text-green-800" : "bg-muted text-muted-foreground"}`}>
            {s.is_active ? "Active" : "Inactive"}
          </Badge>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Start Date" value={s.start_date} />
          {s.end_date && <Field label="End Date" value={s.end_date} />}
          <Field label="Timezone" value={s.timezone || "UTC"} />
          {s.next_run_date && <Field label="Next Run" value={s.next_run_date} />}
        </div>

        {windows.length > 0 && (
          <div>
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Delivery Windows</span>
            <div className="mt-2 space-y-1.5">
              {windows.map((w: any, i: number) => (
                <div key={i} className="flex items-center gap-3 bg-secondary/40 rounded-sm px-4 py-2">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium">{w.start || w}</span>
                  {w.end && <>
                    <span className="text-muted-foreground">→</span>
                    <span className="font-medium">{w.end}</span>
                  </>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}

function MessageInfo({ mc }: { mc: NonNullable<ApiCampaign["message_content"]> }) {
  const langs = Array.isArray(mc.languages_available)
    ? mc.languages_available
    : typeof mc.languages_available === "string"
      ? [mc.languages_available]
      : [];

  const preview = typeof mc.preview === "object" && mc.preview
    ? mc.preview
    : typeof mc.preview === "string"
      ? { language: mc.default_language, preview: mc.preview }
      : null;

  return (
    <Section icon={MessageSquare} title="Message Content">
      <div className="space-y-3 text-sm">
        <Field label="Default Language" value={LANGUAGE_LABELS[mc.default_language as keyof typeof LANGUAGE_LABELS] || mc.default_language} />
        <div>
          <span className="text-xs text-muted-foreground uppercase tracking-wider">Languages Available</span>
          <div className="mt-1 flex gap-1 flex-wrap">
            {langs.map((l) => (
              <Badge key={l} variant="secondary" className="text-xs">
                {LANGUAGE_LABELS[l as keyof typeof LANGUAGE_LABELS] || l}
              </Badge>
            ))}
          </div>
        </div>
        {preview && (
          <div>
            <span className="text-xs text-muted-foreground uppercase tracking-wider">Preview ({preview.language})</span>
            <p className="mt-1 bg-secondary/50 rounded-sm px-3 py-2 whitespace-pre-wrap">{preview.preview}</p>
          </div>
        )}
        {mc.content && typeof mc.content === "object" && Object.keys(mc.content).length > 0 && (
          <div className="space-y-2 border-t pt-3">
            {Object.entries(mc.content).map(([lang, text]) => (
              <div key={lang}>
                <span className="text-xs font-medium text-muted-foreground uppercase">
                  {LANGUAGE_LABELS[lang as keyof typeof LANGUAGE_LABELS] || lang}
                  {lang === mc.default_language && " (default)"}
                </span>
                <p className="mt-1 bg-secondary/50 rounded-sm px-3 py-2 whitespace-pre-wrap text-sm">{text as string}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function CampaignMessageQueue({ campaignId, activationWorking }: { campaignId: number; activationWorking: boolean }) {
  const queryClient = useQueryClient();
  const [confirmAction, setConfirmAction] = useState<"build" | "clear" | null>(null);
  const [working, setWorking] = useState(false);
  const statsQuery = useQuery({
    queryKey: ["campaign-message-stats", campaignId],
    queryFn: () => fetchCampaignMessageStats(campaignId),
    refetchInterval: 300000,
  });
  const messagesQuery = useQuery({
    queryKey: ["campaign-messages", campaignId],
    queryFn: () => fetchCampaignMessages(campaignId, 1, 5),
    refetchInterval: 300000,
  });
  const buildProgressQuery = useQuery({
    queryKey: ["campaign-message-build-progress", campaignId],
    queryFn: () => fetchCampaignMessageBuildProgress(campaignId),
    refetchInterval: (query) =>
      working || activationWorking || query.state.data?.data?.status === "RUNNING" ? 1000 : 300000,
  });
  const stats = statsQuery.data?.data;
  const messages = messagesQuery.data?.results ?? [];
  const messageBuild = buildProgressQuery.data?.data;

  async function runQueueAction() {
    if (!confirmAction) return;
    setWorking(true);
    try {
      if (confirmAction === "build") {
        const result = await buildCampaignMessages(campaignId);
        toast.success(`${result.data.built} messages built for this campaign`);
      } else {
        const result = await clearCampaignMessages(campaignId);
        toast.success(result.message);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["campaign-message-stats", campaignId] }),
        queryClient.invalidateQueries({ queryKey: ["campaign-messages", campaignId] }),
        queryClient.invalidateQueries({ queryKey: ["campaign-message-build-progress", campaignId] }),
      ]);
    } catch (error: any) {
      toast.error(error.message || "Unable to update the message queue");
    } finally {
      setWorking(false);
      setConfirmAction(null);
    }
  }

  return (
    <Section icon={Layers} title="Message Queue">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 flex-1">
            <StatBox icon={Mail} label="Queued" value={stats?.total ?? 0} color="text-foreground" />
            <StatBox icon={Clock} label="Pending" value={stats?.pending ?? 0} color="text-muted-foreground" />
            <StatBox icon={Loader2} label="Processing" value={stats?.processing ?? 0} color="text-yellow-600" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={working || activationWorking || messageBuild?.status === "RUNNING"} onClick={() => setConfirmAction("build")}>
              <Layers className="h-3.5 w-3.5 mr-1.5" />
              {stats?.total ? "Rebuild Queue" : "Build Queue"}
            </Button>
            {Boolean(stats?.total) && (
              <Button size="sm" variant="destructive" disabled={working} onClick={() => setConfirmAction("clear")}>
                <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Clear
              </Button>
            )}
          </div>
        </div>

        {messageBuild && (
          <div className="space-y-2 border-t pt-4" role="status" aria-live="polite">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">
                {messageBuild.status === "RUNNING" ? "Building message objects" : `Message build ${messageBuild.status.toLowerCase()}`}
              </span>
              <span className="text-muted-foreground">
                {messageBuild.total ? `${Math.round(messageBuild.percent)}%` : messageBuild.phase}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-secondary"
              role="progressbar"
              aria-label="Message object build progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={messageBuild.total ? Math.round(messageBuild.percent) : undefined}
            >
              <div
                className={`h-full bg-primary transition-all ${messageBuild.total ? "" : "w-1/3 animate-progress-indeterminate"}`}
                style={messageBuild.total ? { width: `${Math.min(messageBuild.percent, 100)}%` } : undefined}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {messageBuild.phase}: {messageBuild.processed.toLocaleString()} / {messageBuild.total.toLocaleString()} audience rows processed; {messageBuild.built.toLocaleString()} messages committed to the database
            </p>
            {messageBuild.error && <p className="text-xs text-destructive">{messageBuild.error}</p>}
          </div>
        )}

        {messages.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Recipient</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Message</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Batch</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {messages.map((message: CampaignMessageQueueItem) => (
                  <TableRow key={message.id}>
                    <TableCell className="font-mono text-xs">{message.recipient}</TableCell>
                    <TableCell>{message.language_code ? LANGUAGE_LABELS[message.language_code as keyof typeof LANGUAGE_LABELS] || message.language_code : "—"}</TableCell>
                    <TableCell className="max-w-[320px] truncate">{message.message_content}</TableCell>
                    <TableCell><Badge variant="outline">{message.status}</Badge></TableCell>
                    <TableCell className="font-mono text-xs">{message.batch_id}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No message rows have been built for this campaign.</p>
        )}
        {(stats?.total ?? 0) > 0 && (
          <div className="flex justify-end border-t pt-3">
            <Link to={`/campaigns/${campaignId}/messages`} className="text-sm font-medium text-primary hover:underline">
              View all {stats?.total} messages
            </Link>
          </div>
        )}
        {stats?.language_breakdown && Object.keys(stats.language_breakdown).length > 0 && (
          <div className="flex flex-wrap gap-2 border-t pt-3 text-xs text-muted-foreground">
            {Object.entries(stats.language_breakdown).map(([language, count]) => (
              <span key={language}>{LANGUAGE_LABELS[language as keyof typeof LANGUAGE_LABELS] || language}: {count}</span>
            ))}
          </div>
        )}
      </div>

      <AlertDialog open={Boolean(confirmAction)} onOpenChange={(open) => !open && setConfirmAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmAction === "clear" ? "Clear Message Queue" : "Build Message Queue"}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === "clear"
                ? "This permanently removes all queued message rows for this campaign."
                : "This builds messages from the linked campaign content and audience, replacing any existing queue rows."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={working}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={working} onClick={() => void runQueueAction()}>
              {working ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Section>
  );
}
