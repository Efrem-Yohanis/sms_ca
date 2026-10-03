export type CampaignStatus = "draft" | "active" | "paused" | "completed" | "archived";
export type ScheduleType = "once" | "daily" | "weekly" | "monthly";
export type ScheduleStatus = "pending" | "running" | "stop" | "completed";
export type Channel = "sms" | "app_notification" | "flash_sms";
export type Language = "en" | "am" | "ti" | "om" | "so";

export const CHANNEL_LABELS: Record<Channel, string> = {
  sms: "SMS",
  app_notification: "App Notification",
  flash_sms: "Flash SMS",
};

export const SCHEDULE_STATUS_LABELS: Record<ScheduleStatus, string> = {
  pending: "Pending",
  running: "Running",
  stop: "Stopped",
  completed: "Completed",
};

export const EXECUTION_STATUS_LABELS: Record<string, string> = {
  PENDING: "Pending",
  PROCESSING: "Processing",
  PAUSED: "Paused",
  STOPPED: "Stopped",
  COMPLETED: "Completed",
  FAILED: "Failed",
  ACTIVE: "Active",
};

export const WINDOW_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  active: "Active",
  completed: "Completed",
  partial: "Partial",
  skipped: "Skipped",
};

export const SCHEDULE_TYPE_LABELS: Record<ScheduleType, string> = {
  once: "One-time",
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
};

export const SUPPORTED_LANGUAGES: Language[] = ["en", "am", "ti", "om", "so"];

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: "English",
  am: "Amharic",
  ti: "Tigrinya",
  om: "Afaan Oromoo",
  so: "Somali",
};

export const DAY_LABELS: Record<number, string> = {
  0: "Monday",
  1: "Tuesday",
  2: "Wednesday",
  3: "Thursday",
  4: "Friday",
  5: "Saturday",
  6: "Sunday",
};

export interface Recipient {
  msisdn: string;
  lang: Language;
}

export interface AudienceDatabaseSelection {
  source_database_id: number;
  source_table: string;
  source_msisdn_column: string;
  source_language_column: string;
  source_filter_clause: string;
}

export interface TimeWindow {
  start: string;
  end: string;
}

export interface Schedule {
  schedule_type: ScheduleType;
  start_date: string;
  end_date?: string;
  run_days?: number[];
  time_windows: TimeWindow[];
  timezone: string;
  auto_reset: boolean;
  is_active: boolean;
  status: ScheduleStatus;
}

export interface CampaignProgress {
  total_messages: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  failed_delivery_count: number;
  pending_count: number;
  progress_percent: number;
  status: string;
  started_at: string;
  completed_at: string | null;
}

export interface ExecutionRound {
  round: number;
  date: string;
  window: string;
  status: "completed" | "partial" | "failed" | "pending" | "active";
  queued: number;
  sent: number;
  delivered: number;
  failed_send: number;
  failed_delivery: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface MessageContent {
  content: Record<Language, string>;
  default_language: Language;
}

export interface Audience {
  recipients: Recipient[];
  total_count: number;
  valid_count: number;
  invalid_count: number;
}

export interface Campaign {
  id: string;
  name: string;
  status: CampaignStatus;
  execution_status?: string;
  execution_status_display?: string;
  sender_id: string;
  channels: Channel[];
  schedule: Schedule;
  message_content: MessageContent;
  audience: Audience;
  progress?: CampaignProgress;
  execution_rounds?: ExecutionRound[];
  can_start?: boolean;
  can_pause?: boolean;
  can_resume?: boolean;
  can_stop?: boolean;
  can_complete?: boolean;
  created_at: string;
  updated_at: string;
}

/* ---------- Wizard ---------- */

export type AudienceSource = "manual" | "file" | "database";

export interface WizardData {
  name: string;
  owner_emails: string[];
  sender_id: string;
  channels: Channel[];
  schedule_type: ScheduleType;
  start_date: string;
  end_date: string;
  run_days: number[];
  time_windows: TimeWindow[];
  timezone: string;
  auto_reset: boolean;
  content: Record<Language, string>;
  default_language: Language;
  audience_source: AudienceSource;
  audience_database_config: AudienceDatabaseSelection | null;
  source_file: File | null;
  recipients: Recipient[];
  db_query: string;
}

export const EMPTY_WIZARD: WizardData = {
  name: "",
  owner_emails: [],
  sender_id: "",
  channels: ["sms"],
  schedule_type: "once",
  start_date: "",
  end_date: "",
  run_days: [],
  time_windows: [{ start: "", end: "" }],
  timezone: "UTC",
  auto_reset: true,
  content: { en: "", am: "", ti: "", om: "", so: "" },
  default_language: "en",
  audience_source: "manual",
  audience_database_config: null,
  source_file: null,
  recipients: [],
  db_query: "",
};
