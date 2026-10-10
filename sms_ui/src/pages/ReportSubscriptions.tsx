import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Clock3, Mail, Plus, Send, Trash2, X } from "lucide-react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchCampaigns, type ApiCampaign } from "@/lib/api";
import { fetchEmailServices, type EmailService } from "@/lib/api/configurations";
import {
  createReport,
  deleteReport,
  fetchReports,
  patchReport,
  sendReportNow,
  type Report,
  type ReportFormat,
  type ReportFrequency,
  type ReportSubscriptionInput,
} from "@/lib/api/reports";

type FormState = Omit<ReportSubscriptionInput, "is_active"> & { recipientDraft: string };

const initialForm = (): FormState => ({
  name: "",
  campaign_ids: [],
  recipients: [],
  recipientDraft: "",
  include_campaign_owners: true,
  email_config_id: null,
  frequency: "1hr",
  format: "html",
});

const FREQUENCIES: { value: ReportFrequency; label: string }[] = [
  { value: "10min", label: "Every 10 minutes" },
  { value: "1hr", label: "Every hour" },
  { value: "1day", label: "Every day" },
  { value: "manual", label: "Manual only" },
];
const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ETHIOPIAN_TIMEZONE = "Africa/Addis_Ababa";
const ETHIOPIAN_OFFSET_MS = 3 * 60 * 60 * 1000;

function formatEthiopianDate(value: Date | string) {
  return new Intl.DateTimeFormat("en-ET", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: ETHIOPIAN_TIMEZONE,
  }).format(value instanceof Date ? value : new Date(value));
}

function nextRunPreview(frequency: ReportFrequency) {
  const now = new Date(Date.now() + ETHIOPIAN_OFFSET_MS);
  if (frequency === "manual") return null;
  if (frequency === "10min") {
    now.setUTCMinutes(Math.floor(now.getUTCMinutes() / 10) * 10, 0, 0);
    now.setUTCMinutes(now.getUTCMinutes() + 10);
  } else if (frequency === "1hr") {
    now.setUTCMinutes(0, 0, 0);
    now.setUTCHours(now.getUTCHours() + 1);
  } else {
    now.setUTCDate(now.getUTCDate() + 1);
  }
  return new Date(now.getTime() - ETHIOPIAN_OFFSET_MS);
}

