import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import ListViewToggle, { useListView } from "@/components/ListViewToggle";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LANGUAGE_LABELS, SUPPORTED_LANGUAGES } from "@/types/campaign";
import type { Language } from "@/types/campaign";
import { Plus, MessageSquareText, Eye, Pencil, Trash2, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { fetchMessageContents, deleteMessageContentById } from "@/lib/api/messages";
import type { ApiMessageContentListItem } from "@/lib/api/messages";
import { toast } from "sonner";

export default function MessageContentList() {
  const navigate = useNavigate();
  const [view, setView] = useListView("messages-view");
  const [messages, setMessages] = useState<ApiMessageContentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const pageSize = 10;

  // Filters
  const [search, setSearch] = useState("");
  const [filterLang, setFilterLang] = useState("all");
  const [filterCompleteness, setFilterCompleteness] = useState("all");

  const [deleteTarget, setDeleteTarget] = useState<ApiMessageContentListItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const buildFilters = useCallback(() => {
    const filters: Record<string, string> = {};
    if (search.trim()) filters.search = search.trim();
    if (filterLang !== "all") filters.default_language = filterLang;
    if (filterCompleteness !== "all") filters.completeness = filterCompleteness;
    return filters;
  }, [search, filterLang, filterCompleteness]);

  useEffect(() => { loadData(); }, [page, filterLang, filterCompleteness]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      loadData();
    }, 400);
    return () => clearTimeout(timer);
  }, [search]);

  async function loadData() {
    setLoading(true);
    try {
      const filters = buildFilters();
      const listRes = await fetchMessageContents(page, pageSize, Object.keys(filters).length > 0 ? filters : undefined);
      setMessages(listRes.results);
      setTotalCount(listRes.count);
      setLoadError(false);
    } catch (e) {
      console.error("Failed to load message contents", e);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteMessageContentById(deleteTarget.id);
      toast.success("Message content deleted");
      setDeleteTarget(null);
      loadData();
    } catch (e: any) {
      toast.error(e.message || "Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  function clearFilters() {
    setSearch("");
    setFilterLang("all");
    setFilterCompleteness("all");
    setPage(1);
  }

  const hasActiveFilters = search.trim() !== "" || filterLang !== "all" || filterCompleteness !== "all";
  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Message Content</h1>
          <p className="text-sm text-muted-foreground mt-1">Campaign message templates and translations</p>
        </div>
        <div className="flex items-center gap-2">
          <ListViewToggle view={view} onChange={setView} />
          <Link to="/messages/create">
            <Button className="gap-2 shadow-soft">
              <Plus className="h-4 w-4" /> Create New
            </Button>
          </Link>
        </div>
      </div>

      {totalCount > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Messages</p>
            <p className="text-2xl font-semibold">{totalCount}</p>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">By Default Language</p>
            <div className="flex flex-wrap gap-1 mt-1">
              {Object.entries(
                messages.reduce<Record<string, number>>((acc, m) => {
                  acc[m.default_language] = (acc[m.default_language] || 0) + 1;
                  return acc;
                }, {})
              ).map(([lang, count]) => (
                <Badge key={lang} variant="outline" className="text-xs">
                  {LANGUAGE_LABELS[lang as Language] ?? lang}: {count}
                </Badge>
              ))}
            </div>
          </Card>
          <Card className="p-4 shadow-card">
            <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Languages Used</p>
            <div className="flex flex-wrap gap-1 mt-1">
              {[...new Set(messages.flatMap(m => m.languages_available))].map((lang) => (
                <Badge key={lang} variant="secondary" className="text-xs">{LANGUAGE_LABELS[lang as Language] ?? lang}</Badge>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Search & Filters */}
      <Card className="p-4 shadow-card">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by campaign name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={filterLang} onValueChange={(v) => { setFilterLang(v); setPage(1); }}>
            <SelectTrigger className="w-full sm:w-[180px]">
              <SelectValue placeholder="Language" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Languages</SelectItem>
              {SUPPORTED_LANGUAGES.map((l) => (
                <SelectItem key={l} value={l}>{LANGUAGE_LABELS[l]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={filterCompleteness} onValueChange={(v) => { setFilterCompleteness(v); setPage(1); }}>
            <SelectTrigger className="w-full sm:w-[180px]">
              <SelectValue placeholder="Completeness" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="complete">Complete</SelectItem>
              <SelectItem value="partial">Partial</SelectItem>
              <SelectItem value="empty">Empty</SelectItem>
            </SelectContent>
          </Select>
          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="gap-1.5 shrink-0">
              <X className="h-3.5 w-3.5" /> Clear
            </Button>
          )}
        </div>
      </Card>

      {view === "list" ? <Card className="shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Campaign</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Default</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Languages</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Completeness</th>
                <th className="text-left px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Preview</th>
                <th className="text-right px-5 py-3.5 font-medium text-muted-foreground text-xs uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 6 }).map((_, j) => (
                    <td key={j} className="px-5 py-3.5"><Skeleton className="h-4 w-20" /></td>
                  ))}
                </tr>
              ))}
              {!loading && messages.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-16 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted">
                        <MessageSquareText className="h-6 w-6 text-muted-foreground" />
                      </div>
                      <p className="text-muted-foreground">
                        {loadError ? "Could not load message content." : hasActiveFilters ? "No results match your filters." : "No message content found."}
                      </p>
                      {loadError ? (
                        <Button variant="outline" size="sm" className="mt-2" onClick={loadData}>
                          Retry
                        </Button>
                      ) : hasActiveFilters ? (
                        <Button variant="outline" size="sm" className="mt-2 gap-1.5" onClick={clearFilters}>
                          <X className="h-3.5 w-3.5" /> Clear filters
                        </Button>
                      ) : (
                        <Link to="/messages/create">
                          <Button variant="outline" size="sm" className="mt-2 gap-1.5">
                            <Plus className="h-3.5 w-3.5" /> Create your first message
                          </Button>
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              )}
              {!loading && messages.map((m) => {
                const langCount = m.languages_available?.length || Object.keys(m.content).length;
                const totalLangs = 5; // en, am, ti, om, so
                const completeness = Math.round((langCount / totalLangs) * 100);
                return (
                  <tr key={m.id} className="border-b last:border-b-0 hover:bg-accent/50 transition-colors">
                    <td className="px-5 py-3.5 font-medium">
                      Campaign #{m.campaign}
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge variant="outline" className="text-xs">{LANGUAGE_LABELS[m.default_language as Language] ?? m.default_language}</Badge>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex gap-1 flex-wrap">
                        {m.languages_available.map((l) => (
                          <Badge key={l} variant="secondary" className="text-xs">{LANGUAGE_LABELS[l as Language] ?? l}</Badge>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`text-xs font-medium ${completeness === 100 ? "text-emerald-600" : "text-amber-600"}`}>
                        {completeness}%
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-muted-foreground truncate max-w-[200px] text-xs">
                      {m.preview && typeof m.preview === "object" ? m.preview.preview?.slice(0, 60) : "—"}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(`/messages/${m.id}`)}>
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => navigate(`/messages/${m.id}/edit`)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" onClick={() => setDeleteTarget(m)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

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
      ) : messages.length === 0 ? (
        <Card className="p-12 text-center text-muted-foreground">
          {loadError ? "Could not load message content." : hasActiveFilters ? "No results match your filters." : "No message content found."}
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {messages.map((m) => {
            const langCount = m.languages_available?.length || Object.keys(m.content).length;
            const completeness = Math.round((langCount / 5) * 100);
            const preview = m.preview && typeof m.preview === "object" ? m.preview.preview : "";
            return (
              <Card key={m.id} className="flex min-h-[220px] flex-col justify-between gap-4 p-5 shadow-card">
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><p className="font-semibold truncate">{m.campaign_name || `Campaign #${m.campaign}`}</p><p className="mt-1 text-xs text-muted-foreground">Message #{m.id}</p></div>
                    <Badge variant="outline" className="shrink-0 text-xs">{LANGUAGE_LABELS[m.default_language as Language] ?? m.default_language}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {m.languages_available.map((language) => <Badge key={language} variant="secondary" className="text-xs">{LANGUAGE_LABELS[language as Language] ?? language}</Badge>)}
                  </div>
                  <p className="line-clamp-3 min-h-12 text-sm text-muted-foreground">{preview || "No preview available"}</p>
                  <p className={`text-xs font-medium ${completeness === 100 ? "text-emerald-600" : "text-amber-600"}`}>{completeness}% complete</p>
                </div>
                <div className="flex justify-end gap-1 border-t pt-2">
                  <Button variant="ghost" size="icon" className="h-8 w-8" title="View" onClick={() => navigate(`/messages/${m.id}`)}><Eye className="h-3.5 w-3.5" /></Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8" title="Edit" onClick={() => navigate(`/messages/${m.id}/edit`)}><Pencil className="h-3.5 w-3.5" /></Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" title="Delete" onClick={() => setDeleteTarget(m)}><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Message Content</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete message content for "Campaign #{deleteTarget?.campaign}"? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
