import { Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, Check,
  CheckCircle2, ChevronDown, ChevronRight, CircleHelp, Clock3, Copy,
  Ellipsis, FileText, Gauge, Hash, Inbox, Layers3, ListFilter, PanelLeftClose, PanelLeftOpen, Trash2,
  Mail, Menu, MessageSquareText, MoreHorizontal, Pencil, Plus, Radio, RefreshCw, Search,
  Send, SlidersHorizontal, Users, X, Zap,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { BackendConfiguration, type BackendConfigPage } from "@/components/admin/backend-configuration";
import {
  UsersManagement,
  UserEditor,
  type UserAssignmentOptions,
  type UserRecord,
  type UserSaveInput,
} from "@/components/admin/users-management";
import {
  replaceConfigurationEntries,
  useConfigurationEntries,
  type ConfigEntry,
  type ConfigPage,
} from "@/components/admin/configuration-store";
import {
  adminRequest,
  clearAdminTokens,
  deleteUser,
  getAccessToken,
  listConfig,
  listUsers,
  saveUser as saveApiUser,
  type ApiConfig,
  type ApiUser,
  type UserInput,
} from "@/lib/admin-api";

export type Page = "Overview" | "Users" | "Campaigns" | "SMSC Accounts" | "Sender IDs" | "Channels" | "TPS" | "N-Addresses" | "TPS & N-Addresses" | "SMTP" | "System Logs" | "Kafka Monitor";
type User = UserRecord;
type Campaign = {
  id: string;
  name: string;
  owner: string;
  status: "Active" | "Completed" | "Draft" | "Paused";
  executionStatus: string;
  audience: string;
  audienceValid: string;
  audienceInvalid: string;
  audienceSource: string;
  audienceDescription: string;
  type: string;
  sent: string;
  delivered: string;
  failedSent: string;
  failedDelivery: string;
  date: string;
  rate: number;
  scheduleType: string;
  scheduleStart: string;
  scheduleEnd: string;
  scheduleTimezone: string;
  scheduleRepeat: string;
  messageContent: Record<"am" | "en" | "om" | "so" | "ti", string>;
  senderId: string;
  channel: string;
  smscAccount: string;
  executionStartedAt: string;
  executionCompletedAt: string;
};

const campaignsSeed: Campaign[] = [
  { id: "CMP-2048", name: "September product launch", owner: "Olivia Chen", status: "Active", executionStatus: "Processing", audience: "24,580", audienceValid: "24,580", audienceInvalid: "0", audienceSource: "Product launch subscribers", audienceDescription: "Subscribers opted in to product announcements.", type: "Bulk SMS", sent: "18,420", delivered: "17,892", failedSent: "0", failedDelivery: "528", date: "Sep 30, 2026", rate: 97.1, scheduleType: "One-time", scheduleStart: "Sep 30, 2026, 9:00 AM", scheduleEnd: "Sep 30, 2026, 5:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Does not repeat", messageContent: { am: "ሰላም! አዲሱ ምርታችን ደርሷል። አዳዲስ ነገሮችን ይመልከቱ እና የቅርብ ጊዜ ቅናሾችን ያግኙ።", en: "Hi there! Our new product is here. Discover what’s new and explore the latest offers today.", om: "Akkam! Oomishni keenya haaraan dhiyaateera. Har’a wantoota haaraa fi dhiyeessiiwwan yeroo dhiyoo ilaalaa.", so: "Salaan! Badeecaddeenna cusub waa diyaar. Maanta ogow waxa cusub oo eeg dalabyadii ugu dambeeyay.", ti: "ሰላም! ሓድሽ ፍርያትና በጺሑ ኣሎ። ሓድሽ ነገራት ርኣዩን ናይ ቀረባ ግዜ ቅናሻትና ድማ መርምሩ።" }, senderId: "ACME", channel: "SMS", smscAccount: "Primary gateway", executionStartedAt: "Sep 30, 2026, 9:00 AM", executionCompletedAt: "In progress" },
  { id: "CMP-2047", name: "Fall welcome series", owner: "Marcus Rivera", status: "Active", executionStatus: "Processing", audience: "12,340", audienceValid: "12,340", audienceInvalid: "0", audienceSource: "New customer list", audienceDescription: "New customers registered during the fall campaign period.", type: "Scheduled SMS", sent: "8,756", delivered: "8,521", failedSent: "0", failedDelivery: "235", date: "Sep 30, 2026", rate: 97.3, scheduleType: "Weekly", scheduleStart: "Sep 30, 2026, 10:00 AM", scheduleEnd: "Oct 31, 2026, 4:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Every Wednesday", messageContent: { am: "እንኳን ደህና መጡ! ስለተቀላቀሉን እናመሰግናለን። እዚህ በመሆንዎ ደስ ብሎናል፤ ወቅታዊ መረጃዎችንም እናሳውቅዎታለን።", en: "Welcome! Thank you for joining us. We’re glad you’re here and look forward to keeping you updated.", om: "Baga nagaan dhuftan! Nu waliin waan makamtaniif galatoomaa. As jiraachuun keessan nu gammachiisa; odeeffannoo haaraas isin beeksisna.", so: "Soo dhawoow! Waad ku mahadsan tahay inaad nagu soo biirtay. Waan ku faraxsanahay inaad nala joogto, wararkana waan kula wadaagi doonnaa.", ti: "እንቋዕ ብደሓን መጻእኩም! ስለ ዝተጸንበርኩምና ነመስግነኩም። ምሳና ምህላውኩም የሐጉሰና፣ ሓድሽ ሓበሬታ እውን ክንህበኩም ኢና።" }, senderId: "BRIGHTLY", channel: "SMS", smscAccount: "Brightly SMS", executionStartedAt: "Sep 30, 2026, 10:00 AM", executionCompletedAt: "In progress" },
  { id: "CMP-2046", name: "Appointment reminders", owner: "James Okafor", status: "Completed", executionStatus: "Completed", audience: "8,420", audienceValid: "8,186", audienceInvalid: "234", audienceSource: "Upcoming appointments", audienceDescription: "Contacts with appointments scheduled for the reminder period.", type: "Scheduled SMS", sent: "8,420", delivered: "8,186", failedSent: "0", failedDelivery: "234", date: "Sep 29, 2026", rate: 97.2, scheduleType: "One-time", scheduleStart: "Sep 29, 2026, 8:00 AM", scheduleEnd: "Sep 29, 2026, 12:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Does not repeat", messageContent: { am: "ማስታወሻ፦ ቀጣይ ቀጠሮ አለዎት። ለውጥ ማድረግ ከፈለጉ እባክዎ ያነጋግሩን።", en: "Reminder: you have an upcoming appointment. Please contact us if you need to make a change.", om: "Yaadachiisa: beellamni keessan dhiyaachaa jira. Jijjiirama yoo barbaaddan maaloo nu qunnamaa.", so: "Xusuusin: ballan ayaa kuu soo socda. Fadlan nala soo xiriir haddii aad u baahan tahay inaad wax beddesho.", ti: "መዘኻኸሪ፦ ዝመጽእ ቆጸራ ኣለኩም። ለውጢ ክትገብሩ እንተደሊኹም በጃኹም ርኸቡና።" }, senderId: "MERIDIAN", channel: "SMS", smscAccount: "Meridian backup", executionStartedAt: "Sep 29, 2026, 8:00 AM", executionCompletedAt: "Sep 29, 2026, 11:42 AM" },
  { id: "CMP-2045", name: "Member rewards update", owner: "Aisha Patel", status: "Completed", executionStatus: "Completed", audience: "16,280", audienceValid: "16,280", audienceInvalid: "0", audienceSource: "Rewards members", audienceDescription: "Active members enrolled in the rewards program.", type: "Bulk SMS", sent: "16,280", delivered: "15,954", failedSent: "0", failedDelivery: "326", date: "Sep 29, 2026", rate: 98.0, scheduleType: "One-time", scheduleStart: "Sep 29, 2026, 1:00 PM", scheduleEnd: "Sep 29, 2026, 6:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Does not repeat", messageContent: { am: "ሽልማቶችዎ ይጠብቁዎታል! አዳዲስ የአባልነት ጥቅሞችንና ቅናሾችን ለማየት መለያዎን ይመልከቱ።", en: "Your rewards are waiting! Check your account to see the latest member benefits and offers.", om: "Badhaasni keessan isin eeggata! Faayidaalee miseensummaa fi dhiyeessii haaraa ilaaluuf herrega keessan ilaalaa.", so: "Abaalmarinnadaadu way ku sugayaan! Akoonkaaga ka eeg faa'iidooyinka xubinnimada iyo dalabyada cusub.", ti: "ሽልማታትኩም ይጽበዩኹም ኣለዉ! ሓደሽቲ ጥቕምታትን ቅናሻትን ንምርኣይ ኣካውንትኩም ርኣዩ።" }, senderId: "NORTHSTAR", channel: "SMS", smscAccount: "Northstar primary", executionStartedAt: "Sep 29, 2026, 1:00 PM", executionCompletedAt: "Sep 29, 2026, 4:15 PM" },
  { id: "CMP-2044", name: "October early access", owner: "Daniel Kim", status: "Draft", executionStatus: "Pending", audience: "31,200", audienceValid: "30,940", audienceInvalid: "260", audienceSource: "Early access list", audienceDescription: "Customers registered for early access announcements.", type: "Bulk SMS", sent: "—", delivered: "—", failedSent: "—", failedDelivery: "—", date: "Sep 28, 2026", rate: 0, scheduleType: "One-time", scheduleStart: "Oct 05, 2026, 9:00 AM", scheduleEnd: "Oct 05, 2026, 5:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Does not repeat", messageContent: { am: "የጥቅምት ስብስባችንን ከሁሉ በፊት ይመልከቱ። አዳዲስ ምርቶችን ለማሰስ ድረ ገጻችንን ይጎብኙ።", en: "Get early access to our October collection. Visit our website to explore what’s new.", om: "Kuusaa Onkololeessaa keenya dursee argadhaa. Wantoota haaraa ilaaluuf marsariitii keenya daawwadhaa.", so: "Hel helitaan hore oo ku saabsan ururintayada Oktoobar. Booqo boggayaga si aad u ogaato waxa cusub.", ti: "ኣብ ናይ ጥቅምቲ ምርታትና ቀዳማይ ፍቓድ ርኸቡ። ሓድሽ ንምርኣይ ናብ ወብሳይትና ብጽሑ።" }, senderId: "PULSE", channel: "SMS", smscAccount: "Primary gateway", executionStartedAt: "Not started", executionCompletedAt: "Not completed" },
  { id: "CMP-2043", name: "Customer feedback", owner: "Olivia Chen", status: "Paused", executionStatus: "Paused", audience: "5,400", audienceValid: "5,400", audienceInvalid: "0", audienceSource: "Recent purchasers", audienceDescription: "Customers who made a purchase in the last 30 days.", type: "Bulk SMS", sent: "2,150", delivered: "2,093", failedSent: "0", failedDelivery: "57", date: "Sep 27, 2026", rate: 97.3, scheduleType: "One-time", scheduleStart: "Sep 27, 2026, 2:00 PM", scheduleEnd: "Sep 27, 2026, 6:00 PM", scheduleTimezone: "Africa/Addis_Ababa", scheduleRepeat: "Does not repeat", messageContent: { am: "በቅርቡ ግዢ ስለፈጸሙ እናመሰግናለን! እንድንሻሻል እባክዎ አስተያየትዎን ያጋሩን።", en: "Thanks for your recent purchase! Please share your feedback to help us improve.", om: "Dhiyeenya kana waan bitattaniif galatoomaa! Akka fooyyaanuuf yaada keessan nuuf qoodaa.", so: "Waad ku mahadsan tahay iibsigii dhowaa! Fadlan nala wadaag ra'yigaaga si aan u horumarno.", ti: "ስለ ቀረባ ግዝኣትኩም ነመስግነኩም! ንኽንመሓየሽ በጃኹም ርእይቶኹም ኣካፍሉና።" }, senderId: "ACME", channel: "SMS", smscAccount: "Primary gateway", executionStartedAt: "Sep 27, 2026, 2:00 PM", executionCompletedAt: "Paused" },
];

const navItems: { name: Page; icon: LucideIcon }[] = [
  { name: "Users", icon: Users },
  { name: "Campaigns", icon: Send },
  { name: "SMSC Accounts", icon: Radio },
  { name: "Sender IDs", icon: Hash },
  { name: "Channels", icon: Layers3 },
  { name: "TPS", icon: Gauge },
  { name: "N-Addresses", icon: Inbox },
];
const format = (num: number) => num.toLocaleString("en-US");
const initials = (name: string) => name.split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

function fromApiUser(user: ApiUser): User {
  const name = user.full_name || user.username;
  return {
    profileId: user.id,
    userId: user.user_id,
    name,
    email: user.email,
    company: user.department,
    department: user.department,
    username: user.username,
    apiRole: user.role,
    role: user.role === "ADMIN" ? "Admin" : "Campaign Manager",
    initials: initials(name),
    status: user.is_locked ? "Locked" : user.is_active ? "Active" : "Inactive",
    smsc: user.assigned_config_counts.smsc,
    sender: user.assigned_config_counts.sender_ids,
    channels: user.assigned_config_counts.channels,
    tps: user.tps_limit ?? 0,
    n: user.assigned_config_counts.n_addresses,
    login: user.last_login ? new Date(user.last_login).toLocaleString() : "Never",
    lastLoginAt: user.last_login ?? undefined,
    tone: "mint",
    notes: user.notes,
    assignedSmscs: user.assigned_smscs,
    assignedSenderIds: user.assigned_sender_ids,
    assignedChannels: user.assigned_channels,
    assignedTpsConfigs: user.assigned_tps_configs,
    assignedNAddressConfigs: user.assigned_n_address_configs,
    assignedNAddresses: user.assigned_n_addresses,
  };
}

function labelsFor(users: User[], ids: unknown) {
  const userIds = Array.isArray(ids) ? ids.map(Number) : [];
  return userIds
    .map((id) => users.find((user) => user.userId === id)?.email)
    .filter((email): email is string => Boolean(email));
}

function toStoreEntries(page: ConfigPage, configs: ApiConfig[], users: User[]): ConfigEntry[] {
  return configs.map((config) => {
    const subscribers = labelsFor(users, config.assigned_user_ids);
    let values: string[];
    if (page === "SMSC Accounts") {
      values = [
        String(config.name ?? ""),
        subscribers.length ? `${subscribers.length} assigned` : "—",
        String(config.base_url ?? ""),
        String(config.auth_type ?? ""),
        `${String(config.rate_limit_per_second ?? "—")}/s`,
      ];
    } else if (page === "Sender IDs") {
      values = [
        String(config.sender_id ?? ""),
        String(config.name ?? ""),
        subscribers.length ? `${subscribers.length} assigned` : "—",
        config.is_default ? "Yes" : "No",
      ];
    } else {
      values = [
        String(config.code ?? ""),
        String(config.name ?? ""),
        `${subscribers.length} users`,
      ];
    }
    return {
      id: String(config.id),
      values,
      active: Boolean(config.is_active),
      subscriberEmails: subscribers,
    };
  });
}

function Status({ value }: { value: string }) {
  const tone = value === "Active" || value === "Connected" || value === "Delivered" || value === "Completed" ? "bg-success-soft text-success" : value === "Paused" || value === "Pending" || value === "Draft" ? "bg-warning-soft text-warning" : value === "Inactive" || value === "Failed" ? "bg-danger-soft text-destructive" : "bg-muted text-muted-foreground";
  return <span className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${tone}`}><span className="size-1.5 rounded-full bg-current" />{value}</span>;
}
function Avatar({ name, tone = "mint", size = "sm" }: { name: string; tone?: string; size?: "sm" | "lg" }) {
  const colors: Record<string, string> = { mint: "bg-accent text-accent-foreground", lavender: "bg-secondary text-secondary-foreground", peach: "bg-warning-soft text-warning", blue: "bg-muted text-foreground", rose: "bg-danger-soft text-destructive", yellow: "bg-warning-soft text-warning" };
  return <span className={`inline-flex shrink-0 items-center justify-center rounded-full font-bold ${size === "lg" ? "size-14 text-lg" : "size-8 text-[10px]"} ${colors[tone] || colors["mint"]}`}>{initials(name)}</span>;
}
function SectionHeading({ title, detail, action }: { title: string; detail?: string; action?: React.ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><h2 className="font-display text-[16px] font-bold text-foreground">{title}</h2>{detail && <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p>}</div>{action}</div>;
}
function DetailSection({ title, fields, children }: { title: string; fields?: [string, string][]; children?: React.ReactNode }) {
  return <section className="rounded-md border border-border bg-card p-5"><h2 className="mb-4 font-display text-base font-bold">{title}</h2>{fields && <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">{fields.map(([label, value]) => <div key={label}><dt className="text-[11px] text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-medium">{value}</dd></div>)}</dl>}{children}</section>;
}
function Empty({ text = "No results found" }: { text?: string }) { return <div className="py-16 text-center text-sm text-muted-foreground">{text}</div>; }

function AssignedResources({
  user,
  page,
  options,
}: {
  user: User;
  page: "SMSC Accounts" | "Sender IDs" | "Channels" | "TPS" | "N-Addresses";
  options: UserAssignmentOptions;
}) {
  const fields: Record<typeof page, [string, number[], { id: number; label: string }[]][]> = {
    "SMSC Accounts": [["SMSC connections", user.assignedSmscs, options.smscs]],
    "Sender IDs": [["Sender IDs", user.assignedSenderIds, options.senderIds]],
    Channels: [["Channels", user.assignedChannels, options.channels]],
    TPS: [["TPS configurations", user.assignedTpsConfigs, options.tpsConfigs]],
    "N-Addresses": [
      ["N-address configurations", user.assignedNAddressConfigs, options.nAddressConfigs],
      ["N-addresses", user.assignedNAddresses, options.nAddresses],
    ],
  };
  const assigned = fields[page].flatMap(([label, ids, choices]) => {
    const selected = choices.filter((item) => ids.includes(item.id));
    return selected.length ? [{ label, values: selected.map((item) => item.label) }] : [];
  });
  return (
    <div className="grid gap-4">
      {assigned.map(({ label, values }) => (
        <DetailSection key={label} title={label}>
          <ul className="space-y-2 text-sm">
            {values.map((value) => <li key={value}>{value}</li>)}
          </ul>
        </DetailSection>
      ))}
      {assigned.length === 0 && (
        <div className="rounded-md border border-border bg-card">
          <Empty text={`No ${page.toLowerCase()} assigned to this user.`} />
        </div>
      )}
    </div>
  );
}

export function AdminConsole({ initialPage }: { initialPage: Page }) {
  const [page, setPage] = useState<Page>(initialPage);
  useEffect(() => setPage(initialPage), [initialPage]);
  const navigate = useNavigate();
  const [users, setUsers] = useState<User[]>([]);
  const [assignmentOptions, setAssignmentOptions] = useState<UserAssignmentOptions>({
    smscs: [],
    senderIds: [],
    channels: [],
    tpsConfigs: [],
    nAddressConfigs: [],
    nAddresses: [],
  });
  const [currentAdmin, setCurrentAdmin] = useState("Admin");
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState("");
  const campaigns = campaignsSeed;
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [editingUserDetails, setEditingUserDetails] = useState(false);
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [detailTab, setDetailTab] = useState("Profile");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All statuses");
  const [modal, setModal] = useState<string | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [notice, setNotice] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", company: "", phone: "", notes: "", tps: "100", n: "250" });
  const [settings, setSettings] = useState({ tps: "100", n: "250", smsc: "Primary gateway", email: "Default reports" });
  const [resourceRows, setResourceRows] = useState<Record<string, string[]>>({});

  useEffect(() => {
    let active = true;
    const expireSession = () => {
      void navigate({ to: "/login" });
    };
    window.addEventListener("admin-session-expired", expireSession);
    if (!getAccessToken()) {
      void navigate({ to: "/login" });
      return () => window.removeEventListener("admin-session-expired", expireSession);
    }

    void (async () => {
      try {
        const me = await adminRequest<ApiUser>("/admin/me/");
        const [apiUsers, smscs, senderIds, channels, tpsConfigs, nAddressConfigs, nAddresses] =
          await Promise.all([
            listUsers(),
            listConfig("smsc-configs"),
            listConfig("sender-ids"),
            listConfig("channels"),
            listConfig("tps-configs"),
            listConfig("n-address-configs"),
            listConfig("n-addresses"),
          ]);
        if (!active) return;
        const mappedUsers = apiUsers.map(fromApiUser);
        setUsers(mappedUsers);
        setCurrentAdmin(me.full_name || me.username);
        setAssignmentOptions({
          smscs: smscs.map((item) => ({ id: item.id, label: `${String(item.name ?? item.id)} (${String(item.base_url ?? "")})` })),
          senderIds: senderIds.map((item) => ({ id: item.id, label: `${String(item.sender_id ?? "")} — ${String(item.name ?? "")}` })),
          channels: channels.map((item) => ({ id: item.id, label: `${String(item.name ?? "")} (${String(item.code ?? "")})` })),
          tpsConfigs: tpsConfigs.map((item) => ({ id: item.id, label: `${String(item.name ?? "")} — ${String(item.global_tps ?? "")} TPS` })),
          nAddressConfigs: nAddressConfigs.map((item) => ({ id: item.id, label: `${String(item.name ?? "")} — ${String(item.max_addresses_per_request ?? "")} per request` })),
          nAddresses: nAddresses.map((item) => ({ id: item.id, label: `${String(item.value ?? "")} (${String(item.address_type ?? "")})` })),
        });
        replaceConfigurationEntries({
          "SMSC Accounts": toStoreEntries("SMSC Accounts", smscs, mappedUsers),
          "Sender IDs": toStoreEntries("Sender IDs", senderIds, mappedUsers),
          Channels: toStoreEntries("Channels", channels, mappedUsers),
        });
        setReady(true);
      } catch (reason) {
        if (active) {
          setBootError(reason instanceof Error ? reason.message : "Could not load the admin workspace.");
          setReady(true);
        }
      }
    })();
    return () => {
      active = false;
      window.removeEventListener("admin-session-expired", expireSession);
    };
  }, [navigate]);

  const pagePaths: Record<Page, string> = { Overview: "/", Users: "/users", Campaigns: "/campaigns", "SMSC Accounts": "/smsc-accounts", "Sender IDs": "/sender-ids", Channels: "/channels", TPS: "/tps", "N-Addresses": "/n-addresses", "TPS & N-Addresses": "/tps-n-addresses", SMTP: "/smtp", "System Logs": "/system-logs", "Kafka Monitor": "/kafka-monitor" };
  const go = (next: Page) => { setSelectedUser(null); setSelectedCampaign(null); setQuery(""); setFilter("All statuses"); setMenuOpen(false); if (next !== page) void navigate({ to: pagePaths[next] }); };
  const flash = (message: string) => { setNotice(message); window.setTimeout(() => setNotice(""), 3800); };
  const viewUser = (user: User) => { setSelectedUser(user); setDetailTab("Profile"); if (page !== "Users") void navigate({ to: "/users" }); };
  const viewCampaign = (campaign: Campaign) => { setSelectedCampaign(campaign); if (page !== "Campaigns") void navigate({ to: "/campaigns" }); };
  const toApiUser = (payload: UserSaveInput): UserInput => ({
    username: payload.username,
    email: payload.email,
    first_name: payload.firstName,
    last_name: payload.lastName,
    department: payload.department,
    role: payload.role,
    ...(payload.password ? { password: payload.password } : {}),
    is_active: payload.isActive,
    is_locked: payload.isLocked,
    notes: payload.notes,
    tps_limit: payload.tpsLimit,
    assigned_smscs: payload.assignedSmscs,
    assigned_sender_ids: payload.assignedSenderIds,
    assigned_channels: payload.assignedChannels,
    assigned_tps_configs: payload.assignedTpsConfigs,
    assigned_n_address_configs: payload.assignedNAddressConfigs,
    assigned_n_addresses: payload.assignedNAddresses,
  });
  const persistUser = async (
    user: User | null,
    _record: User,
    payload: UserSaveInput,
  ): Promise<User> => {
    const saved = fromApiUser(await saveApiUser(user?.profileId ?? null, toApiUser(payload)));
    if (selectedUser?.profileId === saved.profileId) setSelectedUser(saved);
    return saved;
  };
  const removeUser = async (user: User) => {
    await deleteUser(user.profileId);
    if (selectedUser?.profileId === user.profileId) setSelectedUser(null);
  };
  const updateAccount = async (
    user: User,
    changes: { isActive: boolean; isLocked: boolean },
  ): Promise<User> => {
    const payload: UserSaveInput = {
      username: user.username ?? user.email.split("@")[0] ?? "",
      email: user.email,
      firstName: user.firstName ?? "",
      lastName: user.lastName ?? "",
      department: user.department ?? user.company,
      role: user.apiRole ?? "CAMPAIGN_MANAGER",
      password: "",
      isActive: changes.isActive,
      isLocked: changes.isLocked,
      notes: user.notes ?? "",
      tpsLimit: user.tps || null,
      assignedSmscs: user.assignedSmscs,
      assignedSenderIds: user.assignedSenderIds,
      assignedChannels: user.assignedChannels,
      assignedTpsConfigs: user.assignedTpsConfigs,
      assignedNAddressConfigs: user.assignedNAddressConfigs,
      assignedNAddresses: user.assignedNAddresses,
    };
    const updated = fromApiUser(await saveApiUser(user.profileId, toApiUser(payload)));
    if (selectedUser?.profileId === updated.profileId) setSelectedUser(updated);
    return updated;
  };
  const persistUserDetails = async (record: User, payload: UserSaveInput) => {
    if (!selectedUser) return;
    const updated = await persistUser(selectedUser, record, payload);
    setUsers((current) =>
      current.map((candidate) => candidate.profileId === updated.profileId ? updated : candidate),
    );
    setSelectedUser(updated);
    setEditingUserDetails(false);
    flash("User changes saved.");
  };
  const openUserForm = (user?: User) => {
    if (user) setEditingUserDetails(true);
  };
  const saveUser = () => {
    if (!form.name.trim() || !form.email.includes("@")) { flash("Enter a name and valid email address."); return; }
    if (editing) setUsers((old) => old.map((u) => u.email === editing.email ? { ...u, name: form.name, email: form.email, company: form.company, tps: Number(form.tps), n: Number(form.n) } : u));
    else setUsers((old) => [{ name: form.name, email: form.email, company: form.company, initials: initials(form.name), status: "Active", smsc: 0, sender: 0, channels: 0, tps: Number(form.tps), n: Number(form.n), login: "Never", tone: "mint" }, ...old]);
    setSelectedUser(null); setModal(null); flash(editing ? "User changes saved in this preview." : "User added to this preview.");
  };
  const filteredUsers = useMemo(() => users.filter((u) => (`${u.name} ${u.email} ${u.company}`).toLowerCase().includes(query.toLowerCase()) && (filter === "All statuses" || u.status === filter)), [users, query, filter]);
  const filteredCampaigns = useMemo(() => campaigns.filter((c) => (`${c.name} ${c.id} ${c.owner}`).toLowerCase().includes(query.toLowerCase()) && (filter === "All statuses" || c.status === filter)), [campaigns, query, filter]);
  const openResource = (name: string) => { setForm({ name: "", email: "", company: "", phone: "", notes: "", tps: "100", n: "250" }); setModal(name); };

  if (!ready) {
    return <div className="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">Loading admin workspace…</div>;
  }
  if (bootError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
        <p role="alert" className="max-w-lg text-sm text-destructive">{bootError}</p>
        <Button onClick={() => { clearAdminTokens(); void navigate({ to: "/login" }); }}>Return to sign in</Button>
      </div>
    );
  }

  return <div className="flex min-h-screen bg-background font-sans text-foreground">
    {menuOpen && <div className="fixed inset-0 z-30 bg-foreground/40 lg:hidden" onClick={() => setMenuOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col bg-sidebar text-sidebar-foreground lg:translate-x-0 ${sidebarCollapsed ? "lg:w-16" : "lg:w-[248px]"} ${menuOpen ? "translate-x-0" : "-translate-x-full"}`}>
      <div className={`flex h-[75px] items-center gap-3 border-b border-sidebar-foreground/10 px-5 ${sidebarCollapsed ? "lg:justify-center lg:px-2" : ""}`}><span className={`font-display text-sm font-bold leading-tight text-sidebar-foreground ${sidebarCollapsed ? "lg:hidden" : ""}`}>SMS Campaign Manager</span>{sidebarCollapsed && <span className="hidden rounded bg-sidebar-foreground/10 px-2 py-1 text-xs font-bold text-sidebar-foreground lg:inline-flex" aria-hidden="true">SMS</span>}<Button variant="ghost" size="icon" className="ml-auto text-sidebar-foreground lg:hidden" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X /></Button></div>
      <nav className="admin-scroll flex-1 overflow-y-auto px-3 py-5"><div className="space-y-0.5">{navItems.map(({ name, icon: Icon }) => <Button key={name} variant="ghost" onClick={() => go(name)} title={sidebarCollapsed ? name : undefined} aria-label={name} className={`h-9 w-full justify-start gap-3 rounded-md px-3 text-[13px] font-medium shadow-none hover:bg-sidebar-active hover:text-sidebar-foreground ${sidebarCollapsed ? "lg:justify-center lg:px-0" : ""} ${page === name ? "bg-sidebar-active text-sidebar-foreground" : "text-sidebar-muted"}`}><Icon className="size-[17px] shrink-0" strokeWidth={1.9} /><span className={sidebarCollapsed ? "lg:sr-only" : ""}>{name}</span>{name === "Campaigns" && <span className={`ml-auto rounded bg-sidebar-foreground/10 px-1.5 py-0.5 text-[10px] ${sidebarCollapsed ? "lg:hidden" : ""}`}>{campaigns.length}</span>}</Button>)}</div></nav>
      <div className="border-t border-sidebar-foreground/10 p-3"><div className={`flex h-12 items-center gap-3 px-2 text-sidebar-foreground ${sidebarCollapsed ? "lg:justify-center lg:px-0" : ""}`} aria-label={`${currentAdmin}, administrator`}><Avatar name={currentAdmin} tone="mint" /><span className={`min-w-0 text-left ${sidebarCollapsed ? "lg:hidden" : ""}`}><span className="block truncate text-xs font-semibold">{currentAdmin}</span><span className="block text-[11px] text-sidebar-muted">Administrator</span></span></div></div>
    </aside>

    <div className={`min-w-0 flex-1 ${sidebarCollapsed ? "lg:pl-16" : "lg:pl-[248px]"}`}>
      <header className="sticky top-0 z-20 flex h-[75px] items-center justify-between gap-4 border-b border-border bg-card px-5 md:px-8 lg:px-10"><div className="flex min-w-0 items-center gap-3"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu /></Button><Button variant="ghost" size="icon" className="hidden lg:inline-flex" onClick={() => setSidebarCollapsed(collapsed => !collapsed)} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>{sidebarCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}</Button><span className="hidden text-xs text-muted-foreground sm:inline">Workspace</span><ChevronRight className="hidden size-3 text-muted-foreground sm:inline" /><span className="truncate text-sm font-semibold">{selectedUser ? selectedUser.name : selectedCampaign ? selectedCampaign.name : page}</span></div><div className="flex items-center gap-2 md:gap-4"><Avatar name={currentAdmin} /><Link to="/login" onClick={() => clearAdminTokens()} className="text-xs font-medium text-muted-foreground hover:text-foreground">Sign out</Link></div></header>

      <main className="mx-auto max-w-[1600px] px-5 pb-12 pt-8 md:px-8 lg:px-10">
        {page === "Overview" && <>
          <div className="mb-8 flex flex-wrap items-start justify-between gap-4"><div><h1 className="font-display text-[27px] font-bold leading-tight md:text-[32px]">Welcome, {currentAdmin} <span className="font-normal">✳</span></h1><p className="mt-1.5 text-sm text-muted-foreground">Here’s what’s happening across your messaging platform today.</p></div><div className="flex items-center gap-2"><span className="flex h-9 items-center gap-2 rounded-md border border-border bg-card px-3 text-xs font-medium text-muted-foreground"><Clock3 className="size-3.5" /> Sep 30, 2026</span></div></div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
            { label: "Total users", value: format(users.length), change: "Current", icon: Users, note: `${users.filter(u => u.status === "Active").length} active users`, pos: true },
            { label: "Total campaigns", value: "1,284", change: "+8.2%", icon: Send, note: `${campaigns.filter(c => c.status === "Active").length + 22} currently active`, pos: true },
            { label: "Messages sent today", value: "284,592", change: "+18.6%", icon: MessageSquareText, note: "vs. previous day", pos: true },
            { label: "Delivered today", value: "276,811", change: "97.3%", icon: CheckCircle2, note: "delivery rate", pos: true },
          ].map(({ label, value, change, icon: Icon, note }) => <div key={label} className="rounded-md border border-border bg-card p-5"><div className="flex items-start justify-between"><div className="text-xs font-medium text-muted-foreground">{label}</div><div className="flex size-8 items-center justify-center rounded-md bg-accent text-primary"><Icon className="size-4" /></div></div><div className="mt-3 font-display text-[28px] font-bold leading-none">{value}</div><div className="mt-4 flex items-center gap-2 text-[11px]"><span className="inline-flex items-center gap-0.5 font-bold text-success"><ArrowUpRight className="size-3" />{change}</span><span className="text-muted-foreground">{note}</span></div></div>)}</div>
          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)]"><div className="rounded-md border border-border bg-card p-5 md:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-display text-[16px] font-bold">Message activity</h2><p className="mt-1 text-xs text-muted-foreground">Sending and delivery volume over time</p></div><div className="flex items-center gap-4 text-[11px] text-muted-foreground"><span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-primary" />Sent</span><span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-success/40" />Delivered</span><span className="rounded border border-border px-2 py-1 font-medium">Last 7 days <ChevronDown className="ml-1 inline size-3" /></span></div></div><div className="mt-8 flex h-[200px] gap-3 md:gap-5"><div className="flex h-full flex-col justify-between pb-5 text-[10px] text-muted-foreground"><span>50k</span><span>40k</span><span>30k</span><span>20k</span><span>10k</span><span>0</span></div><div className="chart-bars flex flex-1 items-end justify-around gap-2 pb-5">{[55,69,61,78,70,88,76].map((h, i) => <div key={i} className="relative flex h-full w-full max-w-14 items-end justify-center gap-1"><div className="w-1/3 rounded-t-sm bg-primary transition-all" style={{ height: `${h}%` }} /><div className="w-1/3 rounded-t-sm bg-success/40 transition-all" style={{ height: `${h - 5}%` }} /><span className="absolute -bottom-5 text-[10px] text-muted-foreground">{["Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"][i]}</span></div>)}</div></div></div>
          <div className="rounded-md border border-border bg-card p-5 md:p-6"><div className="flex items-start justify-between"><div><h2 className="font-display text-[16px] font-bold">Campaign status</h2><p className="mt-1 text-xs text-muted-foreground">Across all users</p></div><Button variant="ghost" size="icon" onClick={() => go("Campaigns")} title="View campaigns"><ArrowUpRight /></Button></div><div className="mt-7 flex items-center gap-6"><div className="relative flex size-[140px] shrink-0 items-center justify-center rounded-full" style={{ background: "conic-gradient(var(--primary) 0 54%, var(--success) 54% 82%, var(--warning) 82% 92%, var(--border) 92% 100%)" }}><div className="flex size-[105px] flex-col items-center justify-center rounded-full bg-card"><strong className="font-display text-[25px] leading-none">1,284</strong><span className="mt-1 text-[10px] text-muted-foreground">total</span></div></div><div className="min-w-0 flex-1 space-y-3">{[["Completed", "694", "bg-primary"], ["Active", "360", "bg-success"], ["Paused", "128", "bg-warning"], ["Draft", "102", "bg-border"]].map(([label, count, dot]) => <div key={label} className="flex items-center justify-between gap-3 text-xs"><span className="flex items-center gap-2 text-muted-foreground"><i className={`size-2 rounded-full ${dot}`} />{label}</span><strong className="font-semibold">{count}</strong></div>)}</div></div><div className="mt-6 border-t border-border pt-4 text-[11px] text-muted-foreground">Most campaigns are running smoothly this week.</div></div></div>
          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,1fr)]"><div className="overflow-hidden rounded-md border border-border bg-card"><div className="flex items-center justify-between border-b border-border px-5 py-4"><div><h2 className="font-display text-[16px] font-bold">Recent campaigns</h2><p className="mt-0.5 text-xs text-muted-foreground">Latest activity across your workspace</p></div><Button variant="ghost" size="sm" onClick={() => go("Campaigns")} className="text-primary">View all <ArrowRight className="size-3.5" /></Button></div><div className="overflow-x-auto"><table className="w-full min-w-[570px] text-left text-xs"><thead className="bg-surface text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"><tr><th className="px-5 py-3">CAMPAIGN</th><th className="px-4 py-3">OWNER</th><th className="px-4 py-3">STATUS</th><th className="px-4 py-3 text-right">DELIVERED</th></tr></thead><tbody>{campaigns.slice(0, 5).map((c) => <tr key={c.id} onClick={() => viewCampaign(c)} className="cursor-pointer border-t border-border hover:bg-surface"><td className="px-5 py-3.5"><div className="font-semibold">{c.name}</div><div className="mt-0.5 text-[10px] text-muted-foreground">{c.id}</div></td><td className="px-4 py-3.5 text-muted-foreground">{c.owner}</td><td className="px-4 py-3.5"><Status value={c.status} /></td><td className="px-4 py-3.5 text-right font-medium">{c.delivered}</td></tr>)}</tbody></table></div></div><div className="rounded-md border border-border bg-card p-5"><SectionHeading title="Recent activity" detail="Latest events across the platform" action={<Button variant="ghost" size="icon" onClick={() => go("System Logs")} title="View logs"><ArrowUpRight /></Button>} /><div className="relative ml-2 border-l border-border pl-5">{[
            { icon: Send, text: "Campaign started", sub: "September product launch · Olivia Chen", time: "2 min ago" },
            { icon: Check, text: "Campaign completed", sub: "Appointment reminders · James Okafor", time: "1 hour ago" },
            { icon: Users, text: "New user added", sub: "Daniel Kim · Pulse Media", time: "3 hours ago" },
            { icon: Radio, text: "SMSC connection tested", sub: "Primary gateway · Aisha Patel", time: "5 hours ago" },
          ].map(({ icon: Icon, text, sub, time }) => <div key={text} className="relative mb-5 last:mb-0"><span className="absolute -left-[31px] top-0 flex size-5 items-center justify-center rounded-full border border-border bg-card text-primary"><Icon className="size-2.5" /></span><div className="text-xs font-semibold">{text}</div><div className="mt-1 text-[11px] text-muted-foreground">{sub}</div><div className="mt-1 text-[10px] text-muted-foreground">{time}</div></div>)}</div></div></div>
        </>}

        {page === "Users" && !selectedUser && (
          <UsersManagement
            users={users}
            setUsers={setUsers}
            assignmentOptions={assignmentOptions}
            onPersistUser={persistUser}
            onDeleteUser={removeUser}
            onUpdateAccount={updateAccount}
            onOpenUser={viewUser}
            onNotice={flash}
          />
        )}

        {page === "Users" && selectedUser && <><Button variant="ghost" size="sm" className="mb-5 -ml-3 text-muted-foreground" onClick={() => setSelectedUser(null)}><ArrowLeft /> Back to users</Button><div className="mb-7 flex flex-wrap items-center gap-4"><Avatar name={selectedUser.name} tone={selectedUser.tone} size="lg" /><div><div className="flex items-center gap-3"><h1 className="font-display text-[28px] font-bold">{selectedUser.name}</h1><Status value={selectedUser.status} /></div><p className="text-sm text-muted-foreground">{selectedUser.email} · {selectedUser.company}</p></div><div className="ml-auto flex gap-2"><Button onClick={() => openUserForm(selectedUser)}>Edit user</Button></div></div><div className="admin-scroll mb-6 flex gap-5 overflow-x-auto border-b border-border">{["Profile", "SMSC Accounts", "Sender IDs", "Channels", "TPS", "N-Addresses", "Campaigns"].map(tab => <Button key={tab} variant="ghost" onClick={() => setDetailTab(tab)} className={`h-10 shrink-0 rounded-none border-b-2 px-0 text-xs shadow-none hover:bg-transparent ${detailTab === tab ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>{tab}</Button>)}</div>
          {detailTab === "Profile" && <div className="grid gap-5"><div className="rounded-md border border-border bg-card p-6"><SectionHeading title="Profile information" /><div className="grid gap-y-6 sm:grid-cols-2">{[["Display name", selectedUser.name], ["Email address", selectedUser.email], ["Department", selectedUser.department ?? selectedUser.company], ["Role", selectedUser.role ?? "Campaign Manager"], ["Username", selectedUser.username ?? selectedUser.email.split("@")[0]], ["Last login", selectedUser.login]].map(([key, val]) => <div key={key}><div className="text-[11px] text-muted-foreground">{key}</div><div className="mt-1 text-sm font-medium">{val}</div></div>)}</div><div className="mt-6 border-t border-border pt-5"><div className="text-[11px] text-muted-foreground">Notes</div><p className="mt-1 text-sm">{selectedUser.notes || "No notes added."}</p></div></div></div>}
          {["SMSC Accounts", "Sender IDs", "Channels", "TPS", "N-Addresses"].includes(detailTab) && <AssignedResources page={detailTab as BackendConfigPage} user={selectedUser} options={assignmentOptions} />}
          {detailTab === "Campaigns" && <CampaignTable rows={campaigns.filter(c => c.owner === selectedUser.name)} onOpen={viewCampaign} />}
        </>}

        {page === "Campaigns" && !selectedCampaign && <>
          <PageTitle title="Campaigns" subtitle="View campaign details and delivery status across all users." />
          <div className="mb-4 flex flex-wrap gap-2">
            <div className="relative min-w-[220px] flex-1 sm:max-w-[360px]">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search campaigns or managers..." value={query} onChange={e => setQuery(e.target.value)} className="bg-card pl-9" />
            </div>
            <select aria-label="Filter campaign status" className="h-9 rounded-md border border-input bg-card px-3 text-xs" value={filter} onChange={e => setFilter(e.target.value)}>
              <option>All statuses</option><option>Active</option><option>Completed</option><option>Paused</option><option>Draft</option>
            </select>
          </div>
          <CampaignTable rows={filteredCampaigns} onOpen={viewCampaign} />
        </>}

        {page === "Campaigns" && selectedCampaign && <>
          <Button variant="ghost" size="sm" className="mb-5 -ml-3 text-muted-foreground" onClick={() => setSelectedCampaign(null)}><ArrowLeft /> Back to campaigns</Button>
          <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-3"><h1 className="font-display text-[28px] font-bold">{selectedCampaign.name}</h1><Status value={selectedCampaign.status} /><Status value={selectedCampaign.executionStatus} /></div>
              <p className="text-xs text-muted-foreground">{selectedCampaign.id}</p>
            </div>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <DetailSection title="Campaign information" fields={[["Campaign name", selectedCampaign.name], ["Campaign manager", selectedCampaign.owner], ["Campaign status", selectedCampaign.status], ["Execution status", selectedCampaign.executionStatus], ["Campaign type", selectedCampaign.type], ["Sender ID", selectedCampaign.senderId], ["Channel", selectedCampaign.channel], ["SMSC account", selectedCampaign.smscAccount], ["Created at", selectedCampaign.date]]} />
            <DetailSection title="Audience information" fields={[["Total audience", selectedCampaign.audience], ["Valid recipients", selectedCampaign.audienceValid], ["Invalid recipients", selectedCampaign.audienceInvalid], ["Audience source", selectedCampaign.audienceSource], ["Audience details", selectedCampaign.audienceDescription]]} />
            <DetailSection title="Schedule information" fields={[["Schedule type", selectedCampaign.scheduleType], ["Starts at", selectedCampaign.scheduleStart], ["Ends at", selectedCampaign.scheduleEnd], ["Time zone", selectedCampaign.scheduleTimezone], ["Repeat", selectedCampaign.scheduleRepeat]]} />
            <DetailSection title="Message content">
              <div className="space-y-3">
                {[
                  ["Amharic", selectedCampaign.messageContent.am],
                  ["English", selectedCampaign.messageContent.en],
                  ["Afaan Oromoo", selectedCampaign.messageContent.om],
                  ["Somali", selectedCampaign.messageContent.so],
                  ["Tigrinya", selectedCampaign.messageContent.ti],
                ].map(([language, content]) => (
                  <div key={language}>
                    <h3 className="mb-1 text-xs font-semibold text-muted-foreground">{language}</h3>
                    <p lang={language === "Amharic" ? "am" : language === "English" ? "en" : language === "Afaan Oromoo" ? "om" : language === "Somali" ? "so" : "ti"} className="whitespace-pre-wrap rounded-md bg-surface p-4 text-sm leading-6">{content}</p>
                  </div>
                ))}
              </div>
            </DetailSection>
            <DetailSection title="Execution status" fields={[["Execution status", selectedCampaign.executionStatus], ["Total sent", selectedCampaign.sent], ["Total delivered", selectedCampaign.delivered], ["Failed to send", selectedCampaign.failedSent], ["Failed delivery", selectedCampaign.failedDelivery], ["Delivery rate", selectedCampaign.rate + "%"], ["Execution started", selectedCampaign.executionStartedAt], ["Execution completed", selectedCampaign.executionCompletedAt]]} />
          </div>
        </>}

        {!["Overview", "Users", "Campaigns"].includes(page) && <><PageTitle title={page} subtitle={pageSubtitle(page)} action={["SMSC Accounts", "Sender IDs", "Channels", "TPS", "N-Addresses", "TPS & N-Addresses", "System Logs", "Kafka Monitor"].includes(page) ? undefined : <Button onClick={() => openResource(page)}><Plus /> Add configuration</Button>} />
          {["SMSC Accounts", "Sender IDs", "Channels", "TPS", "N-Addresses"].includes(page) && <BackendConfiguration page={page as BackendConfigPage} users={users} onNotice={flash} />}
          {page === "TPS & N-Addresses" && <div className="grid gap-8"><section><h2 className="mb-4 font-display text-lg font-bold">TPS limits</h2><BackendConfiguration page="TPS" users={users} onNotice={flash} /></section><section><h2 className="mb-4 font-display text-lg font-bold">N-addresses</h2><BackendConfiguration page="N-Addresses" users={users} onNotice={flash} /></section></div>}
          {page === "SMTP" && <ResourceView page={page} extra={resourceRows[page] || []} onAdd={() => openResource(page)} onAction={flash} />}
          {page === "System Logs" && <><div className="mb-4 flex flex-wrap gap-2"><div className="relative min-w-[220px] flex-1 sm:max-w-[330px]"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input placeholder="Search events..." className="bg-card pl-9" value={query} onChange={e => setQuery(e.target.value)} /></div><select aria-label="Filter log type" className="h-9 rounded-md border border-input bg-card px-3 text-xs" value={filter} onChange={e => setFilter(e.target.value)}><option>All statuses</option><option>Campaign</option><option>SMSC</option><option>System</option></select><select aria-label="Filter log user" className="h-9 rounded-md border border-input bg-card px-3 text-xs" onChange={e => setQuery(e.target.value)}><option value="">All users</option>{[...users.map(u => u.name), "Alex Morgan"].map(n => <option key={n}>{n}</option>)}</select><Input type="date" aria-label="Log date" className="w-[145px] bg-card text-xs" /></div><LogList query={query} category={filter} /></>}
          {page === "Kafka Monitor" && <><div className="mb-5 grid gap-3 sm:grid-cols-3">{[["Topics monitored", "2", Radio], ["Events this hour", "42,861", Zap], ["Consumer health", "Healthy", CheckCircle2]].map(([l,v,Icon]) => { const I = Icon as LucideIcon; return <div key={l as string} className="rounded-md border border-border bg-card p-5"><div className="flex justify-between text-xs text-muted-foreground">{l as string}<I className="size-4 text-primary" /></div><div className="mt-2 font-display text-2xl font-bold">{v as string}</div></div>; })}</div><div className="rounded-md border border-border bg-card"><div className="border-b border-border p-5 font-display text-sm font-bold">Consumer groups</div><div className="overflow-x-auto"><table className="w-full min-w-[600px] text-left text-xs"><thead className="bg-surface text-muted-foreground"><tr>{["TOPIC", "CONSUMER GROUP", "CURRENT LAG", "EVENTS / HOUR", "STATUS"].map(h => <th key={h} className="px-5 py-3">{h}</th>)}</tr></thead><tbody>{[["sent-response", "status-updater", "12", "27,480"], ["delivery-report", "dlr-processor", "4", "15,381"]].map(([t,g,l,e]) => <tr key={t} className="border-t border-border"><td className="px-5 py-4 font-mono font-semibold">{t}</td><td className="px-5 py-4">{g}</td><td className="px-5 py-4">{l}</td><td className="px-5 py-4">{e}</td><td className="px-5 py-4"><Status value="Connected" /></td></tr>)}</tbody></table></div></div><div className="mt-5 rounded-md border border-border bg-card p-5"><SectionHeading title="Events per hour" detail="Last 12 hours across both topics" /><div className="flex h-44 items-end gap-2">{[31,28,35,40,38,44,52,47,41,45,49,43].map((v, i) => <div key={i} className="flex flex-1 flex-col items-center gap-2"><div className="w-full rounded-t bg-primary/80" style={{ height: `${v * 2.6}px` }} title={`${v}k events`} /><span className="text-[10px] text-muted-foreground">{String((i + 23) % 24).padStart(2, "0")}h</span></div>)}</div></div></>}
        </>}
      </main>
    </div>

    {editingUserDetails && selectedUser && (
      <UserEditor
        key={selectedUser.profileId}
        users={users}
        user={selectedUser}
        assignmentOptions={assignmentOptions}
        onClose={() => setEditingUserDetails(false)}
        onSave={persistUserDetails}
      />
    )}
    {notice && <div role="status" className="fixed bottom-5 right-5 z-50 flex max-w-sm items-center gap-2 rounded-md border border-border bg-foreground px-4 py-3 text-xs font-medium text-background shadow-lg"><CircleHelp className="size-4 shrink-0" />{notice}<Button variant="ghost" size="icon" className="ml-2 size-5 text-background hover:text-background" onClick={() => setNotice("")} aria-label="Dismiss"><X className="size-3" /></Button></div>}
    {modal && <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4" onMouseDown={e => { if (e.target === e.currentTarget) setModal(null); }}><div role="dialog" aria-modal="true" aria-label={modal === "user" ? "User form" : `Add ${modal}`} className="admin-scroll max-h-[90vh] w-full max-w-[540px] overflow-y-auto rounded-md bg-card shadow-xl"><div className="flex items-center justify-between border-b border-border px-6 py-5"><div><h2 className="font-display text-lg font-bold">{modal === "user" ? editing ? "Edit user" : "Add new user" : `Add ${modal === "SMSC Accounts" ? "SMSC account" : modal === "Sender IDs" ? "sender ID" : modal === "Channels" ? "channel" : "configuration"}`}</h2><p className="mt-1 text-xs text-muted-foreground">Changes are only visible in this preview.</p></div><Button variant="ghost" size="icon" aria-label="Close" onClick={() => setModal(null)}><X /></Button></div><div className="grid gap-4 p-6 sm:grid-cols-2">{modal === "user" ? <><Field label="Display name" value={form.name} onChange={v => setForm({ ...form, name: v })} placeholder="e.g. Taylor Reed" /><Field label="Email address" value={form.email} onChange={v => setForm({ ...form, email: v })} placeholder="name@company.com" type="email" /><Field label="Company" value={form.company} onChange={v => setForm({ ...form, company: v })} placeholder="Company name" /><Field label="Phone" value={form.phone} onChange={v => setForm({ ...form, phone: v })} placeholder="Optional" /><Field label="TPS ceiling" value={form.tps} onChange={v => setForm({ ...form, tps: v })} type="number" /><Field label="N-address limit" value={form.n} onChange={v => setForm({ ...form, n: v })} type="number" /><div className="sm:col-span-2"><Field label="Notes" value={form.notes} onChange={v => setForm({ ...form, notes: v })} placeholder="Internal notes" /></div></> : <><Field label={modal === "Sender IDs" ? "Sender ID" : modal === "Channels" ? "Channel name" : "Name"} value={form.name} onChange={v => setForm({ ...form, name: v })} placeholder={modal === "Sender IDs" ? "e.g. ACME" : "Enter a name"} /><Field label={modal === "SMSC Accounts" ? "Base URL" : modal === "Channels" ? "Code" : modal === "SMTP" ? "Host" : "Description"} value={form.company} onChange={v => setForm({ ...form, company: v })} placeholder={modal === "SMSC Accounts" ? "https://gateway.example.com" : "Optional"} />{modal === "SMSC Accounts" && <><Field label="Username" value={form.email} onChange={v => setForm({ ...form, email: v })} /><Field label="Password" value={form.phone} onChange={v => setForm({ ...form, phone: v })} type="password" /></>}</>}</div><div className="flex justify-end gap-2 border-t border-border px-6 py-4"><Button variant="outline" onClick={() => setModal(null)}>Cancel</Button><Button onClick={() => { if (modal === "user") saveUser(); else if (!form.name.trim()) flash("Enter a name first."); else { setResourceRows(old => ({ ...old, [modal]: [form.name, ...(old[modal] || [])] })); flash("Added to this preview."); setModal(null); } }}>{modal === "user" ? editing ? "Save changes" : "Add user" : "Add"}</Button></div></div></div>}
  </div>;
}

function PageTitle({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) { return <div className="mb-7 flex flex-wrap items-center justify-between gap-4"><div><h1 className="font-display text-[28px] font-bold leading-tight">{title}</h1><p className="mt-1 text-sm text-muted-foreground">{subtitle}</p></div>{action}</div>; }
function Field({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string }) { return <label className="block text-xs font-semibold">{label}<Input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className="mt-2 font-normal" /></label>; }
function CampaignTable({ rows, onOpen }: { rows: Campaign[]; onOpen: (campaign: Campaign) => void }) {
  const columns = ["Campaign", "Campaign manager", "Campaign status", "Execution status", "Total audience", "Type", "Total sent", "Total delivered", "Created at"];
  return <div className="overflow-hidden rounded-md border border-border bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[1250px] text-left text-xs"><thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground"><tr>{columns.map(column => <th key={column} className="whitespace-nowrap px-4 py-3 font-semibold">{column}</th>)}</tr></thead><tbody>{rows.map(c => <tr key={c.id} className="border-t border-border hover:bg-surface"><td className="px-4 py-4"><button type="button" onClick={() => onOpen(c)} className="text-left font-semibold text-primary hover:underline">{c.name}</button><div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{c.id}</div></td><td className="whitespace-nowrap px-4 py-4">{c.owner}</td><td className="px-4 py-4"><Status value={c.status} /></td><td className="px-4 py-4"><Status value={c.executionStatus} /></td><td className="px-4 py-4">{c.audience}</td><td className="whitespace-nowrap px-4 py-4">{c.type}</td><td className="px-4 py-4">{c.sent}</td><td className="px-4 py-4">{c.delivered}</td><td className="whitespace-nowrap px-4 py-4 text-muted-foreground">{c.date}</td></tr>)}</tbody></table>{rows.length === 0 && <Empty />}</div><div className="border-t border-border px-5 py-3 text-xs text-muted-foreground">Showing {rows.length} campaigns</div></div>;
}
function ResourceView({ page, owner, extra, onAction }: { page: string; owner?: User; extra: string[]; onAction: (message: string) => void }) {
  const configPage: ConfigPage = page === "SMSC Accounts" || page === "Sender IDs" ? page : "Channels";
  const configurations = useConfigurationEntries(configPage);
  const ownerEmail = owner?.email;
  const assignedConfigurations = useMemo(
    () => ownerEmail ? configurations.filter(entry => entry.subscriberEmails.includes(ownerEmail)) : [],
    [configurations, ownerEmail],
  );
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedConfigId, setSelectedConfigId] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const isAssignmentView = Boolean(owner);
  const selectableConfigurations = configurations.filter(entry =>
    editingId === entry.id || (entry.active && !entry.subscriberEmails.includes(owner?.email ?? "")),
  );
  const headings = page === "SMSC Accounts"
    ? ["Account", "Base URL", "Auth", "Rate limit", "Status"]
    : page === "Sender IDs"
      ? ["Sender ID", "Name", "Default", "Status"]
      : page === "Channels"
        ? ["Code", "Channel", "Status"]
        : ["Connection", "Host", "Port", "Encryption", "Status"];
  const rows = isAssignmentView
    ? assignedConfigurations.map(entry => ({
        id: entry.id,
        name: entry.values[0] ?? "Configuration",
        values: page === "SMSC Accounts"
          ? [entry.values[0] ?? "", entry.values[2] ?? "", entry.values[3] ?? "", entry.values[4] ?? "", entry.active ? "Active" : "Inactive"]
          : page === "Sender IDs"
            ? [entry.values[0] ?? "", entry.values[1] ?? "", entry.values[3] ?? "", entry.active ? "Active" : "Inactive"]
            : [entry.values[0] ?? "", entry.values[1] ?? "", entry.active ? "Active" : "Inactive"],
      }))
    : [
        { id: "smtp-primary", name: "Primary SMTP", values: ["Primary SMTP", "smtp.relay.example", "587", "TLS", "Active"] },
        { id: "smtp-backup", name: "Backup SMTP", values: ["Backup SMTP", "smtp-backup.relay.example", "465", "SSL", "Active"] },
        ...extra.map(name => ({ id: name, name, values: [name, "—", "—", "—", "Active"] })),
      ];

  const openAddDialog = () => {
    setEditingId(null);
    setSelectedConfigId("");
    setDialogOpen(true);
  };
  const openEditDialog = (id: string) => {
    setEditingId(id);
    setSelectedConfigId(id);
    setDialogOpen(true);
  };
  const closeDialog = () => {
    setDialogOpen(false);
    setEditingId(null);
    setSelectedConfigId("");
  };
  const saveAssignment = () => {
    if (!owner || !selectedConfigId) return;
    const previousId = editingId;
    updateConfigurationEntries(configPage, current => current.map(entry => {
      const removePrevious = previousId !== null && previousId !== selectedConfigId && entry.id === previousId;
      const addSelected = entry.id === selectedConfigId;
      if (!removePrevious && !addSelected) return entry;
      const subscriberEmails = removePrevious
        ? entry.subscriberEmails.filter(email => email !== owner.email)
        : entry.subscriberEmails.includes(owner.email)
          ? entry.subscriberEmails
          : [...entry.subscriberEmails, owner.email];
      return { ...entry, subscriberEmails };
    }));
    onAction(previousId ? `${page} assignment changed for ${owner.name}.` : `${page} added for ${owner.name}.`);
    closeDialog();
  };
  const removeAssignment = (id: string, name: string) => {
    if (!owner || !window.confirm(`Remove ${name} from ${owner.name}'s ${page}?`)) return;
    updateConfigurationEntries(configPage, current => current.map(entry =>
      entry.id === id
        ? { ...entry, subscriberEmails: entry.subscriberEmails.filter(email => email !== owner.email) }
        : entry,
    ));
    onAction(`${name} removed from ${owner.name}'s ${page}.`);
  };

  return (
    <>
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border p-5">
          <div><h2 className="font-display text-sm font-bold">{page}{owner ? ` for ${owner.name}` : ""}</h2><p className="mt-1 text-xs text-muted-foreground">{rows.length} {page.toLowerCase()} assigned</p></div>
          {owner && <Button size="sm" onClick={openAddDialog}><Plus /> Add</Button>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>{headings.map(heading => <th key={heading} className="px-5 py-3 font-semibold">{heading}</th>)}<th className="px-5 py-3 text-right font-semibold">ACTIONS</th></tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.id} className="border-t border-border hover:bg-surface">
                  {row.values.map((cell, index) => <td key={index} className={`px-5 py-4 ${index === 0 ? "font-semibold" : "text-muted-foreground"}`}>{cell === "Active" || cell === "Inactive" ? <Status value={cell} /> : cell}</td>)}
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-2">
                      {owner ? <>
                        <Button variant="outline" size="sm" aria-label={`Edit ${row.name}`} onClick={() => openEditDialog(row.id)}><Pencil /> Edit</Button>
                        <Button variant="outline" size="sm" aria-label={`Remove ${row.name}`} className="text-destructive hover:text-destructive" onClick={() => removeAssignment(row.id, row.name)}><Trash2 /> Remove</Button>
                      </> : <Button variant="ghost" size="icon" title="More actions" onClick={() => onAction("This action is unavailable in the UI-only preview.")}><MoreHorizontal /></Button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <Empty text={`No ${page.toLowerCase()} assigned yet.`} />}
        </div>
      </div>
      {owner && dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
          <div role="dialog" aria-modal="true" aria-label={`${editingId ? "Change" : "Add"} ${page} assignment`} className="w-full max-w-md rounded-md border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="font-display text-lg font-bold">{editingId ? "Change" : "Add"} {page} assignment</h2>
              <Button variant="ghost" size="icon" aria-label="Close" onClick={closeDialog}><X /></Button>
            </div>
            <div className="p-5">
              <label className="block text-xs font-semibold" htmlFor="configuration-assignment">
                Select {page === "SMSC Accounts" ? "SMSC account" : page === "Sender IDs" ? "Sender ID" : "channel"}
              </label>
              <select id="configuration-assignment" aria-label={`Select ${page} configuration`} className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={selectedConfigId} onChange={event => setSelectedConfigId(event.target.value)}>
                <option value="">Select a configuration</option>
                {selectableConfigurations.map(entry => <option key={entry.id} value={entry.id}>{entry.values[0]}</option>)}
              </select>
              {selectableConfigurations.length === 0 && <p className="mt-2 text-xs text-muted-foreground">No unassigned active configurations are available. Create or activate one in {page} first.</p>}
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
              <Button variant="outline" onClick={closeDialog}>Cancel</Button>
              <Button onClick={saveAssignment} disabled={!selectedConfigId || selectedConfigId === editingId}>{editingId ? "Update assignment" : "Add"}</Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
const logEvents = [
  { action: "Campaign activated", detail: "September product launch", user: "Olivia Chen", type: "Campaign", time: "Today, 10:22 AM", status: "Completed" },
  { action: "SMSC connection tested", detail: "Primary gateway", user: "Aisha Patel", type: "SMSC", time: "Today, 09:48 AM", status: "Completed" },
  { action: "Messages built", detail: "Fall welcome series", user: "Marcus Rivera", type: "Campaign", time: "Today, 09:32 AM", status: "Completed" },
  { action: "Campaign completed", detail: "Appointment reminders", user: "James Okafor", type: "Campaign", time: "Today, 08:14 AM", status: "Completed" },
  { action: "Report sent", detail: "Weekly delivery summary", user: "Alex Morgan", type: "System", time: "Yesterday, 05:00 PM", status: "Completed" },
  { action: "Test SMS sent", detail: "Northstar primary", user: "Aisha Patel", type: "SMSC", time: "Yesterday, 02:36 PM", status: "Completed" },
];
function LogList({ filterName, query = "", category = "All statuses" }: { filterName?: string; query?: string; category?: string }) { const rows = logEvents.filter(e => (!filterName || `${e.user} ${e.detail}`.includes(filterName)) && (category === "All statuses" || e.type === category) && `${e.action} ${e.detail} ${e.user}`.toLowerCase().includes(query.toLowerCase())); return <div className="overflow-hidden rounded-md border border-border bg-card"><div className="border-b border-border px-5 py-4 font-display text-sm font-bold">Activity log</div><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground"><tr>{["EVENT", "USER", "TYPE", "TIME", "STATUS"].map(h => <th key={h} className="px-5 py-3">{h}</th>)}</tr></thead><tbody>{rows.map((e,i) => <tr key={i} className="border-t border-border"><td className="px-5 py-4"><strong>{e.action}</strong><span className="mt-1 block text-[11px] text-muted-foreground">{e.detail}</span></td><td className="px-5 py-4">{e.user}</td><td className="px-5 py-4 text-muted-foreground">{e.type}</td><td className="px-5 py-4 text-muted-foreground">{e.time}</td><td className="px-5 py-4"><Status value={e.status} /></td></tr>)}</tbody></table>{rows.length === 0 && <Empty />}</div></div>; }
function pageSubtitle(page: Page) { const subtitles: Partial<Record<Page, string>> = { "SMSC Accounts": "Manage messaging gateways and account connections.", "Sender IDs": "Control sender identities available to your users.", "Channels": "Manage delivery channels and user access.", TPS: "Configure named messages-per-second sending profiles.", "N-Addresses": "Configure named recipient-per-request limit profiles.", "TPS & N-Addresses": "Set default sending and recipient limits for new users.", "SMTP": "Monitor and configure outbound email connections.", "System Logs": "Audit actions and events across the platform.", "Kafka Monitor": "Monitor topic throughput and consumer health." }; return subtitles[page] || ""; }
