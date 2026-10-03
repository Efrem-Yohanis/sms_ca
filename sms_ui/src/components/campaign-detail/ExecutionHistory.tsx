import { useState } from "react";
import { History, ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Section } from "./Section";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import type { ExecutionRound } from "@/types/campaign";

const ROUND_STATUS_STYLES: Record<string, { badge: string; icon: string }> = {
  completed: { badge: "bg-blue-100 text-blue-800", icon: "✅" },
  partial: { badge: "bg-yellow-100 text-yellow-800", icon: "⚠️" },
  failed: { badge: "bg-destructive/10 text-destructive", icon: "❌" },
  pending: { badge: "bg-muted text-muted-foreground", icon: "⏳" },
  active: { badge: "bg-green-100 text-green-800", icon: "🔄" },
};

function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return `${h}h ${m}m`;
}

interface ExecutionHistoryProps {
  rounds: ExecutionRound[];
  isOneTime: boolean;
}

export function ExecutionHistory({ rounds, isOneTime }: ExecutionHistoryProps) {
  const [open, setOpen] = useState(false);

  if (!rounds || rounds.length === 0) return null;

  return (
    <Section
      icon={History}
      title="Execution History"
      action={
        <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} className="gap-1 text-xs">
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          {open ? "Collapse" : `Show ${rounds.length} ${isOneTime ? "execution" : "rounds"}`}
        </Button>
      }
    >
      {open ? (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16">Round</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Window</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Queued</TableHead>
                <TableHead className="text-right">Sent</TableHead>
                <TableHead className="text-right">Delivered</TableHead>
                <TableHead className="text-right">Failed (Send)</TableHead>
                <TableHead className="text-right">Failed (Delivery)</TableHead>
                <TableHead>Started At</TableHead>
                <TableHead>Completed At</TableHead>
                <TableHead>Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rounds.map((r) => {
                const style = ROUND_STATUS_STYLES[r.status] || ROUND_STATUS_STYLES.pending;
                return (
                  <TableRow key={r.round}>
                    <TableCell className="font-medium text-muted-foreground">#{r.round}</TableCell>
                    <TableCell>{new Date(r.date).toLocaleDateString()}</TableCell>
                    <TableCell className="text-muted-foreground">{r.window}</TableCell>
                    <TableCell>
                      <Badge className={`text-xs ${style.badge}`}>
                        {style.icon} {r.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">{r.queued.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-green-600">{r.sent.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-blue-600">{r.delivered.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-destructive">{r.failed_send.toLocaleString()}</TableCell>
                    <TableCell className="text-right text-destructive">{r.failed_delivery.toLocaleString()}</TableCell>
                    <TableCell className="text-xs">{r.started_at ? new Date(r.started_at).toLocaleString() : "—"}</TableCell>
                    <TableCell className="text-xs">{r.completed_at ? new Date(r.completed_at).toLocaleString() : "—"}</TableCell>
                    <TableCell className="text-xs font-medium">{formatDuration(r.started_at, r.completed_at)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {rounds.length} execution {isOneTime ? "record" : "rounds"}. Click to expand.
        </p>
      )}
    </Section>
  );
}
