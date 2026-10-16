import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ScheduleWizard } from "@/components/task-scheduler/schedule-wizard";
import {
  SchedulesPage,
  UpcomingSchedulesPage,
} from "@/components/task-scheduler/schedules-page";
import { RunHistory } from "@/components/task-scheduler/run-history";
import {
  newSchedule,
  useScheduler,
} from "@/lib/task-scheduler/store";

export default function TaskSchedulerPage() {
  return <SchedulesPage />;
}

export function TaskSchedulerUpcomingPage() {
  return <UpcomingSchedulesPage />;
}

export function TaskSchedulerCreatePage() {
  const [initial] = useState(newSchedule);
  return <ScheduleWizard initial={initial} isNew />;
}

export function TaskSchedulerEditPage() {
  const { id = "" } = useParams();
  const schedule = useScheduler((state) => state.schedules.find((item) => item.id === id));
  const loaded = useScheduler((state) => state.loaded);
  if (!schedule && !loaded) {
    return <div className="py-20 text-center text-muted-foreground">Loading task schedule…</div>;
  }
  if (!schedule) return <TaskScheduleNotFound />;
  return <ScheduleWizard key={id} initial={schedule} isNew={false} />;
}

export function TaskSchedulerRunsPage() {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Run History</h1>
        <p className="text-sm text-muted-foreground">All runs across your task schedules. Select a run to view its logs.</p>
      </div>
      <RunHistory />
    </div>
  );
}

export function TaskScheduleNotFound() {
  return (
    <div className="py-20 text-center">
      <p className="text-lg font-medium">Task schedule not found</p>
      <Button asChild variant="outline" className="mt-4">
        <Link to="/task-scheduler">Back to Task Scheduler</Link>
      </Button>
    </div>
  );
}
