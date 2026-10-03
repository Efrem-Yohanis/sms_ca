import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import ListViewToggle, { useListView } from "@/components/ListViewToggle";
import { Users, Eye, ChevronLeft, ChevronRight, Plus, Pencil, Trash2, Search } from "lucide-react";
import { fetchAudiences, fetchAudienceSummary } from "@/lib/api/audiences";
import type { ApiAudienceListItem, AudienceSummary } from "@/lib/api/audiences";
import AudienceFormDialog from "@/components/AudienceFormDialog";
import DeleteAudienceDialog from "@/components/DeleteAudienceDialog";

export default function AudienceList() {
  const [view, setView] = useListView("audiences-view");
  const [audiences, setAudiences] = useState<ApiAudienceListItem[]>([]);
  const [summary, setSummary] = useState<AudienceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const pageSize = 10;

  // Filters
  const [campaignFilter, setCampaignFilter] = useState("");

  // Dialogs
  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; campaignId: number; name: string } | null>(null);

  useEffect(() => {
    loadData();
  }, [page, campaignFilter]);

  async function loadData() {
    setLoading(true);
    try {
      const filters: Record<string, string> = {};
      if (campaignFilter.trim()) filters.campaign = campaignFilter.trim();

      const [listRes, summaryRes] = await Promise.all([
        fetchAudiences(page, pageSize, Object.keys(filters).length ? filters : undefined),
        page === 1 ? fetchAudienceSummary() : Promise.resolve(null),
      ]);
      setAudiences(listRes.results);
      setTotalCount(listRes.count);
      if (summaryRes) setSummary(summaryRes);
    } catch (e) {
      console.error("Failed to load audiences", e);
    } finally {
      setLoading(false);
    }
  }

  function openCreate() {
    setEditId(null);
    setFormOpen(true);
  }

  function openEdit(id: number) {
    setEditId(id);
    setFormOpen(true);
  }

  function openDelete(id: number, campaignId: number, name: string) {
    setDeleteTarget({ id, campaignId, name });
    setDeleteOpen(true);
  }

  function handleMutationSuccess() {
    setPage(1);
    loadData();
  }

  function getRowColor(pct: number) {
    if (pct >= 90) return "border-l-4 border-l-emerald-500";
    if (pct >= 70) return "border-l-4 border-l-amber-500";
    return "border-l-4 border-l-destructive";
  }

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audiences</h1>
          <p className="text-sm text-muted-foreground mt-1">Campaign audience segments and recipients</p>
        </div>
        <div className="flex items-center gap-2">
          <ListViewToggle view={view} onChange={setView} />
          <Link to="/audiences/create">
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              Create Audience
            </Button>
          </Link>
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Audiences</p>
            <p className="text-2xl font-semibold">{summary.total_audiences}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Recipients</p>
            <p className="text-2xl font-semibold">{summary.total_recipients.toLocaleString()}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Valid</p>
            <p className="text-2xl font-semibold text-emerald-600">{summary.total_valid.toLocaleString()}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Avg Valid %</p>
            <p className="text-2xl font-semibold">{summary.avg_valid_percentage.toFixed(1)}%</p>
          </Card>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-3">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={campaignFilter}
            onChange={(e) => {
              setCampaignFilter(e.target.value);
              setPage(1);
            }}
            placeholder="Filter by campaign ID..."
            className="pl-10"
          />
        </div>
      </div>

      {view === "list" ? <Card className="shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Campaign</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Status</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Total</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Valid</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Invalid</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider min-w-[140px]">Valid %</th>
                <th className="text-right px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="px-5 py-3.5"><Skeleton className="h-4 w-20" /></td>
                  ))}
                </tr>
              ))}
              {!loading && audiences.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-16 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
                        <Users className="h-6 w-6 text-muted-foreground" />
                      </div>
                      <p className="text-muted-foreground">No audiences found.</p>
                      <Button variant="outline" size="sm" onClick={openCreate} className="mt-2">
                        <Plus className="h-3.5 w-3.5 mr-1" /> Create one
                      </Button>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && audiences.map((a) => (
                <tr key={a.id} className={`border-b last:border-b-0 hover:bg-accent/50 transition-colors ${getRowColor(a.valid_percentage)}`}>
                  <td className="px-5 py-3.5 font-medium">{a.campaign_info?.name ?? `Campaign #${a.campaign}`}</td>
                  <td className="px-5 py-3.5">
                    <Badge variant="secondary" className="text-xs capitalize">{a.campaign_info?.status ?? "—"}</Badge>
                  </td>
                  <td className="px-5 py-3.5 font-medium">{a.total_count.toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-emerald-600">{a.valid_count.toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-destructive">{a.invalid_count}</td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <Progress value={a.valid_percentage} className="h-2 flex-1" />
                      <span className={`text-xs font-medium min-w-[40px] text-right ${a.valid_percentage >= 90 ? "text-emerald-600" : a.valid_percentage >= 70 ? "text-amber-600" : "text-destructive"}`}>
                        {a.valid_percentage.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Link to={`/audiences/${a.id}`}>
                        <Button variant="ghost" size="icon" className="h-8 w-8" title="View Details">
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                      <Button variant="ghost" size="icon" className="h-8 w-8" title="Edit" onClick={() => openEdit(a.id)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive hover:text-destructive"
                        title="Delete"
                        onClick={() => openDelete(a.id, a.campaign, a.campaign_info?.name ?? `Campaign #${a.campaign}`)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t bg-muted/20">
            <p className="text-xs text-muted-foreground">
              Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount}
            </p>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className="h-8 w-8" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card> : loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => <Card key={index} className="p-5"><Skeleton className="h-5 w-40" /><Skeleton className="mt-4 h-4 w-full" /></Card>)}
        </div>
      ) : audiences.length === 0 ? (
        <Card className="p-12 text-center text-muted-foreground">No audiences found.</Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {audiences.map((a) => (
            <Card key={a.id} className={`space-y-4 p-5 shadow-card ${getRowColor(a.valid_percentage)}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold truncate">{a.campaign_info?.name ?? `Campaign #${a.campaign}`}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Audience #{a.id}</p>
                </div>
                <Badge variant="secondary" className="shrink-0 text-xs capitalize">{a.campaign_info?.status ?? "—"}</Badge>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm">
                <div><p className="text-xs text-muted-foreground">Total</p><p className="font-medium">{a.total_count.toLocaleString()}</p></div>
                <div><p className="text-xs text-muted-foreground">Valid</p><p className="font-medium text-emerald-600">{a.valid_count.toLocaleString()}</p></div>
                <div><p className="text-xs text-muted-foreground">Invalid</p><p className="font-medium text-destructive">{a.invalid_count.toLocaleString()}</p></div>
              </div>
              <div className="flex items-center gap-2">
                <Progress value={a.valid_percentage} className="h-2 flex-1" />
                <span className="min-w-[48px] text-right text-xs font-medium">{a.valid_percentage.toFixed(1)}%</span>
              </div>
              <div className="flex justify-end gap-1 border-t pt-2">
                <Link to={`/audiences/${a.id}`}><Button variant="ghost" size="icon" className="h-8 w-8" title="View Details"><Eye className="h-3.5 w-3.5" /></Button></Link>
                <Button variant="ghost" size="icon" className="h-8 w-8" title="Edit" onClick={() => openEdit(a.id)}><Pencil className="h-3.5 w-3.5" /></Button>
                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="Delete" onClick={() => openDelete(a.id, a.campaign, a.campaign_info?.name ?? `Campaign #${a.campaign}`)}><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Dialogs */}
      <AudienceFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        audienceId={editId}
        onSuccess={handleMutationSuccess}
      />
      <DeleteAudienceDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        campaignId={deleteTarget?.campaignId ?? null}
        audienceName={deleteTarget?.name}
        onSuccess={handleMutationSuccess}
      />
    </div>
  );
}
