import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  actions,
  CONNECTIONS,
  scheduleToHuman,
  useScheduler,
  type Schedule,
} from "@/lib/task-scheduler/store";

const STEPS = ["Basic Info", "Schedule", "Task"];
const TIMEZONES = ["UTC", "Africa/Nairobi", "Europe/London", "America/New_York", "Asia/Singapore"];
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const RUN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const CRON_FIELDS = ["Minute", "Hour", "Day", "Month", "Weekday"];
type CronPreset = "Daily" | "Weekly" | "Monthly" | "Custom cron";

function initialCronPreset(cron: string): CronPreset {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return "Custom cron";
  const [, , day, month, weekday] = parts;
  const [minute, hour] = parts;
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && day === "*" && month === "*" && weekday === "*")
    return "Daily";
  if (
    /^\d+$/.test(minute) &&
    /^\d+$/.test(hour) &&
    day === "*" &&
    month === "*" &&
    /^\d$/.test(weekday)
  )
    return "Weekly";
  if (
    /^\d+$/.test(minute) &&
    /^\d+$/.test(hour) &&
    /^\d+$/.test(day) &&
    month === "*" &&
    weekday === "*"
  )
    return "Monthly";
  return "Custom cron";
}

function validEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function ScheduleWizard({ initial, isNew }: { initial: Schedule; isNew: boolean }) {
  const navigate = useNavigate();
  const existing = useScheduler((state) => state.schedules);
  const [schedule, setSchedule] = useState<Schedule>(initial);
  const [step, setStep] = useState(0);
  const [cronPreset, setCronPreset] = useState<CronPreset>(() => initialCronPreset(initial.cron));
  const [time, setTime] = useState(() => {
    const [minute = "0", hour = "2"] = initial.cron.split(/\s+/);
    return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
  });
  const [weekday, setWeekday] = useState(() => {
    const day = Number(initial.cron.trim().split(/\s+/)[4]);
    return String(Number.isInteger(day) && day >= 0 && day <= 6 ? day : 1);
  });
  const [monthDay, setMonthDay] = useState(() => {
    const day = Number(initial.cron.trim().split(/\s+/)[2]);
    return String(Number.isInteger(day) && day >= 1 && day <= 31 ? day : 1);
  });
  const [excludedDateInput, setExcludedDateInput] = useState("");
  const [codeSource, setCodeSource] = useState<"upload" | "type">("type");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const cronParts = schedule.cron.trim().split(/\s+/);
  const windowStart = schedule.windowStart?.slice(0, 5) ?? "";
  const windowEnd = schedule.windowEnd?.slice(0, 5) ?? "";
  const scheduleConstraintError =
    schedule.scheduleType !== "Cron" &&
    (schedule.daysOfWeek.length > 0 || Boolean(schedule.windowStart) || Boolean(schedule.windowEnd))
      ? "Weekday and time-window filters are only supported for Cron schedules"
      : Boolean(windowStart) !== Boolean(windowEnd)
        ? "Provide both window start and end times, or neither"
        : windowStart && windowEnd && windowEnd <= windowStart
          ? "Window end must be later than window start; overnight windows are not supported"
          : null;
  const nameTaken = existing.some(
    (item) =>
      item.id !== schedule.id && item.name.toLowerCase() === schedule.name.trim().toLowerCase(),
  );
  const errors: Record<number, string | null> = {
    0: !schedule.name.trim()
      ? "Schedule name is required"
      : nameTaken
        ? "Schedule name must be unique"
        : !schedule.owner.trim()
          ? "Owner name is required"
          : !validEmail(schedule.ownerEmail)
            ? "Enter a valid owner email"
            : null,
    1:
      schedule.scheduleType === "Cron" &&
      (cronParts.length !== 5 || cronParts.some((part) => !part))
        ? "Cron expression needs 5 fields"
        : (scheduleConstraintError ??
          (schedule.scheduleType === "Interval" &&
          (!Number.isInteger(schedule.intervalValue) || schedule.intervalValue < 1)
            ? "Interval must be at least 1"
            : null)),
    2: !schedule.code.trim()
      ? "Upload or enter a script"
      : schedule.type === "SQL" && !schedule.connection
        ? "Select a connection"
        : null,
  };
  const update = <K extends keyof Schedule>(key: K, value: Schedule[K]) =>
    setSchedule((current) => ({ ...current, [key]: value }));

  const applyPreset = (
    preset: CronPreset,
    nextTime = time,
    nextWeekday = weekday,
    nextMonthDay = monthDay,
  ) => {
    setCronPreset(preset);
    if (preset === "Custom cron") return;
    const [hour, minute] = nextTime.split(":");
    const expression =
      preset === "Daily"
        ? `${minute} ${hour} * * *`
        : preset === "Weekly"
          ? `${minute} ${hour} * * ${nextWeekday}`
          : `${minute} ${hour} ${nextMonthDay} * *`;
    if (preset === "Weekly") update("daysOfWeek", []);
    update("cron", expression);
  };

  const toggleRunDay = (day: number) => {
    const days = schedule.daysOfWeek.includes(day)
      ? schedule.daysOfWeek.filter((item) => item !== day)
      : [...schedule.daysOfWeek, day].sort((a, b) => a - b);
    update("daysOfWeek", days);
  };

  const addExcludedDate = () => {
    if (!excludedDateInput || schedule.excludedDates.includes(excludedDateInput)) return;
    update("excludedDates", [...schedule.excludedDates, excludedDateInput].sort());
    setExcludedDateInput("");
  };

  const changeTime = (value: string) => {
    setTime(value);
    if (cronPreset !== "Custom cron") applyPreset(cronPreset, value);
  };

  const next = () => {
    if (errors[step]) {
      toast.error(errors[step] ?? "Check the required fields");
      return;
    }
    setStep((current) => Math.min(current + 1, STEPS.length - 1));
  };

  const save = async () => {
    const firstError = Object.entries(errors).find(([, error]) => error);
    if (firstError) {
      setStep(Number(firstError[0]));
      toast.error(firstError[1] ?? "Check the required fields");
      return;
    }
    const status = isNew ? "Active" : initial.status;
    setSaving(true);
    try {
      await actions.save(
        {
          ...schedule,
          name: schedule.name.trim(),
          owner: schedule.owner.trim(),
          ownerEmail: schedule.ownerEmail.trim(),
          status,
        },
        isNew,
      );
      toast.success(isNew ? "Schedule created" : "Schedule updated");
      navigate("/task-scheduler");
    } catch (error) {
      console.error("Unable to save schedule", error);
      toast.error(error instanceof Error ? error.message : "Unable to save schedule");
    } finally {
      setSaving(false);
    }
  };

  const loadFile = async (file?: File) => {
    if (!file) return;
    try {
      update("code", await file.text());
    } catch (error) {
      console.error("Unable to read uploaded script", error);
      toast.error("Unable to read the selected file");
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {isNew ? "New Schedule" : `Edit ${initial.name}`}
        </h1>
        <p className="text-sm text-muted-foreground">
          {isNew ? "Create a job with only the essentials." : "Update the schedule configuration."}
        </p>
      </div>

      <ol className="flex items-center gap-2" aria-label="Wizard steps">
        {STEPS.map((label, index) => (
          <li key={label} className="flex flex-1 items-center gap-2">
            <button
              type="button"
              onClick={() => index < step && setStep(index)}
              aria-current={index === step ? "step" : undefined}
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-sm font-medium transition-colors",
                index === step
                  ? "border-primary bg-primary text-primary-foreground"
                  : index < step
                    ? "border-primary text-primary"
                    : "text-muted-foreground",
              )}
            >
              {index + 1}
            </button>
            <span
              className={cn(
                "hidden text-sm md:inline",
                index === step ? "font-medium" : "text-muted-foreground",
              )}
            >
              {label}
            </span>
            {index < STEPS.length - 1 && <div className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <Card>
        <CardContent className="space-y-5 p-6">
          {step === 0 && (
            <>
              <Field
                label="Schedule name *"
                id="name"
                error={schedule.name && nameTaken ? "Schedule name must be unique" : undefined}
              >
                <Input
                  id="name"
                  placeholder="Daily Sales ETL"
                  value={schedule.name}
                  onChange={(event) => update("name", event.target.value)}
                />
              </Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Owner name *" id="owner">
                  <Input
                    id="owner"
                    placeholder="Efrem"
                    value={schedule.owner}
                    onChange={(event) => update("owner", event.target.value)}
                  />
                </Field>
                <Field label="Owner email *" id="owner-email">
                  <Input
                    id="owner-email"
                    type="email"
                    placeholder="efrem@example.com"
                    value={schedule.ownerEmail}
                    onChange={(event) => update("ownerEmail", event.target.value)}
                  />
                </Field>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <Label htmlFor="notifications">Accept Notifications</Label>
                  <p className="text-xs text-muted-foreground">
                    Email run updates to the owner email above.
                  </p>
                </div>
                <Switch
                  id="notifications"
                  checked={schedule.acceptNotifications}
                  onCheckedChange={(value) => update("acceptNotifications", value)}
                />
              </div>
              {errors[0] && <p className="text-sm text-destructive">{errors[0]}</p>}
            </>
          )}

          {step === 1 && (
            <>
              <Field label="Schedule type" id="schedule-type">
                <Pick
                  id="schedule-type"
                  value={schedule.scheduleType}
                  onChange={(value) => {
                    const scheduleType = value as Schedule["scheduleType"];
                    update("scheduleType", scheduleType);
                    if (scheduleType !== "Cron") {
                      update("daysOfWeek", []);
                      update("windowStart", null);
                      update("windowEnd", null);
                    }
                  }}
                  options={["Cron", "Interval", "Manual"]}
                />
              </Field>
              {schedule.scheduleType === "Cron" && (
                <>
                  <Field label="Cron preset" id="cron-preset">
                    <Pick
                      id="cron-preset"
                      value={cronPreset}
                      onChange={(value) => applyPreset(value as CronPreset)}
                      options={["Daily", "Weekly", "Monthly", "Custom cron"]}
                    />
                  </Field>
                  {cronPreset !== "Custom cron" ? (
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Time" id="cron-time">
                        <Input
                          id="cron-time"
                          type="time"
                          value={time}
                          onChange={(event) => changeTime(event.target.value)}
                        />
                      </Field>
                      {cronPreset === "Weekly" && (
                        <Field label="Day of week" id="weekday">
                          <Pick
                            id="weekday"
                            value={weekday}
                            onChange={(value) => {
                              setWeekday(value);
                              applyPreset("Weekly", time, value);
                            }}
                            options={DAYS.map((day, index) => `${index}|${day}`)}
                            formatOption={(option) => option.split("|")[1]}
                          />
                        </Field>
                      )}
                      {cronPreset === "Monthly" && (
                        <Field label="Day of month" id="month-day">
                          <Input
                            id="month-day"
                            type="number"
                            min={1}
                            max={31}
                            value={monthDay}
                            onChange={(event) => {
                              setMonthDay(event.target.value);
                              applyPreset("Monthly", time, weekday, event.target.value || "1");
                            }}
                          />
                        </Field>
                      )}
                    </div>
                  ) : (
                    <div className="grid grid-cols-5 gap-2">
                      {CRON_FIELDS.map((field, index) => (
                        <div key={field} className="space-y-1">
                          <Label
                            htmlFor={`cron-${index}`}
                            className="text-xs text-muted-foreground"
                          >
                            {field}
                          </Label>
                          <Input
                            id={`cron-${index}`}
                            className="text-center font-mono"
                            value={cronParts[index] ?? "*"}
                            onChange={(event) => {
                              const parts = [...cronParts];
                              while (parts.length < 5) parts.push("*");
                              parts[index] = event.target.value.trim() || "*";
                              update("cron", parts.join(" "));
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="rounded-md bg-muted p-3">
                    <p className="font-mono text-sm">{schedule.cron}</p>
                    <p className="text-sm text-muted-foreground">{scheduleToHuman(schedule)}</p>
                  </div>
                  <div className="space-y-4 border p-4">
                    <div className="space-y-2">
                      <p className="text-sm font-medium">Allowed weekdays</p>
                      <p className="text-xs text-muted-foreground">
                        Selected weekdays further restrict cron triggers. Leave all days unselected
                        to rely on the cron expression.
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {RUN_DAYS.map((day, index) => (
                          <button
                            key={day}
                            type="button"
                            aria-pressed={schedule.daysOfWeek.includes(index)}
                            onClick={() => toggleRunDay(index)}
                            className={cn(
                              "border px-3 py-2 text-sm transition-colors",
                              schedule.daysOfWeek.includes(index)
                                ? "border-primary bg-primary text-primary-foreground"
                                : "border-input hover:bg-accent",
                            )}
                          >
                            {day.slice(0, 3)}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field label="Window start (optional)" id="window-start">
                        <Input
                          id="window-start"
                          type="time"
                          value={windowStart}
                          onChange={(event) => update("windowStart", event.target.value || null)}
                        />
                      </Field>
                      <Field label="Window end (optional)" id="window-end">
                        <Input
                          id="window-end"
                          type="time"
                          value={windowEnd}
                          onChange={(event) => update("windowEnd", event.target.value || null)}
                        />
                      </Field>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Both times are required together. Cron triggers outside this same-day window
                      are skipped using the selected timezone.
                    </p>
                  </div>
                </>
              )}
              {schedule.scheduleType === "Interval" && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Every" id="interval-value">
                    <Input
                      id="interval-value"
                      type="number"
                      min={1}
                      value={schedule.intervalValue}
                      onChange={(event) => update("intervalValue", Number(event.target.value))}
                    />
                  </Field>
                  <Field label="Unit" id="interval-unit">
                    <Pick
                      id="interval-unit"
                      value={schedule.intervalUnit}
                      onChange={(value) =>
                        update("intervalUnit", value as Schedule["intervalUnit"])
                      }
                      options={["minutes", "hours"]}
                    />
                  </Field>
                </div>
              )}
              {schedule.scheduleType === "Manual" && (
                <p className="text-sm text-muted-foreground">
                  This job runs only when you choose Run Now.
                </p>
              )}
              <div className="space-y-3 border p-4">
                <div>
                  <p className="text-sm font-medium">Excluded dates</p>
                  <p className="text-xs text-muted-foreground">
                    Runs on these dates are skipped. Dates use the schedule timezone.
                  </p>
                </div>
                <div className="flex gap-2">
                  <Input
                    aria-label="Date to exclude"
                    type="date"
                    value={excludedDateInput}
                    onChange={(event) => setExcludedDateInput(event.target.value)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={addExcludedDate}
                    disabled={
                      !excludedDateInput || schedule.excludedDates.includes(excludedDateInput)
                    }
                  >
                    <Plus className="h-4 w-4" /> Add date
                  </Button>
                </div>
                {schedule.excludedDates.length > 0 && (
                  <ul className="flex flex-wrap gap-2" aria-label="Excluded dates">
                    {schedule.excludedDates.map((date) => (
                      <li key={date} className="flex items-center gap-2 border px-2 py-1 text-sm">
                        <span>{date}</span>
                        <button
                          type="button"
                          aria-label={`Remove excluded date ${date}`}
                          onClick={() =>
                            update(
                              "excludedDates",
                              schedule.excludedDates.filter((item) => item !== date),
                            )
                          }
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Timezone" id="timezone">
                  <Pick
                    id="timezone"
                    value={schedule.timezone}
                    onChange={(value) => update("timezone", value)}
                    options={TIMEZONES}
                  />
                </Field>
                <Field label="Start date" id="start-date">
                  <Input
                    id="start-date"
                    type="date"
                    value={schedule.startDate ?? ""}
                    onChange={(event) => update("startDate", event.target.value)}
                  />
                </Field>
                <Field label="End date" id="end-date">
                  <Input
                    id="end-date"
                    type="date"
                    value={schedule.endDate ?? ""}
                    onChange={(event) => update("endDate", event.target.value)}
                  />
                </Field>
              </div>
              {errors[1] && <p className="text-sm text-destructive">{errors[1]}</p>}
            </>
          )}

          {step === 2 && (
            <>
              <Field label="Task type" id="task-type">
                <Segmented
                  value={schedule.type}
                  onChange={(value) => update("type", value as Schedule["type"])}
                  options={["Python", "SQL"]}
                />
              </Field>
              {schedule.type === "SQL" && (
                <Field label="Connection *" id="connection">
                  <Pick
                    id="connection"
                    value={schedule.connection ?? ""}
                    onChange={(value) => update("connection", value)}
                    options={CONNECTIONS}
                    placeholder="Choose a connection"
                  />
                </Field>
              )}
              <Field label="Script source" id="script-source">
                <Segmented
                  value={codeSource === "upload" ? "Upload file" : "Type script"}
                  onChange={(value) => setCodeSource(value === "Upload file" ? "upload" : "type")}
                  options={["Upload file", "Type script"]}
                />
              </Field>
              {codeSource === "upload" && (
                <Field label="Script file" id="script-file">
                  <Input
                    id="script-file"
                    type="file"
                    accept={schedule.type === "Python" ? ".py,.txt" : ".sql,.txt"}
                    onChange={(event) => void loadFile(event.target.files?.[0])}
                  />
                  <p className="text-xs text-muted-foreground">
                    Accepted: {schedule.type === "Python" ? ".py, .txt" : ".sql, .txt"}
                  </p>
                </Field>
              )}
              {(codeSource === "type" || schedule.code) && (
                <Field label={codeSource === "upload" ? "Uploaded script" : "Script"} id="script">
                  <Textarea
                    id="script"
                    spellCheck={false}
                    className="min-h-56 bg-sidebar font-mono text-sm text-sidebar-foreground"
                    value={schedule.code}
                    readOnly={codeSource === "upload"}
                    onChange={(event) => update("code", event.target.value)}
                    placeholder={schedule.type === "SQL" ? "SELECT ..." : "def main():"}
                  />
                </Field>
              )}
              <div className="rounded-md border">
                <button
                  type="button"
                  className="flex w-full items-center justify-between p-3 text-left text-sm font-medium"
                  aria-expanded={advancedOpen}
                  onClick={() => setAdvancedOpen((open) => !open)}
                >
                  Advanced <span className="text-muted-foreground">{advancedOpen ? "−" : "+"}</span>
                </button>
                {advancedOpen && (
                  <div className="grid gap-4 border-t p-3 sm:grid-cols-2">
                    <Field label="Retries" id="retries">
                      <Input
                        id="retries"
                        type="number"
                        min={0}
                        value={schedule.retries}
                        onChange={(event) =>
                          update("retries", Math.max(0, Number(event.target.value)))
                        }
                      />
                    </Field>
                    <Field label="Retry delay (seconds)" id="retry-delay">
                      <Input
                        id="retry-delay"
                        type="number"
                        min={0}
                        value={schedule.retryDelay}
                        onChange={(event) =>
                          update("retryDelay", Math.max(0, Number(event.target.value)))
                        }
                      />
                    </Field>
                  </div>
                )}
              </div>
              {errors[2] && <p className="text-sm text-destructive">{errors[2]}</p>}
            </>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          variant="ghost"
          onClick={() => (step === 0 ? navigate("/task-scheduler") : setStep(step - 1))}
        >
          <ChevronLeft className="h-4 w-4" /> {step === 0 ? "Cancel" : "Back"}
        </Button>
        {step < STEPS.length - 1 ? (
          <Button onClick={next}>
            Next <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving..." : isNew ? "Create Schedule" : "Save Changes"}
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  id,
  error,
  children,
}: {
  label: string;
  id: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

function Pick({
  id,
  value,
  onChange,
  options,
  placeholder,
  formatOption = (option) => option,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  formatOption?: (option: string) => string;
}) {
  return (
    <Select value={value || undefined} onValueChange={onChange}>
      <SelectTrigger id={id}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option} value={option.split("|")[0]}>
            {formatOption(option)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <div role="radiogroup" className="inline-flex rounded-md border bg-muted p-1">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={value === option}
          onClick={() => onChange(option)}
          className={cn(
            "rounded px-3 py-1.5 text-sm transition-colors",
            value === option
              ? "bg-card font-medium shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
