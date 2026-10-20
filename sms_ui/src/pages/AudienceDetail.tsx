import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { LANGUAGE_LABELS } from "@/types/campaign";
import type { Language } from "@/types/campaign";
import { Search, Users, ArrowLeft, Trash2, Copy } from "lucide-react";
import { fetchAudienceDetail, fetchRecipientsPreview } from "@/lib/api/audiences";
import type { ApiAudienceDetail, RecipientsPreview } from "@/lib/api/audiences";
import DeleteAudienceDialog from "@/components/DeleteAudienceDialog";
import { toast } from "sonner";

export default function AudienceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [audience, setAudience] = useState<ApiAudienceDetail | null>(null);
  const [preview, setPreview] = useState<RecipientsPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [searchError, setSearchError] = useState("");

  // Dialogs
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    if (!id) return;
    loadData();
  }, [id]);

  useEffect(() => {
    const query = search.replace(/\D/g, "");
    if (!id) return;
    if (query.length < 9) {
      setPreview(null);
      setSearchError("");
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setSearchError("");
      fetchRecipientsPreview(Number(id), query || undefined)
        .then((result) => { if (!cancelled) setPreview(result); })
        .catch((error) => {
          if (!cancelled) {
            setPreview(null);
            setSearchError(error instanceof Error ? error.message : "Search failed. Check the MSISDN and try again.");
          }
        });
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, search]);

  async function loadData() {
    setLoading(true);
    try {
      const numId = Number(id);
      const detail = await fetchAudienceDetail(numId);
      setAudience(detail);
      setPreview(null);
    } catch (e) {
      console.error("Failed to load audience", e);
    } finally {
      setLoading(false);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-3 gap-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!audience) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-lg mb-4">Audience not found</p>
        <Link to="/audiences"><Button variant="outline">Back to Audiences</Button></Link>
      </div>
    );
  }

  const recipients = preview?.preview ?? [];
  const normalizedSearch = search.replace(/\D/g, "");
  const lookupReady = normalizedSearch.length >= 9;
  const visibleRecipients = normalizedSearch ? recipients : [];
  const matchCount = preview?.matching_count ?? visibleRecipients.length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/audiences" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-1">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Audiences
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">
            Audience — {audience.campaign_info?.name ?? `Campaign #${audience.campaign}`}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-destructive hover:text-destructive" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Recipients</p>
          <p className="text-2xl font-semibold">{audience.total_count.toLocaleString()}</p>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Valid</p>
          <p className="text-2xl font-semibold text-emerald-600">{audience.valid_count.toLocaleString()}</p>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Invalid</p>
          <p className="text-2xl font-semibold text-destructive">{audience.invalid_count}</p>
        </Card>
        <Card className="p-4 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Valid %</p>
          <p className={`text-2xl font-semibold ${audience.valid_percentage >= 90 ? "text-emerald-600" : "text-amber-600"}`}>
            {audience.valid_percentage.toFixed(1)}%
          </p>
        </Card>
      </div>

      {/* Database info */}
      {audience.database_info && (
        <Card className="p-5 shadow-card">
          <h3 className="text-sm font-medium mb-3">Database Info</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-xs text-muted-foreground uppercase mb-1">Table</p>
              <p className="font-mono text-xs">{typeof audience.database_info === "string" ? audience.database_info : audience.database_info.table}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase mb-1">ID Field</p>
              <p className="font-mono text-xs">{typeof audience.database_info === "string" ? "—" : audience.database_info.id_field}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground uppercase mb-1">Filter</p>
              <p className="font-mono text-xs">{typeof audience.database_info === "string" ? "—" : audience.database_info.filter || "—"}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Recipients preview */}
      <Card className="shadow-card overflow-hidden">
        <div className="px-5 py-3 border-b bg-muted/40 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            {normalizedSearch ? `Search Results (showing ${visibleRecipients.length} of ${matchCount})` : "Search recipients by MSISDN"}
          </span>
        </div>

        <div className="p-5">
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by phone number..." className="pl-10" />
          </div>
        </div>

        <div className="px-3 pb-3 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="text-left px-5 py-2 font-medium text-muted-foreground text-xs uppercase">#</th>
              <th className="text-left px-5 py-2 font-medium text-muted-foreground text-xs uppercase">Phone (MSISDN)</th>
              <th className="text-left px-5 py-2 font-medium text-muted-foreground text-xs uppercase">Language</th>
              <th className="text-right px-5 py-2 font-medium text-muted-foreground text-xs uppercase">Copy</th>
            </tr>
          </thead>
          <tbody>
            {visibleRecipients.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-muted-foreground">
                  {searchError || (lookupReady ? "No recipients match your search." : "Enter a full MSISDN to search the audience.")}
                </td>
              </tr>
            )}
            {visibleRecipients.map((r, i) => {
              return (
                <tr key={r.msisdn} className="border-b last:border-b-0 hover:bg-accent/30 transition-colors">
                  <td className="px-5 py-3 text-muted-foreground">{i + 1}</td>
                  <td className="px-5 py-3 font-mono text-xs">{r.msisdn}</td>
                  <td className="px-5 py-3">
                    <Badge variant="outline" className="text-xs">
                      {LANGUAGE_LABELS[r.lang as Language] ?? r.lang}
                    </Badge>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => copyToClipboard(r.msisdn)}>
                      <Copy className="h-3 w-3" />
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </Card>

      {/* Dialogs */}
      <DeleteAudienceDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        campaignId={audience?.campaign ?? null}
        audienceName={audience.campaign_info?.name ?? `Campaign #${audience.campaign}`}
        onSuccess={() => navigate("/audiences")}
      />
    </div>
  );
}
