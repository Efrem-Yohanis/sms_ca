import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LANGUAGE_LABELS } from "@/types/campaign";
import type { Language } from "@/types/campaign";
import { toast } from "sonner";
import { Pencil, Trash2, ArrowLeft } from "lucide-react";
import { fetchMessageContentDetail, deleteMessageContentById } from "@/lib/api/messages";
import type { ApiMessageContentListItem } from "@/lib/api/messages";

function calcSmsSegments(text: string): number {
  if (!text) return 0;
  return text.length <= 160 ? 1 : Math.ceil(text.length / 153);
}

export default function MessageContentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [mc, setMc] = useState<ApiMessageContentListItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("en");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (id) loadData();
  }, [id]);

  async function loadData() {
    setLoading(true);
    try {
      const data = await fetchMessageContentDetail(Number(id));
      setMc(data);
      setActiveTab(data.default_language);
    } catch (e) {
      console.error("Failed to load message content", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteMessageContentById(Number(id));
      toast.success("Message content deleted");
      navigate("/messages");
    } catch (e: any) {
      toast.error(e.message || "Failed to delete");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-64" /></div>;
  }

  if (!mc) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
        <p className="text-lg mb-4">Message content not found</p>
        <Link to="/messages"><Button variant="outline">Back to Messages</Button></Link>
      </div>
    );
  }

  const langs = mc.languages_available.length > 0 ? mc.languages_available : Object.keys(mc.content);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/messages" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-1">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Messages
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">
            Message #{mc.id} — Campaign #{mc.campaign}
          </h1>
        </div>
        <div className="flex gap-2">
          <Link to={`/messages/${mc.id}/edit`}>
            <Button variant="outline" size="sm" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Edit</Button>
          </Link>
          <Button variant="destructive" size="sm" className="gap-1.5" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
        </div>
      </div>

      {/* Meta cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Campaign</p>
          <p className="font-medium">#{mc.campaign}</p>
        </Card>
        <Card className="p-5 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Default Language</p>
          <Badge variant="outline">{LANGUAGE_LABELS[mc.default_language as Language] ?? mc.default_language}</Badge>
        </Card>
        <Card className="p-5 shadow-card">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Languages</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {langs.map((l) => (
              <Badge key={l} variant="secondary" className="text-xs">{LANGUAGE_LABELS[l as Language] ?? l}</Badge>
            ))}
          </div>
        </Card>
      </div>

      {/* Language tabs with content */}
      <Card className="shadow-card overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b px-5">
            <TabsList className="bg-transparent h-auto p-0 gap-0">
              {langs.map((l) => (
                <TabsTrigger key={l} value={l} className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-3 text-sm">
                  {LANGUAGE_LABELS[l as Language] ?? l}
                  {l === mc.default_language && <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0">Default</Badge>}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {langs.map((l) => {
            const text = mc.content[l] || "";
            const segments = calcSmsSegments(text);
            return (
              <TabsContent key={l} value={l} className="p-5 space-y-4 mt-0">
                {text.trim() ? (
                  <>
                    <p className="text-sm whitespace-pre-wrap">{text}</p>
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                      <span>{text.length} characters</span>
                      <span>{segments} SMS segment{segments !== 1 ? "s" : ""}</span>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground italic">No content for this language</p>
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      </Card>

      {/* Delete dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Message Content</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this message content? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
