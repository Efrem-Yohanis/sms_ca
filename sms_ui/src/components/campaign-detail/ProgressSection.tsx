import { useState, useMemo } from "react";
import { BarChart3, Download, Mail, CheckCircle2, Send, XCircle, Clock, TrendingUp } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Section } from "./Section";
import type { CampaignProgress, ExecutionRound, Schedule } from "@/types/campaign";
import { EXECUTION_STATUS_LABELS, SCHEDULE_TYPE_LABELS } from "@/types/campaign";

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "bg-green-100 text-green-800",
  COMPLETED: "bg-blue-100 text-blue-800",
  STOPPED: "bg-yellow-100 text-yellow-800",
  FAILED: "bg-destructive/10 text-destructive",
  PENDING: "bg-muted text-muted-foreground",
  PROCESSING: "bg-green-100 text-green-800",
  PAUSED: "bg-yellow-100 text-yellow-800",
};

const ROUND_STATUS_ICONS: Record<string, string> = {
  completed: "✅",
  partial: "⚠️",
  failed: "❌",
  pending: "⏳",
  active: "🔄",
};

function formatDuration(startStr: string, endStr: string | null): string {
  if (!startStr || !endStr) return "—";
  const ms = new Date(endStr).getTime() - new Date(startStr).getTime();
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  return `${hours}h ${minutes}m`;
}

function pct(value: number, total: number): string {
  if (total === 0) return "0%";
  return `${((value / total) * 100).toFixed(1)}%`;
}

