import { useEffect, useSyncExternalStore } from "react";
import { toast } from "sonner";
import { schedulerApi } from "@/lib/task-scheduler/api";

export type TaskType = "Python" | "SQL";
export type ScheduleStatus = "Active" | "Paused" | "Failed" | "Pending" | "Draft";
export type RunStatus = "Success" | "Failed" | "Running" | "Queued";

export interface Schedule {
  id: string;
  name: string;
  owner: string;
  ownerEmail: string;
  acceptNotifications: boolean;
  scheduleType: "Cron" | "Interval" | "Manual";
  cron: string;
  intervalValue: number;
  intervalUnit: "minutes" | "hours";
  timezone: string;
  daysOfWeek: number[];
  windowStart: string | null;
  windowEnd: string | null;
  excludedDates: string[];
  effectiveCron?: string;
  startDate?: string | null;
  endDate?: string | null;
  type: TaskType;
  code: string;
  connection?: string;
  retries: number;
  retryDelay: number;
  status: ScheduleStatus;
  airflowSyncedAt?: string | null;
  airflowSyncError?: string;
  lastRun?: number;
  lastStatus?: RunStatus;
  nextRun?: number;
}

export interface Run {
  id: string;
  scheduleId: string;
  start: number;
  end?: number;
  status: RunStatus;
  trigger: "Scheduled" | "Manual";
  logs: { ts: number; level: "INFO" | "WARN" | "ERROR"; msg: string }[];
}

export const CONNECTIONS = ["warehouse_pg", "analytics_snowflake", "crm_mysql", "reporting_mssql"];

interface State {
  schedules: Schedule[];
  runs: Run[];
  loaded: boolean;
}

let state: State = { schedules: [], runs: [], loaded: false };
let loading: Promise<void> | null = null;
let loaded = false;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

function update(fn: (current: State) => State) {
  state = fn(state);
  notify();
}

async function loadScheduler(force = false) {
  if (loading) return loading;
  if (!force && loaded) return;

  loading = Promise.all([schedulerApi.listSchedules(), schedulerApi.listRuns()])
    .then(([schedules, runs]) => {
      state = { schedules, runs, loaded: true };
      loaded = true;
      notify();
    })
    .catch((error: unknown) => {
      console.error("Unable to load schedules from the scheduler API", error);
      toast.error(error instanceof Error ? error.message : "Unable to load schedules");
    })
    .finally(() => {
      loading = null;
    });
  return loading;
}

export function useScheduler<T>(selector: (current: State) => T): T {
  useEffect(() => {
    void loadScheduler();
  }, []);
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => selector(state),
    () => selector(state),
  );
}

export const actions = {
  async save(schedule: Schedule, isNew: boolean) {
    const saved = await schedulerApi.saveSchedule(schedule, isNew);
    loaded = false;
    update((current) => ({
      ...current,
      schedules: isNew
        ? [saved, ...current.schedules]
        : current.schedules.map((item) => (item.id === saved.id ? saved : item)),
    }));
    return saved;
  },
  async remove(ids: string[]) {
    await Promise.all(ids.map((id) => schedulerApi.deleteSchedule(id)));
    update((current) => ({
      ...current,
      schedules: current.schedules.filter((schedule) => !ids.includes(schedule.id)),
      runs: current.runs.filter((run) => !ids.includes(run.scheduleId)),
    }));
  },
  async setPaused(ids: string[], paused: boolean) {
    const updated = await Promise.all(ids.map((id) => schedulerApi.setPaused(id, paused)));
    update((current) => ({
      ...current,
      schedules: current.schedules.map(
        (schedule) => updated.find((item) => item.id === schedule.id) ?? schedule,
      ),
    }));
  },
  async runNow(id: string) {
    const run = await schedulerApi.runNow(id);
    update((current) => ({
      ...current,
      runs: [run, ...current.runs.filter((item) => item.id !== run.id)],
      schedules: current.schedules.map((schedule) =>
        schedule.id === id ? { ...schedule, lastRun: run.start, lastStatus: run.status } : schedule,
      ),
    }));
    return run;
  },
  async refresh() {
    await loadScheduler(true);
  },
  async loadRuns(scheduleId?: string) {
    const runs = await schedulerApi.listRuns(scheduleId);
    update((current) => ({
      ...current,
      runs: scheduleId
        ? [...runs, ...current.runs.filter((run) => run.scheduleId !== scheduleId)]
        : runs,
    }));
    return runs;
  },
  updateRunLogs(scheduleId: string, runId: string, logs: Run["logs"]) {
    update((current) => ({
      ...current,
      runs: current.runs.map((run) =>
        run.scheduleId === scheduleId && run.id === runId ? { ...run, logs } : run,
      ),
    }));
  },
};

export function newSchedule(): Schedule {
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`;
  return {
    id: `s${id}`,
    name: "",
    owner: "",
    ownerEmail: "",
    acceptNotifications: true,
    scheduleType: "Cron",
    cron: "0 2 * * *",
    intervalValue: 15,
    intervalUnit: "minutes",
    timezone: "Africa/Nairobi",
    daysOfWeek: [],
    windowStart: null,
    windowEnd: null,
    excludedDates: [],
    type: "Python",
    code: "",
    connection: "",
    retries: 2,
    retryDelay: 300,
    status: "Draft",
  };
}

const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export function scheduleToHuman(
  schedule: Pick<Schedule, "scheduleType" | "cron" | "intervalValue" | "intervalUnit">,
): string {
  if (schedule.scheduleType === "Manual") return "Manual only";
  if (schedule.scheduleType === "Interval") {
    const unit =
      schedule.intervalValue === 1 ? schedule.intervalUnit.slice(0, -1) : schedule.intervalUnit;
    return `Every ${schedule.intervalValue} ${unit}`;
  }
  return cronToHuman(schedule.cron);
}

export function cronToHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "Invalid cron";
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  const time = () => `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
  if (minute.startsWith("*/") && hour === "*") return `Every ${minute.slice(2)} minutes`;
  if (minute === "*" && hour === "*") return "Every minute";
  if (/^\d+$/.test(minute) && hour === "*") return `Hourly at :${minute.padStart(2, "0")}`;
  if (/^\d+$/.test(minute) && hour.startsWith("*/")) return `Every ${hour.slice(2)} hours`;
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour)) {
    if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") return `Daily at ${time()}`;
    if (dayOfMonth === "*" && month === "*" && /^\d$/.test(dayOfWeek))
      return `Weekly on ${DAYS[+dayOfWeek]} at ${time()}`;
    if (/^\d+$/.test(dayOfMonth) && month === "*" && dayOfWeek === "*")
      return `Monthly on day ${dayOfMonth} at ${time()}`;
  }
  return "Custom schedule";
}

export function fmtDuration(ms: number) {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function fmtTime(ts?: number) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
