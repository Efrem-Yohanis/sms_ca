import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import {
  TrendingUp, Zap, CheckCircle2, Users, Send, AlertTriangle,
  Plus, ArrowRight, BarChart3, Target, RefreshCw,
} from "lucide-react";
import { fetchDashboardSummary, type DashboardSummary } from "@/lib/api/dashboard";
import { fetchCampaigns, type ApiCampaign } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";

const STATUS_COLORS: Record<string, string> = {
  draft: "hsl(220 10% 60%)",
  active: "hsl(152 60% 45%)",
  paused: "hsl(40 90% 50%)",
  completed: "hsl(220 72% 50%)",
  archived: "hsl(220 10% 75%)",
};

const STATUS_BADGE_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  completed: "secondary",
  draft: "outline",
  paused: "destructive",
};

export default function Dashboard() {
  const { data: summary, isLoading: summaryLoading, refetch } = useQuery<DashboardSummary>({
    queryKey: ["dashboard-summary"],
    queryFn: fetchDashboardSummary,
    refetchInterval: 30000,
  });

  const { data: activeCampaigns, isLoading: activeLoading } = useQuery({
    queryKey: ["campaigns-active"],
    queryFn: () => fetchCampaigns({ page: 1, pageSize: 5 }),
    select: (data) => data.results.filter((c: ApiCampaign) => c.status === "active" || c.execution_status === "running"),
    refetchInterval: 15000,
  });

  const loading = summaryLoading;

  const statusData = summary?.by_status
    ? Object.entries(summary.by_status)
        .filter(([, v]) => v > 0)
        .map(([status, count]) => ({
          name: status.charAt(0).toUpperCase() + status.slice(1),
          value: count,
          fill: STATUS_COLORS[status] ?? "hsl(220 10% 60%)",
        }))
    : [];

  const deliveryData = summary
    ? [
        { name: "Delivered", value: summary.total_delivered, fill: "hsl(152 60% 45%)" },
        { name: "Failed", value: summary.total_failed, fill: "hsl(0 72% 51%)" },
        { name: "Pending", value: Math.max(0, summary.total_sent - summary.total_delivered - summary.total_failed), fill: "hsl(40 90% 50%)" },
      ].filter((d) => d.value > 0)
    : [];

  if (loading) {
    return (
      <div className="space-y-8">
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-10 w-36" />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-5 pb-5"><Skeleton className="h-4 w-20 mb-3" /><Skeleton className="h-8 w-16" /></CardContent></Card>
          ))}
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {Array.from({ length: 2 }).map((_, i) => (
            <Card key={i}><CardContent className="pt-6"><Skeleton className="h-64 w-full" /></CardContent></Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">Overview of your campaign performance</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => refetch()} title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Link to="/campaigns/new">
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              Create campaign
            </Button>
          </Link>
        </div>
      </div>

      {/* KPI Cards - Row 1: Campaign stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard icon={BarChart3} label="Total Campaigns" value={summary?.total_campaigns ?? 0} />
        <KPICard icon={Zap} label="Active" value={summary?.active_campaigns ?? 0} accent />
        <KPICard icon={CheckCircle2} label="Completed" value={summary?.completed_campaigns ?? 0} />
        <KPICard icon={TrendingUp} label="Draft" value={summary?.draft_campaigns ?? 0} />
      </div>

      {/* KPI Cards - Row 2: Delivery stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard icon={Users} label="Total Recipients" value={(summary?.total_recipients ?? 0).toLocaleString()} />
        <KPICard icon={Send} label="Total Sent" value={(summary?.total_sent ?? 0).toLocaleString()} />
        <KPICard icon={Target} label="Delivery Rate" value={`${summary?.avg_delivery_rate?.toFixed(1) ?? 0}%`} accent />
        <KPICard icon={AlertTriangle} label="Failed" value={(summary?.total_failed ?? 0).toLocaleString()} destructive />
      </div>

      {/* Charts Row */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Status Distribution */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Campaign Status Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {statusData.length === 0 ? (
              <div className="h-[260px] flex items-center justify-center text-muted-foreground text-sm">No data available</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={statusData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={85} innerRadius={50} paddingAngle={3} strokeWidth={0}
                    label={({ name, value }) => `${name}: ${value}`}>
                    {statusData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: "0.5rem", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Delivery Breakdown */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Message Delivery Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            {deliveryData.length === 0 ? (
              <div className="h-[260px] flex items-center justify-center text-muted-foreground text-sm">No delivery data</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={deliveryData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip contentStyle={{ borderRadius: "0.5rem", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {deliveryData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Active Campaigns + Recent */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Active Campaigns */}
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground">Active Campaigns</CardTitle>
            <Link to="/campaigns" className="text-xs text-primary hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </CardHeader>
          <CardContent>
            {activeLoading ? (
              <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}</div>
            ) : !activeCampaigns?.length ? (
              <p className="text-sm text-muted-foreground text-center py-8">No active campaigns</p>
            ) : (
              <div className="space-y-3">
                {activeCampaigns.map((c: ApiCampaign) => {
                  const progress = typeof c.progress === "object" ? c.progress.progress_percent : 0;
                  return (
                    <Link key={c.id} to={`/campaigns/${c.id}`} className="block p-3 border border-border rounded-lg hover:bg-accent/50 transition-colors">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium truncate mr-2">{c.name}</span>
                        <Badge variant={STATUS_BADGE_VARIANT[c.status] ?? "secondary"} className="text-xs capitalize shrink-0">{c.execution_status_display || c.status}</Badge>
                      </div>
                      <div className="flex items-center gap-3">
                        <Progress value={progress} className="h-2 flex-1" />
                        <span className="text-xs text-muted-foreground font-medium w-10 text-right">{progress}%</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Campaigns */}
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium text-muted-foreground">Recent Campaigns</CardTitle>
            <Link to="/campaigns" className="text-xs text-primary hover:underline flex items-center gap-1">
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </CardHeader>
          <CardContent>
            {!summary?.recent_campaigns?.length ? (
              <p className="text-sm text-muted-foreground text-center py-8">No campaigns yet</p>
            ) : (
              <div className="space-y-1">
                {summary.recent_campaigns.map((c) => (
                  <Link key={c.id} to={`/campaigns/${c.id}`} className="flex items-center justify-between py-2.5 hover:bg-accent rounded-lg px-3 -mx-3 transition-colors">
                    <div className="min-w-0 mr-3">
                      <p className="text-sm font-medium truncate">{c.name}</p>
                      <p className="text-xs text-muted-foreground">{formatDistanceToNow(new Date(c.updated_at), { addSuffix: true })}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant={STATUS_BADGE_VARIANT[c.status] ?? "secondary"} className="text-xs capitalize">{c.status}</Badge>
                      {c.progress_percent > 0 && (
                        <span className="text-xs text-muted-foreground">{c.progress_percent}%</span>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function KPICard({ icon: Icon, label, value, accent, destructive }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | string;
  accent?: boolean;
  destructive?: boolean;
}) {
  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="pt-5 pb-5">
        <div className="flex items-center justify-between mb-3">
          <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${
            destructive ? "bg-destructive/10" : accent ? "bg-primary/10" : "bg-muted"
          }`}>
            <Icon className={`h-4 w-4 ${
              destructive ? "text-destructive" : accent ? "text-primary" : "text-muted-foreground"
            }`} />
          </div>
        </div>
        <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
        <p className={`text-2xl font-bold tracking-tight ${
          destructive ? "text-destructive" : accent ? "text-primary" : ""
        }`}>{value}</p>
      </CardContent>
    </Card>
  );
}
