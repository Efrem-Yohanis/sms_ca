import { cn } from "@/lib/utils";

const styles: Record<string, string> = {
  Success: "bg-emerald-500/15 text-emerald-700",
  Active: "bg-emerald-500/15 text-emerald-700",
  Failed: "bg-destructive/15 text-destructive",
  Running: "bg-blue-500/15 text-blue-700",
  Queued: "bg-amber-500/20 text-amber-800",
  Pending: "bg-amber-500/20 text-amber-800",
  Paused: "bg-muted text-muted-foreground",
  Draft: "bg-secondary text-secondary-foreground",
};
const dots: Record<string, string> = {
  Success: "bg-emerald-600", Active: "bg-emerald-600", Failed: "bg-destructive", Running: "bg-blue-600 animate-pulse",
  Queued: "bg-amber-600", Pending: "bg-amber-600", Paused: "bg-muted-foreground", Draft: "bg-muted-foreground",
};

export function StatusBadge({ status }: { status?: string }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", styles[status])}>
      <span className={cn("h-2 w-2 rounded-full", dots[status])} aria-hidden />
      {status}
    </span>
  );
}