function downloadCSV(filename: string, headers: string[], rows: string[][]) {
  const csv = [headers.join(","), ...rows.map(r => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: number;
  total: number;
  color: string;
  onDownload: () => void;
}

function StatCard({ icon: Icon, label, value, total, color, onDownload }: StatCardProps) {
  return (
    <div className="bg-card border rounded-sm px-4 py-3 space-y-1">
      <div className="flex items-center gap-1.5">
        <Icon className={`h-3.5 w-3.5 ${color}`} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <p className={`text-xl font-semibold ${color}`}>{value.toLocaleString()}</p>
      <p className="text-xs text-muted-foreground">{pct(value, total)}</p>
      <Button variant="ghost" size="sm" className="h-6 px-2 text-xs gap-1 text-muted-foreground" onClick={onDownload}>
        <Download className="h-3 w-3" /> CSV
      </Button>
    </div>
  );
}

interface ProgressSectionProps {
  progress: CampaignProgress;
  schedule: Schedule;
  rounds?: ExecutionRound[];
  campaignName: string;
  senderId: string;
}

export function ProgressSection({ progress, schedule, rounds, campaignName, senderId }: ProgressSectionProps) {
  const isRecurring = schedule.schedule_type !== "once";
  const [selectedRound, setSelectedRound] = useState<string>("current");

  const displayData = useMemo(() => {
    if (!isRecurring || selectedRound === "current" || !rounds) {
      return progress;
    }
    if (selectedRound === "all") {
      const agg = rounds.reduce(
        (acc, r) => ({
          total_messages: acc.total_messages + r.queued,
          sent_count: acc.sent_count + r.sent,
          delivered_count: acc.delivered_count + r.delivered,
          failed_count: acc.failed_count + r.failed_send,
          failed_delivery_count: acc.failed_delivery_count + r.failed_delivery,
          pending_count: acc.pending_count + (r.queued - r.sent - r.failed_send),
        }),
        { total_messages: 0, sent_count: 0, delivered_count: 0, failed_count: 0, failed_delivery_count: 0, pending_count: 0 }
      );
      const completed = agg.sent_count + agg.failed_count;
      return {
        ...agg,
        progress_percent: agg.total_messages > 0 ? (completed / agg.total_messages) * 100 : 0,
        status: progress.status,
        started_at: rounds[0]?.started_at || progress.started_at,
        completed_at: rounds[rounds.length - 1]?.completed_at || null,
      };
    }
    const roundNum = parseInt(selectedRound);
    const round = rounds.find(r => r.round === roundNum);
    if (!round) return progress;
    const completed = round.sent + round.failed_send;
    return {
      total_messages: round.queued,
      sent_count: round.sent,
      delivered_count: round.delivered,
      failed_count: round.failed_send,
      failed_delivery_count: round.failed_delivery,
      pending_count: round.queued - completed,
      progress_percent: round.queued > 0 ? (completed / round.queued) * 100 : 0,
      status: round.status === "completed" ? "COMPLETED" : round.status === "failed" ? "FAILED" : round.status === "active" ? "ACTIVE" : "PENDING",
      started_at: round.started_at || "",
      completed_at: round.completed_at,
    };
  }, [isRecurring, selectedRound, rounds, progress]);

  const selectedRoundData = useMemo(() => {
    if (!rounds || selectedRound === "current" || selectedRound === "all") return null;
    return rounds.find(r => r.round === parseInt(selectedRound)) || null;
  }, [rounds, selectedRound]);

  const handleDownload = (type: string) => {
    const roundLabel = selectedRoundData ? `_round${selectedRoundData.round}` : "";
    const headers = ["Message ID", "Phone Number", "Channel", "Sender ID", "Timestamp", "Round"];
    const mockRow = [`msg_${Math.random().toString(36).slice(2, 8)}`, "+251911234567", "sms", senderId, new Date().toISOString(), selectedRoundData?.round?.toString() || "1"];
    downloadCSV(`${campaignName}_${type}${roundLabel}.csv`, headers, [mockRow]);
  };

  const d = displayData;
  const tw = schedule.time_windows?.[0];

  return (
    <Section icon={BarChart3} title="Execution Progress">
      <div className="space-y-5">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Campaign Type:</span>
            <Badge variant="outline">
              {isRecurring ? `🔄 ${SCHEDULE_TYPE_LABELS[schedule.schedule_type]}` : "📅 One-time"}
            </Badge>
          </div>

          {isRecurring && rounds && rounds.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Select Round:</span>
              <Select value={selectedRound} onValueChange={setSelectedRound}>
                <SelectTrigger className="w-[260px] h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="current">Current Progress</SelectItem>
                  {rounds.map(r => (
                    <SelectItem key={r.round} value={String(r.round)}>
                      {ROUND_STATUS_ICONS[r.status]} Round #{r.round} - {new Date(r.date).toLocaleDateString()} ({r.status})
                    </SelectItem>
                  ))}
                  <SelectItem value="all">📊 All Rounds (Summary)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {selectedRoundData && (
          <div className="bg-secondary/50 border rounded-sm px-4 py-2 text-sm flex items-center gap-3 flex-wrap">
            <span className="font-medium">Round #{selectedRoundData.round}</span>
            <span className="text-muted-foreground">{new Date(selectedRoundData.date).toLocaleDateString()}</span>
            <span className="text-muted-foreground">|</span>
            <span className="text-muted-foreground">Window: {selectedRoundData.window}</span>
            <span className="text-muted-foreground">|</span>
            <Badge className={`text-xs ${STATUS_COLORS[d.status] || "bg-muted"}`}>
              {ROUND_STATUS_ICONS[selectedRoundData.status]} {selectedRoundData.status}
            </Badge>
          </div>
        )}

        {selectedRound === "all" && rounds && (
          <div className="bg-secondary/50 border rounded-sm px-4 py-2 text-sm flex items-center gap-4 flex-wrap">
            <span className="font-medium">All Rounds Summary</span>
            <span className="text-muted-foreground">
              Total: {rounds.length} |
              Completed: {rounds.filter(r => r.status === "completed").length} |
              Partial: {rounds.filter(r => r.status === "partial").length} |
              Failed: {rounds.filter(r => r.status === "failed").length} |
              Pending: {rounds.filter(r => r.status === "pending").length}
            </span>
          </div>
        )}

        {!isRecurring && (
          <div className="text-sm text-muted-foreground">
            Execution Date: {schedule.start_date} | Window: {tw ? `${tw.start} – ${tw.end}` : "—"}
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Overall Progress</span>
            <div className="flex items-center gap-2">
              <Badge className={STATUS_COLORS[d.status] || "bg-muted text-muted-foreground"}>
                {EXECUTION_STATUS_LABELS[d.status] || d.status}
              </Badge>
              <span className="font-medium">{d.progress_percent.toFixed(1)}%</span>
            </div>
          </div>
          <Progress value={d.progress_percent} className="h-3" />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <StatCard icon={Mail} label="Total Messages" value={d.total_messages} total={d.total_messages} color="text-foreground" onDownload={() => handleDownload("total")} />
          <StatCard icon={Send} label="Sent" value={d.sent_count} total={d.total_messages} color="text-green-600" onDownload={() => handleDownload("sent")} />
          <StatCard icon={CheckCircle2} label="Delivered" value={d.delivered_count} total={d.total_messages} color="text-blue-600" onDownload={() => handleDownload("delivered")} />
          <StatCard icon={XCircle} label="Failed (Send)" value={d.failed_count} total={d.total_messages} color="text-destructive" onDownload={() => handleDownload("failed_send")} />
          <StatCard icon={Clock} label="Pending" value={d.pending_count} total={d.total_messages} color="text-muted-foreground" onDownload={() => handleDownload("pending")} />
        </div>

        {d.failed_delivery_count > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">📊 Failed Delivery:</span>
            <span className="font-medium text-destructive">
              {d.failed_delivery_count.toLocaleString()} ({pct(d.failed_delivery_count, d.total_messages)})
            </span>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs gap-1 text-muted-foreground" onClick={() => handleDownload("failed_delivery")}>
              <Download className="h-3 w-3" /> CSV
            </Button>
          </div>
        )}

        <div className="flex flex-wrap gap-4 text-xs text-muted-foreground pt-2 border-t">
          {d.started_at && (
            <span>⏱️ Started: <strong className="text-foreground">{new Date(d.started_at).toLocaleString()}</strong></span>
          )}
          {d.completed_at && (
            <span>🏁 Completed: <strong className="text-foreground">{new Date(d.completed_at).toLocaleString()}</strong></span>
          )}
          {d.started_at && d.completed_at && (
            <span>⏱️ Duration: <strong className="text-foreground">{formatDuration(d.started_at, d.completed_at)}</strong></span>
          )}
        </div>

        {d.sent_count > 0 && (
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <TrendingUp className="h-3.5 w-3.5" />
            <span>Success Rate: <strong className="text-foreground">{pct(d.delivered_count, d.total_messages)}</strong></span>
            <span>|</span>
            <span>Send Rate: <strong className="text-foreground">{pct(d.sent_count, d.total_messages)}</strong></span>
            <span>|</span>
            <span>Delivery Rate: <strong className="text-foreground">{pct(d.delivered_count, d.sent_count)}</strong></span>
          </div>
        )}
      </div>
    </Section>
  );
}
