import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Plug } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  EmailService,
  fetchEmailServices,
  createEmailService,
  patchEmailService,
  deleteEmailService,
  testEmailServiceConnection,
  testEmailServiceSettings,
} from "@/lib/api/configurations";

const emptyForm = {
  name: "",
  host: "",
  port: 587,
  username: "",
  password: "",
  default_from_email: "",
  use_tls: true,
  use_ssl: false,
  is_default: false,
  is_active: true,
};

export default function EmailServicesTab() {
  const [data, setData] = useState<EmailService[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"view" | "edit" | "create" | null>(null);
  const [current, setCurrent] = useState<EmailService | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testingForm, setTestingForm] = useState(false);
  const [testEmail, setTestEmail] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await fetchEmailServices(); setData(res.results); }
    catch { toast.error("Failed to load email services"); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const columns: Column<EmailService>[] = [
    { header: "Name", accessor: (r) => r.name, searchable: (r) => r.name },
    { header: "Host", accessor: (r) => `${r.host}:${r.port}`, searchable: (r) => r.host },
    { header: "From", accessor: (r) => r.default_from_email, searchable: (r) => r.default_from_email },
    { header: "Last test", accessor: (r) => r.last_tested_at ? `${r.last_test_status || "tested"} · ${new Date(r.last_tested_at).toLocaleDateString()}` : "Never" },
  ];

  const openView = (item: EmailService) => { setCurrent(item); setModal("view"); };
  const openEdit = (item: EmailService) => {
    setCurrent(item);
    setForm({
      name: item.name, host: item.host, port: item.port,
      username: item.username, password: "", default_from_email: item.default_from_email,
      use_tls: item.use_tls, use_ssl: item.use_ssl, is_default: item.is_default, is_active: item.is_active,
    });
    setModal("edit");
  };
  const openCreate = () => { setCurrent(null); setForm(emptyForm); setModal("create"); };

  const handleSave = async () => {
    if (!form.name || !form.host || !form.default_from_email) { toast.error("Name, host and from email are required"); return; }
    setSaving(true);
    try {
      const payload: Partial<EmailService> = { ...form };
      if (!form.password) delete payload.password;
      if (modal === "create") await createEmailService(payload);
      else if (current) await patchEmailService(current.id, payload);
      toast.success(modal === "create" ? "Email service created" : "Email service updated");
      setModal(null); load();
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    try { await deleteEmailService(id); toast.success("Deleted"); load(); } catch { toast.error("Delete failed"); }
  };

  const handleToggle = async (item: EmailService) => {
    try { await patchEmailService(item.id, { is_active: !item.is_active }); load(); } catch { toast.error("Update failed"); }
  };

  const handleTest = async (item: EmailService) => {
    if (!testEmail.trim()) { toast.error("Enter a test recipient email first"); return; }
    setTestingId(item.id);
    try {
      const res = await testEmailServiceConnection(item.id, testEmail.trim());
      const ok = res?.success ?? res?.status === "success";
      const msg = res?.message || res?.detail || (ok ? "Connection successful" : "Connection failed");
      ok ? toast.success(msg) : toast.error(msg);
      await load();
    } catch { toast.error("Connection test failed"); }
    setTestingId(null);
  };

  const handleTestForm = async () => {
    if (!form.host || !form.port) { toast.error("Host and port are required"); return; }
    if (!testEmail.trim()) { toast.error("Enter a test recipient email first"); return; }
    setTestingForm(true);
    try {
      const result = await testEmailServiceSettings(form, testEmail.trim());
      result.success ? toast.success(result.message || "SMTP connection successful") : toast.error(result.message || "SMTP connection failed");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "SMTP connection test failed");
    }
    setTestingForm(false);
  };

  return (
    <>
      <div className="mb-4 max-w-sm space-y-1.5">
        <Label htmlFor="smtp-test-recipient">Test email recipient</Label>
        <Input
          id="smtp-test-recipient"
          type="email"
          value={testEmail}
          onChange={(event) => setTestEmail(event.target.value)}
          placeholder="you@example.com"
        />
      </div>
      <ConfigTable
        title="Email Services"
        columns={columns}
        data={data}
        loading={loading}
        onAdd={openCreate}
        onView={openView}
        onEdit={openEdit}
        onDelete={handleDelete}
        onToggleActive={handleToggle}
        extraActions={(row) => (
          <Button variant="ghost" size="icon" title="Send test email" disabled={testingId === row.id || !testEmail.trim()} onClick={() => handleTest(row)}>
            <Plug className="h-4 w-4" />
          </Button>
        )}
      />

      <ConfigFormModal open={modal === "view"} onClose={() => setModal(null)} title="Email Service Details" readOnly>
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Host</Label><Input value={current?.host ?? ""} disabled /></div>
        <div><Label>Port</Label><Input value={current?.port ?? ""} disabled /></div>
        <div><Label>Username</Label><Input value={current?.username ?? ""} disabled /></div>
        <div><Label>From Email</Label><Input value={current?.default_from_email ?? ""} disabled /></div>
        <div className="flex items-center gap-2"><Switch checked={current?.use_tls ?? false} disabled /><Label>Use TLS</Label></div>
        <div className="flex items-center gap-2"><Switch checked={current?.use_ssl ?? false} disabled /><Label>Use SSL</Label></div>
        <div className="flex items-center gap-2"><Switch checked={current?.is_default ?? false} disabled /><Label>Default</Label></div>
        <div className="flex items-center gap-2"><Switch checked={current?.is_active ?? false} disabled /><Label>Active</Label></div>
        <div><Label>Last test message</Label><Input value={current?.last_test_message ?? "Not tested"} disabled /></div>
      </ConfigFormModal>

      <ConfigFormModal
        open={modal === "edit" || modal === "create"}
        onClose={() => setModal(null)}
        title={modal === "create" ? "Add Email Service" : "Edit Email Service"}
        onSubmit={handleSave}
        loading={saving}
      >
        <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label>Host</Label><Input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} /></div>
          <div><Label>Port</Label><Input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} /></div>
        </div>
        <div><Label>Username</Label><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
        <div><Label>Password</Label><Input type="password" placeholder={modal === "edit" ? "Leave blank to keep current" : ""} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><Label>From Email</Label><Input type="email" value={form.default_from_email} onChange={(e) => setForm({ ...form, default_from_email: e.target.value })} /></div>
        </div>
        <div className="flex items-center gap-2"><Switch checked={form.use_tls} onCheckedChange={(v) => setForm({ ...form, use_tls: v })} /><Label>Use TLS</Label></div>
        <div className="flex items-center gap-2"><Switch checked={form.use_ssl} onCheckedChange={(v) => setForm({ ...form, use_ssl: v, use_tls: v ? false : form.use_tls })} /><Label>Use SSL</Label></div>
        <div className="flex items-center gap-2"><Switch checked={form.is_default} onCheckedChange={(v) => setForm({ ...form, is_default: v })} /><Label>Default</Label></div>
        <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Active</Label></div>
        <Button type="button" variant="outline" onClick={() => void handleTestForm()} disabled={testingForm || !testEmail.trim()}>
          {testingForm ? <Plug className="mr-2 h-4 w-4 animate-pulse" /> : <Plug className="mr-2 h-4 w-4" />}
          Test current settings
        </Button>
      </ConfigFormModal>
    </>
  );
}
