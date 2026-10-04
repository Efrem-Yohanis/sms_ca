import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  Activity, Check, ChevronLeft, ChevronRight, CircleAlert,
  ClipboardList, Download, Pause, Play, RefreshCw, Search, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchDashboard, type DashboardCampaign, type DashboardData } from "@/lib/api/dashboard";

const STATUS_COLORS: Record<string, string> = {
  active: "#22c55e", draft: "#94a3b8", paused: "#f59e0b",
  completed: "#8b5cf6", cancelled: "#ef4444",
};
const STATUS_BADGES: Record<string, string> = {
  active: "border-green-200 bg-green-50 text-green-800",
  in_progress: "border-green-200 bg-green-50 text-green-800",
  draft: "border-slate-200 bg-slate-100 text-slate-700",
  paused: "border-amber-200 bg-amber-50 text-amber-800",
  stopped: "border-red-200 bg-red-50 text-red-800",
  completed: "border-violet-200 bg-violet-50 text-violet-800",
  cancelled: "border-red-200 bg-red-50 text-red-800",
  archived: "border-slate-200 bg-slate-100 text-slate-700",
};
const EXECUTION_BADGES: Record<string, string> = {
  PENDING: "border-slate-200 bg-slate-100 text-slate-700",
  PROCESSING: "border-green-200 bg-green-50 text-green-800",
  PAUSED: "border-amber-200 bg-amber-50 text-amber-800",
  STOPPED: "border-red-200 bg-red-50 text-red-800",
  COMPLETED: "border-violet-200 bg-violet-50 text-violet-800",
  FAILED: "border-red-200 bg-red-50 text-red-800",
};
const PAGE_SIZE = 50;

function dashboardParams(source: URLSearchParams) {
  const params = new URLSearchParams();
  for (const key of ["page", "sort"]) {
    const value = source.get(key);
    if (value) params.set(key, value);
  }
  params.set("page_size", String(PAGE_SIZE));
  params.set("date_range", "last_30_days");
  return params;
}

function formatNumber(value: number | null | undefined) {
  return value == null ? "—" : Number(value).toLocaleString();
}

