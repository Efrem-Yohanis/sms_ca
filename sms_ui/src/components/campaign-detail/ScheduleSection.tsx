import { CalendarClock, Calendar, Repeat, Clock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Section, Field } from "./Section";
import type { Schedule } from "@/types/campaign";
import {
  SCHEDULE_TYPE_LABELS,
  DAY_LABELS,
  SCHEDULE_STATUS_LABELS,
  WINDOW_STATUS_LABELS,
} from "@/types/campaign";

const SCHEDULE_STATUS_COLORS: Record<string, string> = {
  pending: "bg-muted text-muted-foreground",
  running: "bg-green-100 text-green-800",
  stop: "bg-yellow-100 text-yellow-800",
  completed: "bg-blue-100 text-blue-800",
};

export function ScheduleSection({ schedule }: { schedule: Schedule }) {
  const s = schedule;
  const isOneTime = s.schedule_type === "once";

  return (
    <Section icon={CalendarClock} title="Schedule">
      <div className="space-y-5">
        {/* Schedule Type Header */}
        <div className="flex items-center gap-3 pb-3 border-b">
          {isOneTime ? (
            <div className="flex items-center gap-2 text-sm">
              <Calendar className="h-4 w-4 text-primary" />
              <span className="font-medium">One-time Execution</span>
              <Badge variant="outline" className="text-xs">Single run</Badge>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm">
              <Repeat className="h-4 w-4 text-primary" />
              <span className="font-medium">{SCHEDULE_TYPE_LABELS[s.schedule_type]} Campaign</span>
              <Badge variant="outline" className="text-xs capitalize">
                {SCHEDULE_TYPE_LABELS[s.schedule_type]} cycle
              </Badge>
            </div>
          )}
          <Badge className={`ml-auto ${SCHEDULE_STATUS_COLORS[s.status]}`}>
            {SCHEDULE_STATUS_LABELS[s.status]}
          </Badge>
        </div>

        {/* Dates */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <Field label="Start Date" value={s.start_date} />
          {s.end_date && (
            <Field label="End Date" value={s.end_date} />
          )}
          <Field label="Timezone" value={s.timezone} />
        </div>

        {/* Recurring details */}
        {!isOneTime && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <Field label="Schedule Type" value={SCHEDULE_TYPE_LABELS[s.schedule_type]} />
              {s.run_days && s.run_days.length > 0 && (
                <div>
                  <span className="text-muted-foreground text-sm">Run Days</span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {s.run_days.map((d) => (
                      <Badge key={d} variant="secondary" className="text-xs">
                        {DAY_LABELS[d] || `Day ${d}`}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* Time Windows */}
        <div>
          <span className="text-sm text-muted-foreground flex items-center gap-1.5 mb-2">
            <Clock className="h-3.5 w-3.5" /> Delivery Windows
          </span>
          <div className="space-y-2">
            {s.time_windows.map((tw, i) => (
              <div
                key={i}
                className="flex items-center gap-3 bg-secondary/40 rounded-sm px-4 py-2.5 text-sm"
              >
                <Clock className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{tw.start}</span>
                <span className="text-muted-foreground">→</span>
                <span className="font-medium">{tw.end}</span>
                <Badge
                  variant="outline"
                  className="ml-auto text-xs"
                >
                  {WINDOW_STATUS_LABELS[s.status === "running" ? "active" : s.status === "completed" ? "completed" : "pending"]}
                </Badge>
              </div>
            ))}
          </div>
        </div>

        {/* Next Run Info */}
        {s.status !== "completed" && (
          <div className="bg-primary/5 border border-primary/20 rounded-sm px-4 py-3">
            <span className="text-xs text-muted-foreground">
              {isOneTime ? "Scheduled Execution" : "Next Scheduled Run"}
            </span>
            <p className="text-sm font-medium mt-0.5">
              {s.start_date}
              {s.time_windows[0] && ` at ${s.time_windows[0].start}`}
            </p>
          </div>
        )}
      </div>
    </Section>
  );
}
