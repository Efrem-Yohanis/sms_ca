import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Check, Mail, Pencil, Plug, Plus, Star, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createAdminEmailService,
  deleteAdminEmailService,
  listAdminEmailServices,
  testAdminEmailService,
  updateAdminEmailService,
  type AdminEmailConfig,
  type AdminEmailServiceInput,
} from "@/lib/admin-api";

type EmailForm = Omit<AdminEmailServiceInput, "port"> & { port: string };

const emptyForm: EmailForm = {
  name: "",
  host: "",
  port: "587",
  username: "",
  password: "",
  default_from_email: "",
  use_tls: true,
  use_ssl: false,
  is_default: false,
  is_active: true,
};

export function AdminEmailSettings() {
  const [services, setServices] = useState<AdminEmailConfig[]>([]);
  const [testEmail, setTestEmail] = useState("");
  const [form, setForm] = useState<EmailForm>(emptyForm);
  const [editing, setEditing] = useState<AdminEmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionId, setActionId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await listAdminEmailServices();
      setServices(response.results);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not load email services.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...emptyForm, is_default: services.length === 0 });
    setError("");
    setNotice("");
  };

  const openEdit = (service: AdminEmailConfig) => {
    setEditing(service);
    setForm({
      name: service.name ?? "",
      host: service.host ?? "",
      port: String(service.port ?? 587),
      username: service.username ?? "",
      password: "",
      default_from_email: service.default_from_email ?? service.from_email ?? "",
      use_tls: Boolean(service.use_tls),
      use_ssl: Boolean(service.use_ssl),
      is_default: Boolean(service.is_default),
      is_active: Boolean(service.is_active),
    });
    setError("");
    setNotice("");
  };

  const closeEditor = () => {
    setEditing(null);
    setForm(emptyForm);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const port = Number(form.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      setError("Port must be between 1 and 65535.");
      return;
    }
    if (form.use_tls && form.use_ssl) {
      setError("Select either TLS or SSL, not both.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload: AdminEmailServiceInput = {
        ...form,
        name: form.name.trim(),
        host: form.host.trim(),
        port,
        username: form.username.trim(),
        default_from_email: form.default_from_email.trim(),
      };
      if (!form.password) delete payload.password;
      if (editing?.id) await updateAdminEmailService(editing.id, payload);
      else await createAdminEmailService(payload);
      closeEditor();
      setNotice(editing ? "Email service updated." : "Email service created.");
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not save the email service.");
    } finally {
      setSaving(false);
    }
  };

  const setDefault = async (service: AdminEmailConfig) => {
    if (!service.id) return;
    setActionId(service.id);
    setError("");
    setNotice("");
    try {
      await updateAdminEmailService(service.id, { is_default: true, is_active: true });
      setNotice(`${service.name} is now the default email service.`);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not set the default service.");
    } finally {
      setActionId(null);
    }
  };

  const toggleActive = async (service: AdminEmailConfig) => {
    if (!service.id) return;
    setActionId(service.id);
    setError("");
    setNotice("");
    try {
      const isActive = !service.is_active;
      await updateAdminEmailService(service.id, {
        is_active: isActive,
        ...(isActive ? {} : { is_default: false }),
      });
      setNotice(isActive ? "Email service enabled." : "Email service disabled.");
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not update the email service.");
    } finally {
      setActionId(null);
    }
  };

  const remove = async (service: AdminEmailConfig) => {
    if (!service.id || !window.confirm(`Delete email service "${service.name}"?`)) return;
    setActionId(service.id);
    setError("");
    setNotice("");
    try {
      await deleteAdminEmailService(service.id);
      setNotice("Email service deleted.");
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Could not delete the email service.");
    } finally {
      setActionId(null);
    }
  };

  const test = async (service: AdminEmailConfig) => {
    if (!service.id || !testEmail.trim()) return;
    setActionId(service.id);
    setError("");
    setNotice("");
    try {
      const response = await testAdminEmailService(service.id, testEmail.trim());
      setNotice(response.message || "Test email sent.");
      await load();
    } catch (reason: unknown) {
      const message = reason instanceof Error ? reason.message : "Could not test the email service.";
      await load();
      setError(message);
    } finally {
      setActionId(null);
    }
  };

  const fieldClass = "mt-1.5 bg-background text-sm";

  return (
    <section className="border border-border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border p-5 md:p-6">
        <div>
          <h2 className="font-display text-base font-bold">Email Services</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Manage SMTP servers used for Admin account invitations and password reset emails.
            These services are separate from Campaign Manager.
          </p>
        </div>
        <Button onClick={openCreate}><Plus /> Add Email Service</Button>
      </div>

      <div className="p-5 md:p-6">
        <div className="mb-4 max-w-sm space-y-1.5">
          <label htmlFor="admin-email-test-recipient" className="text-sm font-medium">
            Test email recipient
          </label>
          <Input
            id="admin-email-test-recipient"
            type="email"
            value={testEmail}
            onChange={(event) => setTestEmail(event.target.value)}
            placeholder="you@example.com"
          />
        </div>
        {error && <p role="alert" className="mb-4 text-sm text-destructive">{error}</p>}
        {notice && <p role="status" className="mb-4 text-sm text-success">{notice}</p>}
        {loading ? (
          <p role="status" className="py-8 text-sm text-muted-foreground">Loading email services…</p>
        ) : services.length === 0 ? (
          <div className="border border-dashed border-border px-4 py-10 text-center">
            <Mail className="mx-auto size-6 text-muted-foreground" />
            <p className="mt-3 text-sm font-medium">No email services configured</p>
            <p className="mt-1 text-sm text-muted-foreground">Add an SMTP service to send account emails.</p>
          </div>
        ) : (
          <div className="overflow-x-auto border border-border">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-muted/60 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Host</th>
                  <th className="px-4 py-3 font-medium">From</th>
                  <th className="px-4 py-3 font-medium">Last test</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {services.map((service) => (
                  <tr key={service.id} className="align-middle">
                    <td className="px-4 py-3 font-medium">
                      <span className="flex items-center gap-2">
                        {service.name}
                        {service.is_default && <span className="border border-primary/30 px-1.5 py-0.5 text-[10px] text-primary">Default</span>}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{service.host}:{service.port}</td>
                    <td className="px-4 py-3 text-muted-foreground">{service.default_from_email ?? service.from_email}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {service.last_tested_at
                        ? `${service.last_test_status || "Tested"} · ${new Date(service.last_tested_at).toLocaleString()}`
                        : "Never"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={service.is_active ? "text-success" : "text-muted-foreground"}>
                        {service.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="icon" title="Test email service" aria-label={`Test ${service.name}`} disabled={!service.is_active || !testEmail.trim() || actionId === service.id} onClick={() => void test(service)}><Plug /></Button>
                        {!service.is_default && service.is_active && <Button variant="ghost" size="icon" title="Set as default" aria-label={`Set ${service.name} as default`} disabled={actionId === service.id} onClick={() => void setDefault(service)}><Star /></Button>}
                        <Button variant="ghost" size="icon" title="Edit email service" aria-label={`Edit ${service.name}`} onClick={() => openEdit(service)}><Pencil /></Button>
                        <Button variant="ghost" size="icon" title={service.is_active ? "Deactivate" : "Activate"} aria-label={`${service.is_active ? "Deactivate" : "Activate"} ${service.name}`} disabled={actionId === service.id} onClick={() => void toggleActive(service)}><Check /></Button>
                        <Button variant="ghost" size="icon" title="Delete email service" aria-label={`Delete ${service.name}`} disabled={actionId === service.id} onClick={() => void remove(service)}><Trash2 /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {form !== emptyForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4" onMouseDown={(event) => {
          if (event.target === event.currentTarget) closeEditor();
        }}>
          <section role="dialog" aria-modal="true" aria-labelledby="email-service-form-title" className="w-full max-w-xl border border-border bg-card shadow-xl">
            <header className="flex items-center justify-between border-b border-border px-5 py-4">
              <h3 id="email-service-form-title" className="font-display text-lg font-bold">{editing ? "Edit Email Service" : "Add Email Service"}</h3>
              <Button type="button" variant="ghost" size="icon" aria-label="Close dialog" onClick={closeEditor}><X /></Button>
            </header>
            <form onSubmit={save} className="grid gap-4 p-5 sm:grid-cols-2">
              <label className="text-xs font-semibold sm:col-span-2">Name
                <Input required maxLength={150} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className={fieldClass} />
              </label>
              <label className="text-xs font-semibold">Host
                <Input required maxLength={255} value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} className={fieldClass} />
              </label>
              <label className="text-xs font-semibold">Port
                <Input required type="number" min={1} max={65535} value={form.port} onChange={(event) => setForm({ ...form, port: event.target.value })} className={fieldClass} />
              </label>
              <label className="text-xs font-semibold">Username
                <Input autoComplete="username" maxLength={255} value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} className={fieldClass} />
              </label>
              <label className="text-xs font-semibold">Password
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder={editing?.has_password ? "Saved; leave blank to keep it" : "Optional"} className={fieldClass} />
              </label>
              <label className="text-xs font-semibold sm:col-span-2">From Email
                <Input required type="email" maxLength={254} value={form.default_from_email} onChange={(event) => setForm({ ...form, default_from_email: event.target.value })} className={fieldClass} />
              </label>
              <fieldset className="flex flex-wrap gap-5 text-xs sm:col-span-2">
                <legend className="mb-2 font-semibold">Transport security</legend>
                <label className="flex items-center gap-2 font-normal"><input type="checkbox" checked={form.use_tls} onChange={(event) => setForm({ ...form, use_tls: event.target.checked, use_ssl: event.target.checked ? false : form.use_ssl })} />Use TLS</label>
                <label className="flex items-center gap-2 font-normal"><input type="checkbox" checked={form.use_ssl} onChange={(event) => setForm({ ...form, use_ssl: event.target.checked, use_tls: event.target.checked ? false : form.use_tls })} />Use SSL</label>
                <label className="flex items-center gap-2 font-normal"><input type="checkbox" checked={form.is_default} onChange={(event) => setForm({ ...form, is_default: event.target.checked })} />Default</label>
                <label className="flex items-center gap-2 font-normal"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked, is_default: event.target.checked ? form.is_default : false })} />Active</label>
              </fieldset>
              {error && <p role="alert" className="text-sm text-destructive sm:col-span-2">{error}</p>}
              <footer className="flex justify-end gap-2 border-t border-border pt-4 sm:col-span-2">
                <Button type="button" variant="outline" onClick={closeEditor}>Cancel</Button>
                <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save Email Service"}</Button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </section>
  );
}
