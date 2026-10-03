import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Play, Zap } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConfigTable, { Column } from "@/components/configurations/ConfigTable";
import ConfigFormModal from "@/components/configurations/ConfigFormModal";
import {
  Report,
  fetchReports,
  createReport,
  patchReport,
  deleteReport,
  runReport,
  triggerReport,
  toggleReportStatus,
} from "@/lib/api/reports";

const emptyForm = {
  name: "",
  campaigns: [] as number[],
  recipients: "",
  include_campaign_owners: false,
  frequency: "daily" as Report["frequency"],
  is_active: true,
};

export default function Reports() {
  const [data, setData] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"view" | "edit" | "create" | null>(null);
  const [current, setCurrent] = useState<Report | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await fetchReports(); setData(res.results); }
    catch { toast.error("Failed to load reports"); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const columns: Column<Report>[] = [
    { header: "Name", accessor: (r) => r.name, searchable: (r) => r.name },
    { header: "Campaigns", accessor: (r) => r.campaign_names.join(", "), searchable: (r) => r.campaign_names.join(" ") },
    { header: "Frequency", accessor: (r) => r.frequency.replace("_", " ") },
    {
      header: "Last Run",
      accessor: (r) => (r.last_run_at ? new Date(r.last_run_at).toLocaleString() : "Never"),
    },
    {
      header: "Status",
      accessor: (r) => <Badge variant={r.status === "failed" ? "destructive" : "outline"}>{r.status ?? "idle"}</Badge>,
    },
  ];

  const openView = (item: Report) => { setCurrent(item); setModal("view"); };
  const openEdit = (item: Report) => {
    setCurrent(item);
    setForm({
      name: item.name,
      campaigns: item.campaigns,
      recipients: item.recipients.join(", "),
      include_campaign_owners: item.include_campaign_owners,
      frequency: item.frequency,
      is_active: item.is_active,
    });
    setModal("edit");
  };
  const openCreate = () => { setCurrent(null); setForm(emptyForm); setModal("create"); };

  const handleSave = async () => {
    if (!form.name || form.campaigns.length === 0) { toast.error("Name and at least one campaign are required"); return; }
    const payload = {
      ...form,
      recipients: form.recipients.split(",").map((email) => email.trim()).filter(Boolean),
    };
    setSaving(true);
    try {
      if (modal === "create") await createReport(payload);
      else if (current) await patchReport(current.id, payload);
      toast.success(modal === "create" ? "Report created" : "Report updated");
      setModal(null); load();
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    try { await deleteReport(id); toast.success("Report deleted"); load(); } catch { toast.error("Delete failed"); }
  };

  const handleToggle = async (item: Report) => {
    try { await toggleReportStatus(item.id); load(); } catch { toast.error("Status update failed"); }
  };

  const handleExecute = async (item: Report, mode: "run" | "trigger") => {
    setBusyId(item.id);
    try {
      const res = mode === "run" ? await runReport(item.id) : await triggerReport(item.id);
      const ok = res?.success ?? res?.status !== "failed";
      const msg = res?.message || res?.detail || (mode === "run" ? "Report executed" : "Report triggered");
      ok ? toast.success(msg) : toast.error(msg);
      if (res?.download_url) window.open(res.download_url, "_blank");
      load();
    } catch { toast.error(mode === "run" ? "Run failed" : "Trigger failed"); }
    setBusyId(null);
  };

  const activeCount = data.filter((r) => r.is_active).length;
  const scheduledCount = data.length;

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Reports</h1>
        <p className="text-sm text-muted-foreground">Create, schedule and execute campaign reports</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          { label: "Total Reports", value: data.length },
          { label: "Active", value: activeCount },
          { label: "Scheduled", value: scheduledCount },
        ].map((s) => (
          <div key={s.label} className="border border-border bg-card p-4 shadow-soft">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{s.label}</p>
            <p className="text-2xl font-semibold text-foreground">{s.value}</p>
          </div>
        ))}
      </div>

      <ConfigTable
        title="All Reports"
        columns={columns}
        data={data}
        loading={loading}
        onAdd={openCreate}
        onView={openView}
        onEdit={openEdit}
        onDelete={handleDelete}
        onToggleActive={handleToggle}
        extraActions={(row) => (
          <>
            <Button variant="ghost" size="icon" title="Run report" disabled={busyId === row.id} onClick={() => handleExecute(row, "run")}>
              <Play className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" title="Trigger report" disabled={busyId === row.id} onClick={() => handleExecute(row, "trigger")}>
              <Zap className="h-4 w-4" />
            </Button>
          </>
        )}
      />

      <ConfigFormModal open={modal === "view"} onClose={() => setModal(null)} title="Report Details" readOnly>
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Campaigns</Label><Input value={current?.campaign_names.join(", ") ?? ""} disabled /></div>
        <div><Label>Recipients</Label><Input value={current?.recipients.join(", ") ?? ""} disabled /></div>
        <div><Label>Frequency</Label><Input value={current?.frequency.replace("_", " ") ?? ""} disabled /></div>
        <div><Label>Last Run</Label><Input value={current?.last_run_at ? new Date(current.last_run_at).toLocaleString() : "Never"} disabled /></div>
        <div className="flex items-center gap-2"><Switch checked={current?.is_active ?? false} disabled /><Label>Active</Label></div>
      </ConfigFormModal>

      <ConfigFormModal
        open={modal === "edit" || modal === "create"}
        onClose={() => setModal(null)}
        title={modal === "create" ? "Create Report" : "Edit Report"}
        onSubmit={handleSave}
        loading={saving}
      >
        <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div><Label>Campaign IDs</Label><Input value={form.campaigns.join(", ")} onChange={(e) => setForm({ ...form, campaigns: e.target.value.split(",").map((value) => Number(value.trim())).filter(Boolean) })} placeholder="e.g. 1, 2" /></div>
        <div><Label>Recipients</Label><Input value={form.recipients} onChange={(e) => setForm({ ...form, recipients: e.target.value })} placeholder="comma separated emails" /></div>
        <div>
          <Label>Frequency</Label>
          <Select value={form.frequency} onValueChange={(v) => setForm({ ...form, frequency: v as Report["frequency"] })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{["10_minutes", "hourly", "daily"].map((frequency) => <SelectItem key={frequency} value={frequency}>{frequency.replace("_", " ")}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2"><Switch checked={form.include_campaign_owners} onCheckedChange={(v) => setForm({ ...form, include_campaign_owners: v })} /><Label>Include campaign owners</Label></div>
        <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Active</Label></div>
      </ConfigFormModal>
    </div>
  );
}
