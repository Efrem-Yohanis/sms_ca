import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, RefreshCw, RotateCcw, Send, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Section } from "@/components/campaign-detail/Section";
import { fetchEmailServices, type EmailService } from "@/lib/api/configurations";
import {
  fetchCampaignReportHistory,
  resendCampaignReport,
  sendCampaignReport,
  type ReportDeliveryLog,
} from "@/lib/api/reports";

interface Props {
  campaignId: number;
  campaignName: string;
  ownerEmails: string[];
}

const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function CampaignReports({ campaignId, campaignName, ownerEmails }: Props) {
  const [recipients, setRecipients] = useState<string[]>([]);
  const [recipientDraft, setRecipientDraft] = useState("");
  const [alsoOwners, setAlsoOwners] = useState(false);
  const [subject, setSubject] = useState(`${campaignName} - Reports`);
  const [emailServices, setEmailServices] = useState<EmailService[]>([]);
  const [emailConfigId, setEmailConfigId] = useState("");
  const [loadingServices, setLoadingServices] = useState(true);
  const [format, setFormat] = useState<"text" | "html" | "csv" | "pdf">("html");
  const [history, setHistory] = useState<ReportDeliveryLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [sendResult, setSendResult] = useState<{ status: "sent" | "failed"; message: string; logId?: number } | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      setHistory(await fetchCampaignReportHistory(campaignId));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load report history");
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    setSubject(`${campaignName} - Reports`);
    setRecipients([]);
    setAlsoOwners(false);
    setSendResult(null);
  }, [campaignId, campaignName]);

  useEffect(() => {
    let mounted = true;
    fetchEmailServices()
      .then(({ results }) => {
        const active = results.filter((service) => service.is_active);
        if (!mounted) return;
        setEmailServices(active);
        setEmailConfigId(String(active.find((service) => service.is_default)?.id ?? active[0]?.id ?? ""));
      })
      .catch((error) => toast.error(error instanceof Error ? error.message : "Unable to load email services"))
      .finally(() => { if (mounted) setLoadingServices(false); });
    return () => { mounted = false; };
  }, []);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  useEffect(() => {
    const interval = window.setInterval(() => void loadHistory(), 300000);
    return () => window.clearInterval(interval);
  }, [loadHistory]);

  function addRecipients(value: string) {
    const emails = value.split(/[\s,;]+/).map((email) => email.trim().toLowerCase()).filter(Boolean);
    const invalid = emails.filter((email) => !validEmail.test(email));
    if (invalid.length > 0) { toast.error(`Invalid email address: ${invalid.join(", ")}`); return; }
    setRecipients((current) => [...new Set([...current, ...emails])]);
    setRecipientDraft("");
  }

  function removeRecipient(email: string) {
    setRecipients((current) => current.filter((recipient) => recipient !== email));
  }

  async function sendReport() {
    const allRecipients = [...new Set([...recipients, ...(alsoOwners ? ownerEmails : [])])];
    if (allRecipients.length === 0) { toast.error("Add a recipient or select campaign owners"); return; }
    if (!emailConfigId) { toast.error("Select an active email service"); return; }
    setSending(true);
    setSendResult(null);
    try {
      const result = await sendCampaignReport(campaignId, {
        recipients: allRecipients,
        subject,
        email_config_id: Number(emailConfigId),
        format,
      });
      if (result.status === "sent") {
        setSendResult({ status: "sent", message: `Report sent to ${result.recipients.length} recipients.`, logId: result.id });
        toast.success("Report sent");
      } else {
        setSendResult({ status: "failed", message: result.error_message || "Report delivery failed.", logId: result.id });
        toast.error(result.error_message || "Report was recorded as failed");
      }
      await loadHistory();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to send report";
      setSendResult({ status: "failed", message });
      toast.error(message);
    } finally {
      setSending(false);
    }
  }

  async function resend(logId: number) {
    setResendingId(logId);
    try {
      const result = await resendCampaignReport(logId);
      result.status === "sent" ? toast.success("Report resent") : toast.error(result.error_message || "Resend failed");
      await loadHistory();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to resend report");
    } finally {
      setResendingId(null);
    }
  }

  return (
    <Section icon={Mail} title="Email Reports">
      <div className="space-y-5">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="campaign-report-subject">Subject</Label>
              <Input id="campaign-report-subject" value={subject} onChange={(event) => setSubject(event.target.value)} maxLength={255} />
            </div>
            <div className="space-y-1.5">
              <Label>Email service</Label>
              <Select value={emailConfigId} onValueChange={setEmailConfigId} disabled={loadingServices || emailServices.length === 0}>
                <SelectTrigger><SelectValue placeholder={loadingServices ? "Loading email services…" : "Select an active email service"} /></SelectTrigger>
                <SelectContent>
                  {emailServices.map((service) => (
                    <SelectItem key={service.id} value={String(service.id)}>
                      {service.name}{service.is_default ? " (default)" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!loadingServices && emailServices.length === 0 && <p className="text-xs text-destructive">No active email services are configured.</p>}
            </div>
            <div className="space-y-1.5">
              <Label>Format</Label>
              <Select value={format} onValueChange={(value: "text" | "html" | "csv" | "pdf") => setFormat(value)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{(["html", "text", "csv", "pdf"] as const).map((value) => <SelectItem key={value} value={value}>{value.toUpperCase()}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="campaign-report-recipients">Recipients</Label>
            {recipients.length > 0 && (
              <div className="flex flex-wrap gap-2" aria-label="Selected recipients">
                {recipients.map((email) => (
                  <Badge key={email} variant="secondary" className="gap-1">
                    {email}
                    <button type="button" aria-label={`Remove ${email}`} onClick={() => removeRecipient(email)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Input
                id="campaign-report-recipients"
                type="text"
                value={recipientDraft}
                placeholder="Type or paste email addresses"
                onChange={(event) => setRecipientDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (["Enter", ",", ";"].includes(event.key)) {
                    event.preventDefault();
                    addRecipients(recipientDraft);
                  }
                }}
                onPaste={(event) => {
                  const pasted = event.clipboardData.getData("text");
                  if (/[\s,;]/.test(pasted)) {
                    event.preventDefault();
                    addRecipients(pasted);
                  }
                }}
              />
              <Button type="button" variant="outline" onClick={() => addRecipients(recipientDraft)}>Add</Button>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={alsoOwners} onCheckedChange={(checked) => setAlsoOwners(checked === true)} />
              <span>Also send to campaign owners</span>
            </label>
            {alsoOwners && ownerEmails.length === 0 && <p className="text-xs text-muted-foreground">No campaign owner emails are configured.</p>}
          </div>
        </div>

        <Button onClick={() => void sendReport()} disabled={sending || loadingServices || !emailConfigId || (recipients.length === 0 && (!alsoOwners || ownerEmails.length === 0))}>
          <Send className="mr-2 h-4 w-4" />{sending ? "Sending…" : "Send Now"}
        </Button>
        {sendResult && (
          <p role="status" className={`text-sm ${sendResult.status === "sent" ? "text-emerald-700" : "text-destructive"}`}>
            {sendResult.message}{sendResult.logId ? ` Delivery log #${sendResult.logId}.` : ""}
          </p>
        )}

        <div className="border-t pt-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold">Delivery history</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-2"
              onClick={() => void loadHistory()}
              disabled={loading}
              aria-label="Refresh report delivery history"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
          {loading ? <p className="text-sm text-muted-foreground">Loading history…</p> : history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No reports have been sent for this campaign.</p>
          ) : (
            <div className="space-y-2">
              {history.map((item) => (
                <div key={item.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b py-2 text-sm last:border-0">
                  <Badge variant={item.status === "sent" ? "secondary" : "destructive"}>{item.status}</Badge>
                  <span className="font-medium">{item.format.toUpperCase()}</span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">{item.recipients.join(", ")}</span>
                  <time className="text-xs text-muted-foreground">{new Date(item.sent_at || item.created_at).toLocaleString()}</time>
                  {item.status === "failed" && (
                    <Button variant="ghost" size="icon" title="Resend failed report" disabled={resendingId === item.id} onClick={() => void resend(item.id)}>
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Section>
  );
}