export default function ReportSubscriptions() {
  const [reports, setReports] = useState<Report[]>([]);
  const [campaigns, setCampaigns] = useState<ApiCampaign[]>([]);
  const [emailServices, setEmailServices] = useState<EmailService[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [campaignPickerValue, setCampaignPickerValue] = useState("");
  const [current, setCurrent] = useState<Report | null>(null);
  const [form, setForm] = useState<FormState>(initialForm);
  const [saving, setSaving] = useState(false);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Report | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [reportResponse, campaignResponse, serviceResponse] = await Promise.all([
        fetchReports(),
        fetchCampaigns({ page: 1, pageSize: 100 }),
        fetchEmailServices(),
      ]);
      setReports(reportResponse.results);
      setCampaigns(campaignResponse.results.filter((campaign) =>
        !campaign.is_deleted && ["draft", "active", "in_progress", "paused"].includes(campaign.status),
      ));
      setEmailServices(serviceResponse.results.filter((service) => service.is_active));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const selectedCampaigns = campaigns.filter((campaign) => form.campaign_ids.includes(campaign.id));
  const ownerEmails = [...new Set(selectedCampaigns.flatMap((campaign) => campaign.owner_emails ?? [])
    .map((email) => email.trim().toLowerCase()).filter(Boolean))];
  const finalRecipients = [...new Set([
    ...form.recipients,
    ...(form.include_campaign_owners ? ownerEmails : []),
  ])].sort();
  const nextPreview = nextRunPreview(form.frequency);
  const visibleReports = reports.filter((report) => {
    const query = search.toLowerCase();
    return !query || report.name.toLowerCase().includes(query)
      || report.campaigns.some((campaign) => campaign.name.toLowerCase().includes(query))
      || report.recipients.some((recipient) => recipient.toLowerCase().includes(query));
  });

  function openCreate() {
    setCurrent(null);
    setCampaignPickerValue("");
    setForm({
      ...initialForm(),
      email_config_id: emailServices.find((service) => service.is_default)?.id ?? null,
    });
    setModalOpen(true);
  }

  function openEdit(report: Report) {
    setCurrent(report);
    setCampaignPickerValue("");
    setForm({
      name: report.name,
      campaign_ids: report.campaigns.map((campaign) => campaign.id),
      recipients: report.recipients,
      recipientDraft: "",
      include_campaign_owners: report.include_campaign_owners,
      email_config_id: report.email_config,
      frequency: report.frequency,
      format: report.format,
    });
    setModalOpen(true);
  }

  function addCampaign(campaignId: number) {
    setForm((previous) => ({
      ...previous,
      campaign_ids: [...new Set([...previous.campaign_ids, campaignId])],
    }));
    setCampaignPickerValue("");
  }

  function removeCampaign(campaignId: number) {
    setForm((previous) => ({
      ...previous,
      campaign_ids: previous.campaign_ids.filter((id) => id !== campaignId),
    }));
  }

  function addRecipients() {
    const additions = form.recipientDraft.split(/[;,\s]+/).map((email) => email.trim().toLowerCase()).filter(Boolean);
    const invalid = additions.find((email) => !validEmail.test(email));
    if (invalid) { toast.error(`Invalid email address: ${invalid}`); return; }
    setForm((previous) => ({
      ...previous,
      recipients: [...new Set([...previous.recipients, ...additions])],
      recipientDraft: "",
    }));
  }

  async function save() {
    if (!form.name.trim()) { toast.error("Enter a report name"); return; }
    if (!form.campaign_ids.length) { toast.error("Select at least one eligible campaign"); return; }
    if (!finalRecipients.length) { toast.error("Add a recipient or include campaign owners"); return; }
    setSaving(true);
    try {
      const payload: ReportSubscriptionInput = {
        name: form.name.trim(),
        campaign_ids: form.campaign_ids,
        recipients: form.recipients,
        include_campaign_owners: form.include_campaign_owners,
        email_config_id: form.email_config_id,
        frequency: form.frequency,
        format: form.format,
        is_active: true,
      };
      if (current) await patchReport(current.id, payload);
      else await createReport(payload);
      toast.success(current ? "Report updated" : "Report subscription created");
      setModalOpen(false);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to save report subscription");
    } finally {
      setSaving(false);
    }
  }

  async function sendNow(report: Report) {
    setSendingId(report.id);
    try {
      const result = await sendReportNow(report.id);
      if (!result.success) throw new Error(result.error || "Report delivery failed");
      toast.success(`Report sent to ${result.recipients_count} recipients`);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to send report");
      await load();
    } finally {
      setSendingId(null);
    }
  }

  async function remove() {
    if (!deleteTarget) return;
    try {
      await deleteReport(deleteTarget.id);
      toast.success("Report subscription deleted");
      setDeleteTarget(null);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Unable to delete report subscription");
    }
  }

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="mt-1 text-sm text-muted-foreground">Scheduled campaign email reports</p>
        </div>
        <Button onClick={openCreate}><Plus className="mr-2 h-4 w-4" />New Report</Button>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Subscriptions <span className="ml-1 text-sm font-normal text-muted-foreground">{reports.length}</span></h2>
        <Input className="w-full sm:max-w-xs" placeholder="Search reports" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>

      <div className="overflow-x-auto border border-border">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Campaigns</th>
              <th className="px-4 py-3 font-medium">Recipients</th>
              <th className="px-4 py-3 font-medium">Frequency</th>
              <th className="px-4 py-3 font-medium">Next</th>
              <th className="px-4 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">Loading subscriptions…</td></tr>
              : visibleReports.length === 0 ? <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">No report subscriptions found.</td></tr>
                : visibleReports.map((report) => (
                  <tr key={report.id} className="border-t border-border hover:bg-muted/20">
                    <td className="px-4 py-3 font-medium">{report.name}</td>
                    <td className="px-4 py-3">{report.campaigns.length}</td>
                    <td className="px-4 py-3">{report.recipients.length + (report.include_campaign_owners ? " + owners" : "")}</td>
                    <td className="px-4 py-3">{FREQUENCIES.find((item) => item.value === report.frequency)?.label ?? report.frequency}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{report.next_run_at ? formatEthiopianDate(report.next_run_at) : "Manual"}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <Button variant="outline" size="sm" disabled={sendingId === report.id} onClick={() => void sendNow(report)}>
                          <Send className="mr-1.5 h-3.5 w-3.5" />{sendingId === report.id ? "Sending…" : "Send now"}
                        </Button>
                        <Button variant="ghost" size="icon" title="Edit" aria-label={`Edit ${report.name}`} onClick={() => openEdit(report)}><Mail className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" title="Delete" aria-label={`Delete ${report.name}`} onClick={() => setDeleteTarget(report)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      <Dialog open={modalOpen} onOpenChange={(open) => { if (!saving) setModalOpen(open); }}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{current ? "Edit Report" : "New Report"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-6 py-2">
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Name</h3>
              <div className="space-y-2">
                <Label htmlFor="report-name">Report Name</Label>
                <Input id="report-name" maxLength={150} value={form.name} onChange={(event) => setForm((previous) => ({ ...previous, name: event.target.value }))} />
              </div>
            </section>

            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Campaigns</h3>
              <Select value={campaignPickerValue} onValueChange={(value) => addCampaign(Number(value))}>
                <SelectTrigger><SelectValue placeholder="Select a campaign to add" /></SelectTrigger>
                <SelectContent>
                  {campaigns.map((campaign) => (
                    <SelectItem key={campaign.id} value={String(campaign.id)} disabled={form.campaign_ids.includes(campaign.id)}>
                      {campaign.name} (#{campaign.id})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {campaigns.length === 0 && <p className="text-sm text-muted-foreground">No eligible campaigns available.</p>}
              <div className="flex flex-wrap gap-2">
                {selectedCampaigns.map((campaign) => (
                  <Badge key={campaign.id} variant="secondary" className="gap-1 py-1">
                    {campaign.name}
                    <button type="button" title={`Remove ${campaign.name}`} aria-label={`Remove ${campaign.name}`} onClick={() => removeCampaign(campaign.id)}>
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Recipients</h3>
              <div className="flex gap-2">
                <Input value={form.recipientDraft} placeholder="Add email address" onChange={(event) => setForm((previous) => ({ ...previous, recipientDraft: event.target.value }))} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addRecipients(); } }} />
                <Button type="button" variant="outline" onClick={addRecipients}><Plus className="mr-1 h-4 w-4" />Add</Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {form.recipients.map((email) => (
                  <Badge key={email} variant="secondary" className="gap-1 py-1">
                    {email}
                    <button type="button" title={`Remove ${email}`} aria-label={`Remove ${email}`} onClick={() => setForm((previous) => ({ ...previous, recipients: previous.recipients.filter((value) => value !== email) }))}><X className="h-3 w-3" /></button>
                  </Badge>
                ))}
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={form.include_campaign_owners} onCheckedChange={(checked) => setForm((previous) => ({ ...previous, include_campaign_owners: checked === true }))} />
                <span>Include campaign owners automatically</span>
              </label>
              <p className="text-xs text-muted-foreground">
                {form.include_campaign_owners ? `${ownerEmails.length} owner addresses from ${selectedCampaigns.length} campaigns` : "Campaign owner addresses are excluded"}
              </p>
              <div className="border-l-2 border-border pl-3 text-xs text-muted-foreground">
                <p className="mb-1 font-medium text-foreground">Final recipients ({finalRecipients.length})</p>
                <p className="break-all">{finalRecipients.slice(0, 8).join(", ")}{finalRecipients.length > 8 ? `, +${finalRecipients.length - 8} more` : ""}</p>
              </div>
            </section>

            <section className="space-y-4">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Delivery</h3>
              <div className="space-y-2">
                <Label>Email Service</Label>
                <Select value={form.email_config_id === null ? "default" : String(form.email_config_id)} onValueChange={(value) => setForm((previous) => ({ ...previous, email_config_id: value === "default" ? null : Number(value) }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default email service</SelectItem>
                    {emailServices.map((service) => <SelectItem key={service.id} value={String(service.id)}>{service.name}{service.is_default ? " · Default" : ""}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Frequency</Label>
                <RadioGroup value={form.frequency} onValueChange={(value) => setForm((previous) => ({ ...previous, frequency: value as ReportFrequency }))} className="grid gap-2 sm:grid-cols-2">
                  {FREQUENCIES.map((option) => (
                    <label key={option.value} htmlFor={`frequency-${option.value}`} className="flex cursor-pointer items-center gap-2 border border-border p-3 text-sm hover:bg-muted/30">
                      <RadioGroupItem id={`frequency-${option.value}`} value={option.value} />{option.label}
                    </label>
                  ))}
                </RadioGroup>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Clock3 className="h-3.5 w-3.5" />{nextPreview ? `Next: ${formatEthiopianDate(nextPreview)} Ethiopian time` : "Manual only — no scheduled run"}</p>
              </div>

              <div className="space-y-2">
                <Label>Format</Label>
                <Select value={form.format} onValueChange={(value) => setForm((previous) => ({ ...previous, format: value as ReportFormat }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>{(["html", "text", "csv"] as ReportFormat[]).map((value) => <SelectItem key={value} value={value}>{value.toUpperCase()}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </section>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>Cancel</Button>
            <Button type="button" onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete report subscription?</AlertDialogTitle>
            <AlertDialogDescription>{deleteTarget?.name} will no longer be scheduled.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={(event) => { event.preventDefault(); void remove(); }}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
