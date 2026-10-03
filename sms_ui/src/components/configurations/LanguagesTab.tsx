import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  SupportedLanguage,
  fetchLanguages,
  createLanguage,
  updateLanguage,
  patchLanguage,
  deleteLanguage,
} from "@/lib/api/configurations";

const emptyForm = { code: "", name: "", is_active: true };

export default function LanguagesTab() {
  const [data, setData] = useState<SupportedLanguage[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"view" | "edit" | "create" | null>(null);
  const [current, setCurrent] = useState<SupportedLanguage | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchLanguages();
      setData(res.results);
    } catch { toast.error("Failed to load languages"); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const columns: Column<SupportedLanguage>[] = [
    { header: "Code", accessor: (r) => r.code, searchable: (r) => r.code },
    { header: "Name", accessor: (r) => r.name, searchable: (r) => r.name },
  ];

  const openView = (item: SupportedLanguage) => { setCurrent(item); setModal("view"); };
  const openEdit = (item: SupportedLanguage) => { setCurrent(item); setForm({ code: item.code, name: item.name, is_active: item.is_active }); setModal("edit"); };
  const openCreate = () => { setForm(emptyForm); setModal("create"); };

  const handleSave = async () => {
    if (!form.code || !form.name) { toast.error("Code and name are required"); return; }
    setSaving(true);
    try {
      if (modal === "create") await createLanguage(form);
      else if (current) await updateLanguage(current.id, form);
      toast.success(modal === "create" ? "Language created" : "Language updated");
      setModal(null);
      load();
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    try { await deleteLanguage(id); toast.success("Deleted"); load(); } catch { toast.error("Delete failed"); }
  };

  const handleToggle = async (item: SupportedLanguage) => {
    try { await patchLanguage(item.id, { is_active: !item.is_active }); load(); } catch { toast.error("Update failed"); }
  };

  const formFields = (
    <>
      <div><Label>Code</Label><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} disabled={modal === "view"} /></div>
      <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} disabled={modal === "view"} /></div>
      <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} disabled={modal === "view"} /><Label>Active</Label></div>
    </>
  );

  return (
    <>
      <ConfigTable title="Supported Languages" columns={columns} data={data} loading={loading} onAdd={openCreate} onView={openView} onEdit={openEdit} onDelete={handleDelete} onToggleActive={handleToggle} />
      <ConfigFormModal open={modal === "view"} onClose={() => setModal(null)} title="Language Details" readOnly>
        <div><Label>Code</Label><Input value={current?.code ?? ""} disabled /></div>
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div className="flex items-center gap-2"><Switch checked={current?.is_active ?? false} disabled /><Label>Active</Label></div>
      </ConfigFormModal>
      <ConfigFormModal open={modal === "edit" || modal === "create"} onClose={() => setModal(null)} title={modal === "create" ? "Add Language" : "Edit Language"} onSubmit={handleSave} loading={saving}>
        {formFields}
      </ConfigFormModal>
    </>
  );
}