function csvValue(value: unknown) {
  const text = Array.isArray(value) ? value.join("; ") : String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

export default function DashboardHome() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [tableSearch, setTableSearch] = useState("");
  const [lastUpdated, setLastUpdated] = useState(Date.now());
  const [now, setNow] = useState(Date.now());
  const page = Math.max(1, Number(searchParams.get("page") ?? 1));
  const sort = searchParams.get("sort") ?? "-updated_at";
  const queryParams = new URLSearchParams({ page: String(page), sort });
  const safeParams = dashboardParams(queryParams);
  const queryString = safeParams.toString();

  const { data, isLoading, error, refetch, isFetching } = useQuery<DashboardData>({
    queryKey: ["campaign-dashboard", queryString],
    queryFn: () => fetchDashboard(safeParams),
    staleTime: 15_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchInterval: autoRefresh ? 60_000 : false,
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    if (!isFetching && data) setLastUpdated(Date.now());
  }, [data, isFetching]);

  useEffect(() => {
    if (searchParams.toString() !== queryString) {
      setSearchParams(new URLSearchParams(queryString), { replace: true });
    }
  }, [queryString, searchParams, setSearchParams]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setSearchParams(dashboardParams(searchParams), { replace: true });
  }, [searchParams, setSearchParams]);

  const updateParams = (changes: Record<string, string | null>, resetPage = true) => {
    setSearchParams((current) => {
      const next = dashboardParams(current);
      for (const [key, value] of Object.entries(changes)) {
        if (value == null || value === "") next.delete(key);
        else next.set(key, value);
      }
      if (resetPage && !("page" in changes)) next.delete("page");
      return next;
    }, { replace: true });
  };

  const filteredCampaigns = useMemo(() => {
    const term = tableSearch.trim().toLowerCase();
    return (data?.campaigns.results ?? []).filter((item) =>
      !term || item.name.toLowerCase().includes(term) || item.owner.toLowerCase().includes(term),
    );
  }, [data?.campaigns.results, tableSearch]);

  const applySort = (field: string) => {
    updateParams({ sort: sort === field ? `-${field}` : field, page: null }, false);
  };

  const exportCsv = () => {
    const headers = ["Campaign Name", ...(data?.viewer.is_superuser ? ["Owner"] : []), "Type", "Sender ID", "Channels", "Status", "Execution Status", "Target Audience", "Success Sent", "Failed Sent", "Success Delivery", "Failed Delivery"];
    const rows = filteredCampaigns.map((item) => [
      item.name, ...(data?.viewer.is_superuser ? [item.owner] : []), item.schedule_type,
      item.sender_id, item.channels, item.status, item.execution_status, item.target_audience,
      item.success_sent, item.failed_sent, item.success_delivery, item.failed_delivery,
    ]);
    const url = URL.createObjectURL(new Blob([[headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "campaigns.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (isLoading) return <DashboardLoading />;
  if (error || !data) return <div className="mx-auto max-w-5xl border border-red-200 bg-card p-8 text-center" role="alert">
    <CircleAlert className="mx-auto mb-3 h-6 w-6 text-red-600" />
    <h1 className="text-lg font-semibold">Could not load dashboard</h1>
    <p className="mt-2 text-sm text-muted-foreground">{error instanceof Error ? error.message : "Please try again."}</p>
    <Button className="mt-5" variant="outline" onClick={() => refetch()}>Retry</Button>
  </div>;

  const statusData = STATUSES.map((key) => ({ key, name: key[0].toUpperCase() + key.slice(1), value: data.status_distribution[key] ?? 0, fill: STATUS_COLORS[key] }));
  const statusTotal = statusData.reduce((total, item) => total + item.value, 0);
  const activityData = [
    { name: "Success Sent", count: data.sent_vs_delivery.success_sent, fill: "#15803d" },
    { name: "Failed Sent", count: data.sent_vs_delivery.failed_sent, fill: "#b91c1c" },
    { name: "Success Delivery", count: data.sent_vs_delivery.success_delivery, fill: "#22c55e" },
    { name: "Failed Delivery", count: data.sent_vs_delivery.failed_delivery, fill: "#ef4444" },
  ];
  const hasCampaigns = data.campaigns.count > 0;
  const pageCount = Math.max(1, Math.ceil(data.campaigns.count / PAGE_SIZE));
  const rangeStart = hasCampaigns ? (page - 1) * PAGE_SIZE + 1 : 0;
  const rangeEnd = Math.min(page * PAGE_SIZE, data.campaigns.count);

  return <div className="space-y-5 pb-8">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">Welcome back, {data.viewer.first_name || "there"}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground" aria-live="polite">Updated {Math.max(0, Math.floor((now - lastUpdated) / 1000))} seconds ago</span>
        <Button variant="outline" size="icon" title={autoRefresh ? "Pause auto-refresh" : "Resume auto-refresh"} aria-label={autoRefresh ? "Pause auto-refresh" : "Resume auto-refresh"} onClick={() => setAutoRefresh((value) => !value)}>{autoRefresh ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</Button>
        <Button variant="outline" size="icon" title="Refresh dashboard" aria-label="Refresh dashboard" disabled={isFetching} onClick={() => refetch()}><RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} /></Button>
      </div>
    </header>

    <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5" aria-label="Campaign totals">
      <KpiCard icon={ClipboardList} label="Total Campaigns" value={data.kpis.total_campaigns} tone="blue" />
      <KpiCard icon={Activity} label="Active Campaigns" value={data.kpis.active_campaigns} tone="green" />
      <KpiCard icon={Sparkles} label="Draft Campaigns" value={data.kpis.draft_campaigns} tone="slate" />
      <KpiCard icon={Pause} label="Paused Campaigns" value={data.kpis.paused_campaigns} tone="amber" />
      <KpiCard icon={Check} label="Completed Campaigns" value={data.kpis.completed_campaigns} tone="violet" />
    </section>

    <section className="grid grid-cols-1 gap-4 xl:grid-cols-2" aria-label="Campaign charts">
      <article className="min-w-0 border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Sent vs Delivery</h2>
        <p className="mt-1 text-xs text-muted-foreground">All time · {data.campaigns.count.toLocaleString()} campaigns</p>
        {activityData.every((item) => item.count === 0) ? <div className="flex h-[245px] items-center justify-center text-sm text-muted-foreground">No data for this period.</div> : <div role="img" aria-label="Sent and delivery successes and failures">
          <ResponsiveContainer width="100%" height={245}><BarChart data={activityData} margin={{ top: 24, right: 12, left: 0, bottom: 12 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="name" interval={0} tick={{ fontSize: 10 }} angle={-14} textAnchor="end" height={48} /><YAxis allowDecimals={false} width={48} tickFormatter={(value: number) => value.toLocaleString()} /><Tooltip formatter={(value: number) => [value.toLocaleString(), "Count"]} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>{activityData.map((item) => <Cell key={item.name} fill={item.fill} />)}<LabelList dataKey="count" position="top" formatter={(value: number) => value.toLocaleString()} className="fill-foreground text-[10px]" /></Bar>
          </BarChart></ResponsiveContainer>
        </div>}
      </article>
      <article className="min-w-0 border border-border bg-card p-4">
        <h2 className="text-sm font-semibold">Campaign Status Distribution</h2><p className="mt-1 text-xs text-muted-foreground">Current status of all campaigns</p>
        {statusTotal === 0 ? <div className="flex h-[245px] items-center justify-center text-sm text-muted-foreground">No campaigns yet.</div> : <>
          <div className="relative h-[190px]" role="img" aria-label="Campaigns by current status"><ResponsiveContainer width="100%" height="100%"><PieChart>
            <Pie data={statusData} dataKey="value" nameKey="name" innerRadius={54} outerRadius={79} paddingAngle={2} strokeWidth={0}>{statusData.map((item) => <Cell key={item.key} fill={item.fill} />)}</Pie>
            <Tooltip formatter={(value: number, _name: string, item) => [`${value.toLocaleString()} (${Math.round(value / statusTotal * 100)}%)`, item.payload.name]} />
          </PieChart></ResponsiveContainer><div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><span className="text-2xl font-semibold tabular-nums">{statusTotal.toLocaleString()}</span><span className="text-[10px] uppercase text-muted-foreground">campaigns</span></div></div>
          <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">{statusData.map((item) => <div key={item.key} className="flex min-w-0 items-center justify-between gap-2 py-1 text-xs"><span className="flex min-w-0 items-center gap-2"><span className="h-2.5 w-2.5 shrink-0" style={{ backgroundColor: item.fill }} /><span className="truncate">{item.name}</span></span><span className="shrink-0 tabular-nums text-muted-foreground">{item.value.toLocaleString()} ({Math.round(item.value / statusTotal * 100)}%)</span></div>)}</div>
        </>}
      </article>
    </section>

    <section aria-labelledby="campaign-table-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 id="campaign-table-title" className="text-lg font-semibold">Campaigns <span className="text-sm font-normal text-muted-foreground">({data.campaigns.count.toLocaleString()})</span></h2>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto"><div className="relative min-w-[200px] flex-1 sm:w-64 sm:flex-none"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search campaigns" placeholder="Search campaigns or owners..." value={tableSearch} onChange={(event) => setTableSearch(event.target.value)} className="pl-9" /></div><Button variant="outline" size="sm" className="gap-2" onClick={exportCsv}><Download className="h-4 w-4" />Export CSV</Button></div>
      </div>
      {!hasCampaigns ? <div className="border border-border bg-card px-5 py-12 text-center"><h3 className="font-semibold">You don&apos;t have any campaigns yet</h3><p className="mt-1 text-sm text-muted-foreground">Create your first campaign to get started.</p><Button asChild className="mt-4"><Link to="/campaigns/new">Create Campaign</Link></Button></div> : filteredCampaigns.length === 0 ? <div className="border border-border bg-card px-5 py-12 text-center"><h3 className="font-semibold">No campaigns match this search</h3><p className="mt-1 text-sm text-muted-foreground">Try a different campaign name or owner.</p></div> : <>
        <div className="hidden overflow-x-auto border border-border bg-card md:block"><table className="w-full min-w-[1120px] table-fixed text-left text-xs"><thead className="border-b bg-muted/40 text-[10px] uppercase text-muted-foreground"><tr>
          <SortHeader label="Campaign Name" field="name" sort={sort} onSort={applySort} className="w-[18%]" />
          {data.viewer.is_superuser && <SortHeader label="Owner" field="owner" sort={sort} onSort={applySort} className="w-[12%]" />}
          <SortHeader label="Type" field="type" sort={sort} onSort={applySort} className="w-[8%]" /><SortHeader label="Sender ID" field="sender_id" sort={sort} onSort={applySort} className="w-[9%]" /><SortHeader label="Channels" field="channels" sort={sort} onSort={applySort} className="w-[10%]" /><SortHeader label="Status" field="status" sort={sort} onSort={applySort} className="w-[8%]" /><SortHeader label="Exec Status" field="execution_status" sort={sort} onSort={applySort} className="w-[10%]" /><SortHeader label="Target Audience" field="target_audience" sort={sort} onSort={applySort} className="w-[8%] text-right" /><SortHeader label="Success Sent" field="success_sent" sort={sort} onSort={applySort} className="w-[7%] text-right" /><SortHeader label="Failed Sent" field="failed_sent" sort={sort} onSort={applySort} className="w-[7%] text-right" /><SortHeader label="Success Delivery" field="success_delivery" sort={sort} onSort={applySort} className="w-[8%] text-right" /><SortHeader label="Failed Delivery" field="failed_delivery" sort={sort} onSort={applySort} className="w-[8%] text-right" />
        </tr></thead><tbody>{filteredCampaigns.map((item) => <CampaignRow key={item.id} item={item} showOwner={data.viewer.is_superuser} onOpen={() => navigate(`/campaigns/${item.id}`)} />)}</tbody></table></div>
        <div className="space-y-2 md:hidden">{filteredCampaigns.map((item) => <CampaignCard key={item.id} item={item} showOwner={data.viewer.is_superuser} onOpen={() => navigate(`/campaigns/${item.id}`)} />)}</div>
      </>}
      {hasCampaigns && <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground"><span>Showing {rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} of {data.campaigns.count.toLocaleString()}</span><div className="flex items-center gap-2"><Button variant="outline" size="icon" className="h-8 w-8" aria-label="Previous page" disabled={page <= 1} onClick={() => updateParams({ page: String(page - 1) }, false)}><ChevronLeft className="h-4 w-4" /></Button><span>Page {page} of {pageCount}</span><Button variant="outline" size="icon" className="h-8 w-8" aria-label="Next page" disabled={page >= pageCount} onClick={() => updateParams({ page: String(page + 1) }, false)}><ChevronRight className="h-4 w-4" /></Button></div></div>}
    </section>
  </div>;
}

function KpiCard({ icon: Icon, label, value, tone }: { icon: typeof ClipboardList; label: string; value: number; tone: string }) {
  const colors: Record<string, string> = { blue: "border-sky-200 bg-sky-50/70 text-sky-900", green: "border-green-200 bg-green-50/70 text-green-900", slate: "border-slate-200 bg-slate-50 text-slate-900", amber: "border-amber-200 bg-amber-50/70 text-amber-900", violet: "border-violet-200 bg-violet-50/70 text-violet-900" };
  return <div className={`min-h-[112px] border p-4 text-left ${colors[tone]}`}><span className="flex items-center justify-between gap-2"><Icon className="h-4 w-4 opacity-75" aria-hidden="true" /><span className="text-[10px] font-semibold uppercase text-muted-foreground">{label}</span></span><span className="mt-3 block text-3xl font-semibold tabular-nums">{value.toLocaleString()}</span><span className="mt-1 block text-[10px] text-muted-foreground">— no historical baseline</span></div>;
}

function SortHeader({ label, field, sort, onSort, className = "" }: { label: string; field: string; sort: string; onSort: (field: string) => void; className?: string }) {
  const active = sort === field || sort === `-${field}`;
  return <th className={`px-2 py-3 ${className}`}><button type="button" className="inline-flex items-center gap-1 text-left hover:text-foreground" onClick={() => onSort(field)}>{label}<span aria-hidden="true" className="text-[9px]">{active ? sort.startsWith("-") ? "↓" : "↑" : "↕"}</span></button></th>;
}

function CampaignRow({ item, showOwner, onOpen }: { item: DashboardCampaign; showOwner: boolean; onOpen: () => void }) {
  return <tr role="link" tabIndex={0} aria-label={`Open ${item.name}`} onClick={onOpen} onKeyDown={(event: KeyboardEvent<HTMLTableRowElement>) => { if (event.key === "Enter") onOpen(); }} className="cursor-pointer border-b last:border-0 hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
    <td className="px-2 py-3 font-medium"><Link to={`/campaigns/${item.id}`} title={item.name} onClick={(event) => event.stopPropagation()} className="block truncate hover:underline">{item.name}</Link></td>
    {showOwner && <td className="truncate px-2 py-3 text-muted-foreground" title={item.owner}>{item.owner || "—"}</td>}
    <td className="px-2 py-3 capitalize">{item.schedule_type ?? "—"}</td><td className="truncate px-2 py-3">{item.sender_id || "—"}</td>
    <td className="px-2 py-3"><ChannelBadges channels={item.channels ?? []} /></td><td className="px-2 py-3"><StatusBadge status={item.status} /></td><td className="px-2 py-3"><StatusBadge status={item.execution_status} execution /></td>
    <NumberCell value={item.target_audience} /><NumberCell value={item.success_sent} tone="green" /><NumberCell value={item.failed_sent} tone="red" /><NumberCell value={item.success_delivery} tone="green" /><NumberCell value={item.failed_delivery} tone="red" />
  </tr>;
}

function NumberCell({ value, tone = "muted" }: { value: number | null; tone?: string }) {
  const color = value == null || value === 0 ? "text-muted-foreground" : tone === "green" ? "text-green-700" : tone === "red" ? "text-red-700" : "text-foreground";
  return <td className={`px-2 py-3 text-right tabular-nums ${color}`}>{formatNumber(value)}</td>;
}

function StatusBadge({ status, execution = false }: { status: string; execution?: boolean }) {
  const normalized = status || "PENDING";
  const key = execution ? normalized.toUpperCase() : normalized.toLowerCase();
  const color = execution ? EXECUTION_BADGES[key] : STATUS_BADGES[key];
  return <span className={`inline-flex max-w-full truncate border px-1.5 py-0.5 text-[10px] font-medium capitalize ${color ?? "border-border bg-muted text-muted-foreground"}`}>{normalized.replace(/_/g, " ")}</span>;
}

function ChannelBadges({ channels }: { channels: string[] }) {
  return channels.length ? <div className="flex flex-wrap gap-1">{channels.slice(0, 3).map((channel) => <span key={channel} className="border border-border bg-muted/60 px-1.5 py-0.5 text-[10px]">{channel}</span>)}{channels.length > 3 && <span className="text-muted-foreground">+{channels.length - 3}</span>}</div> : <span className="text-muted-foreground">—</span>;
}

function CampaignCard({ item, showOwner, onOpen }: { item: DashboardCampaign; showOwner: boolean; onOpen: () => void }) {
  return <button type="button" onClick={onOpen} className="w-full border border-border bg-card p-4 text-left hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><span className="block truncate font-semibold" title={item.name}>{item.name}</span>{showOwner && <span className="mt-1 block truncate text-xs text-muted-foreground">{item.owner}</span>}<span className="mt-2 flex flex-wrap items-center gap-1.5"><StatusBadge status={item.status} /><StatusBadge status={item.execution_status} execution /></span><span className="mt-2 block text-xs text-muted-foreground">{item.channels.join(" · ") || "No channels"} · {item.sender_id || "No sender"}</span><span className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs"><span>Audience: <b className="font-medium">{formatNumber(item.target_audience)}</b></span><span>Type: <b className="font-medium capitalize">{item.schedule_type ?? "—"}</b></span><span>Sent: <b className="font-medium text-green-700">{formatNumber(item.success_sent)}</b> / <b className="font-medium text-red-700">{formatNumber(item.failed_sent)}</b></span><span>Delivered: <b className="font-medium text-green-700">{formatNumber(item.success_delivery)}</b> / <b className="font-medium text-red-700">{formatNumber(item.failed_delivery)}</b></span></span></button>;
}

function DashboardLoading() {
  return <div className="space-y-5" aria-label="Loading dashboard"><div className="flex items-center justify-between"><div><Skeleton className="h-7 w-36" /><Skeleton className="mt-2 h-4 w-52" /></div><Skeleton className="h-9 w-36" /></div><div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">{Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-28" />)}</div><div className="grid gap-4 xl:grid-cols-2">{Array.from({ length: 2 }, (_, index) => <Skeleton key={index} className="h-[320px]" />)}</div><div className="space-y-2">{Array.from({ length: 5 }, (_, index) => <Skeleton key={index} className="h-10" />)}</div></div>;
}