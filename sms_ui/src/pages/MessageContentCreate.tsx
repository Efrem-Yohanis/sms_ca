import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { ArrowLeft, Save, Eye } from "lucide-react";
import { fetchSupportedLanguages, createMessageContent } from "@/lib/api/messages";
import type { SupportedLanguage } from "@/lib/api/messages";
import CampaignSelector from "@/components/CampaignSelector";

function calcSmsSegments(text: string): number {
  if (!text) return 0;
  const len = text.length;
  if (len <= 160) return 1;
  return Math.ceil(len / 153);
}

function renderLivePreview(template: string): string {
  return template.replace(/\{name\}/g, "Sample User");
}

export default function MessageContentCreate() {
  const navigate = useNavigate();
  const [languages, setLanguages] = useState<SupportedLanguage[]>([]);
  const [defaultLangFromApi, setDefaultLangFromApi] = useState("en");
  const [loadingLangs, setLoadingLangs] = useState(true);

  const [campaign, setCampaign] = useState("");
  const [content, setContent] = useState<Record<string, string>>({});
  const [defaultLanguage, setDefaultLanguage] = useState("en");
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState("en");

  useEffect(() => {
    fetchSupportedLanguages()
      .then((res) => {
        setLanguages(res.languages);
        setDefaultLangFromApi(res.default);
        setDefaultLanguage(res.default);
        setActiveTab(res.default);
        const initial: Record<string, string> = {};
        res.languages.forEach((l) => (initial[l.code] = ""));
        setContent(initial);
      })
      .catch(() => toast.error("Failed to load supported languages"))
      .finally(() => setLoadingLangs(false));
  }, []);

  async function handleSubmit() {
    if (!campaign.trim()) {
      toast.error("Campaign ID is required");
      return;
    }
    const campaignId = Number(campaign);
    if (isNaN(campaignId) || campaignId <= 0) {
      toast.error("Campaign ID must be a positive number");
      return;
    }
    // Filter out empty content
    const filteredContent: Record<string, string> = {};
    Object.entries(content).forEach(([k, v]) => {
      if (v.trim()) filteredContent[k] = v;
    });
    if (Object.keys(filteredContent).length === 0) {
      toast.error("At least one language must have content");
      return;
    }
    setSubmitting(true);
    try {
      const created = await createMessageContent({
        campaign: campaignId,
        content: filteredContent,
        default_language: defaultLanguage,
      });
      toast.success("Message content created");
      navigate(`/messages/${created.id}`);
    } catch (e: any) {
      toast.error(e.message || "Failed to create");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingLangs) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={() => navigate("/messages")} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-1">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Messages
          </button>
          <h1 className="text-2xl font-semibold tracking-tight">Create Message Content</h1>
        </div>
        <Button onClick={handleSubmit} disabled={submitting} className="gap-1.5">
          <Save className="h-3.5 w-3.5" /> {submitting ? "Creating…" : "Create"}
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="p-5 shadow-card">
          <Label className="text-sm font-medium">Campaign</Label>
          <CampaignSelector
            value={campaign}
            onValueChange={setCampaign}
            className="mt-1.5"
          />
        </Card>
        <Card className="p-5 shadow-card">
          <Label className="text-sm font-medium">Default Language</Label>
          <Select value={defaultLanguage} onValueChange={setDefaultLanguage}>
            <SelectTrigger className="mt-1.5">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {languages.map((l) => (
                <SelectItem key={l.code} value={l.code}>
                  {l.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Card>
        <Card className="p-5 shadow-card">
          <Label className="text-sm font-medium">Languages</Label>
          <div className="flex flex-wrap gap-1 mt-2">
            {languages.map((l) => (
              <Badge key={l.code} variant={content[l.code]?.trim() ? "default" : "outline"} className="text-xs">
                {l.name}
              </Badge>
            ))}
          </div>
        </Card>
      </div>

      <Card className="shadow-card overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b px-5">
            <TabsList className="bg-transparent h-auto p-0 gap-0">
              {languages.map((l) => (
                <TabsTrigger
                  key={l.code}
                  value={l.code}
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-3 text-sm"
                >
                  {l.name}
                  {l.code === defaultLanguage && (
                    <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 py-0">Default</Badge>
                  )}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {languages.map((l) => {
            const text = content[l.code] || "";
            const segments = calcSmsSegments(text);
            const preview = renderLivePreview(text);
            return (
              <TabsContent key={l.code} value={l.code} className="p-5 space-y-4 mt-0">
                <div>
                  <Label className="text-sm font-medium">Message Content ({l.name})</Label>
                  <Textarea
                    value={text}
                    onChange={(e) => setContent({ ...content, [l.code]: e.target.value })}
                    placeholder={`Enter message in ${l.name}. Use {name} for variables.`}
                    rows={5}
                    maxLength={1600}
                    className="mt-1.5"
                  />
                  <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                    <span>{text.length} / 1600 characters</span>
                    <span>{segments} SMS segment{segments !== 1 ? "s" : ""}</span>
                  </div>
                </div>
                {text.trim() && (
                  <div className="rounded-lg border bg-muted/30 p-4">
                    <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-muted-foreground">
                      <Eye className="h-3.5 w-3.5" /> Live Preview
                    </div>
                    <p className="text-sm whitespace-pre-wrap">{preview}</p>
                  </div>
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      </Card>
    </div>
  );
}
