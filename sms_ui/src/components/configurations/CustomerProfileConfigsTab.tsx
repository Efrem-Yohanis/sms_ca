import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Eye, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import { getTableColumns, listTables, previewTableRows, type DbColumn, type DbTable, type DbTablePreview } from "@/lib/api/schema";
import {
  CustomerProfileConfig,
  DataSource,
  fetchCustomerProfileConfigs,
  createCustomerProfileConfig,
  patchCustomerProfileConfig,
  deleteCustomerProfileConfig,
  fetchDataSources,
  fetchLanguages,
  SupportedLanguage,
} from "@/lib/api/configurations";

const emptyForm = {
  name: "",
  database_config: "" as string,
  table_name: "",
  msisdn_column: "msisdn",
  language_column: "language",
  default_language: "" as string,
  is_active: true,
};

export default function CustomerProfileConfigsTab() {
  const [data, setData] = useState<CustomerProfileConfig[]>([]);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [languages, setLanguages] = useState<SupportedLanguage[]>([]);
  const [tables, setTables] = useState<DbTable[]>([]);
  const [tableColumns, setTableColumns] = useState<DbColumn[]>([]);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingColumns, setLoadingColumns] = useState(false);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<"view" | "edit" | "create" | null>(null);
  const [current, setCurrent] = useState<CustomerProfileConfig | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [exploring, setExploring] = useState<CustomerProfileConfig | null>(null);
  const [exploreRows, setExploreRows] = useState<{ msisdn: unknown; language: unknown }[]>([]);
  const [exploreLoading, setExploreLoading] = useState(false);
  const [exploreError, setExploreError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try { const res = await fetchCustomerProfileConfigs(); setData(res.results); }
    catch { toast.error("Failed to load customer profile configs"); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    fetchDataSources().then((r) => setSources(r.results)).catch(() => {});
    fetchLanguages().then((r) => setLanguages(r.results)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!form.database_config) {
      setTables([]);
      setTableColumns([]);
      return;
    }
    setLoadingTables(true);
    setTables([]);
    setTableColumns([]);
    listTables(form.database_config)
      .then(setTables)
      .catch(() => toast.error("Failed to load tables from the selected data source"))
      .finally(() => setLoadingTables(false));
  }, [form.database_config]);

  useEffect(() => {
    if (!form.database_config || !form.table_name) {
      setTableColumns([]);
      return;
    }
    setLoadingColumns(true);
    getTableColumns(form.database_config, form.table_name)
      .then(setTableColumns)
      .catch(() => toast.error("Failed to load columns from the selected table"))
      .finally(() => setLoadingColumns(false));
  }, [form.database_config, form.table_name]);

  const columns: Column<CustomerProfileConfig>[] = [
    { header: "Name", accessor: (r) => r.name, searchable: (r) => r.name },
    { header: "Data Source", accessor: (r) => r.database_name ?? String(r.database_config) },
    { header: "Table", accessor: (r) => r.table_name, searchable: (r) => r.table_name },
    { header: "MSISDN Column", accessor: (r) => r.msisdn_column },
  ];

  const openView = (item: CustomerProfileConfig) => { setCurrent(item); setModal("view"); };
  const openEdit = (item: CustomerProfileConfig) => {
    setCurrent(item);
    setForm({
      name: item.name,
      database_config: String(item.database_config),
      table_name: item.table_name,
      msisdn_column: item.msisdn_column,
      language_column: item.language_column,
      default_language: String(item.default_language),
      is_active: item.is_active,
    });
    setModal("edit");
  };
  const openCreate = () => {
    setCurrent(null);
    const english = languages.find((language) => language.code === "en");
    setForm({ ...emptyForm, default_language: english ? String(english.id) : "" });
    setModal("create");
  };

  const handleSave = async () => {
    if (!form.name || !form.database_config || !form.table_name || !form.msisdn_column || !form.default_language) {
      toast.error("Name, database, table, MSISDN column and an English default language are required");
      return;
    }
    setSaving(true);
    try {
      const payload: Partial<CustomerProfileConfig> = {
        ...form,
        database_config: Number(form.database_config),
        default_language: Number(form.default_language),
      };
      if (modal === "create") await createCustomerProfileConfig(payload);
      else if (current) await patchCustomerProfileConfig(current.id, payload);
      toast.success(modal === "create" ? "Profile config created" : "Profile config updated");
      setModal(null); load();
    } catch { toast.error("Save failed"); }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    try { await deleteCustomerProfileConfig(id); toast.success("Deleted"); load(); } catch { toast.error("Delete failed"); }
  };

  const handleToggle = async (item: CustomerProfileConfig) => {
    try { await patchCustomerProfileConfig(item.id, { is_active: !item.is_active }); load(); } catch { toast.error("Update failed"); }
  };

  const openExplore = async (item: CustomerProfileConfig) => {
    setExploring(item);
    setExploreRows([]);
    setExploreError("");
    setExploreLoading(true);
    try {
      const preview: DbTablePreview = await previewTableRows(String(item.database_config), item.table_name, 10);
      const msisdnIndex = preview.columns.indexOf(item.msisdn_column);
      const languageIndex = preview.columns.indexOf(item.language_column);
      if (msisdnIndex < 0) throw new Error(`Column '${item.msisdn_column}' was not found in the table.`);
      setExploreRows(preview.rows.slice(0, 10).map((row) => ({
        msisdn: row[msisdnIndex],
        language: languageIndex >= 0 ? row[languageIndex] : "",
      })));
    } catch (error) {
      setExploreError(error instanceof Error ? error.message : "Could not load sample rows.");
    } finally {
      setExploreLoading(false);
    }
  };

  return (
    <>
      <ConfigTable
        title="Customer Profile Configuration"
        columns={columns}
        data={data}
        loading={loading}
        onAdd={openCreate}
        onView={openView}
        onEdit={openEdit}
        onDelete={handleDelete}
        onToggleActive={handleToggle}
        extraActions={(item) => (
          <Button variant="ghost" size="icon" title="Explore top 10 rows" onClick={() => void openExplore(item)}>
            <Eye className="h-4 w-4" />
          </Button>
        )}
      />

      <ConfigFormModal
        open={exploring !== null}
        onClose={() => setExploring(null)}
        title={`Explore ${exploring?.table_name ?? "profile table"}`}
        readOnly
      >
        <div className="text-sm text-muted-foreground">
          Showing up to 10 rows from <strong>{exploring?.database_name}</strong>.
        </div>
        {exploreLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading sample rows...</div>}
        {exploreError && <p role="alert" className="text-sm text-destructive">{exploreError}</p>}
        {!exploreLoading && !exploreError && (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left">{exploring?.msisdn_column}</th>
                  <th className="px-3 py-2 text-left">{exploring?.language_column}</th>
                </tr>
              </thead>
              <tbody>
                {exploreRows.length === 0 ? (
                  <tr><td colSpan={2} className="px-3 py-6 text-center text-muted-foreground">No rows found</td></tr>
                ) : exploreRows.map((row, index) => (
                  <tr key={index} className="border-b last:border-0">
                    <td className="px-3 py-2">{String(row.msisdn ?? "")}</td>
                    <td className="px-3 py-2">{String(row.language ?? "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ConfigFormModal>

      <ConfigFormModal open={modal === "view"} onClose={() => setModal(null)} title="Profile Config Details" readOnly>
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Data Source</Label><Input value={current?.database_name ?? String(current?.database_config ?? "")} disabled /></div>
        <div><Label>Table</Label><Input value={current?.table_name ?? ""} disabled /></div>
        <div><Label>MSISDN Column</Label><Input value={current?.msisdn_column ?? ""} disabled /></div>
        <div><Label>Language Column</Label><Input value={current?.language_column ?? ""} disabled /></div>
        <div><Label>Default Language</Label><Input value={languages.find((language) => language.id === current?.default_language)?.name ?? String(current?.default_language ?? "")} disabled /></div>
        <div className="flex items-center gap-2"><Switch checked={current?.is_active ?? false} disabled /><Label>Active</Label></div>
      </ConfigFormModal>

      <ConfigFormModal
        open={modal === "edit" || modal === "create"}
        onClose={() => setModal(null)}
        title={modal === "create" ? "Add Profile Config" : "Edit Profile Config"}
        onSubmit={handleSave}
        loading={saving}
      >
        <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div>
          <Label>Data Source</Label>
          <Select value={form.database_config} onValueChange={(v) => setForm({ ...form, database_config: v, table_name: "", msisdn_column: "", language_column: "" })}>
            <SelectTrigger><SelectValue placeholder="Select data source" /></SelectTrigger>
            <SelectContent>
              {sources.filter((source) => source.is_active).map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Table Name</Label>
          <Select value={form.table_name} onValueChange={(v) => setForm({ ...form, table_name: v, msisdn_column: "", language_column: "" })} disabled={!form.database_config || loadingTables}>
            <SelectTrigger><SelectValue placeholder={loadingTables ? "Loading tables..." : "Select table"} /></SelectTrigger>
            <SelectContent>{tables.map((table) => <SelectItem key={table.name} value={table.name}>{table.name}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>MSISDN Column</Label>
            <Select value={form.msisdn_column} onValueChange={(v) => setForm({ ...form, msisdn_column: v })} disabled={!form.table_name || loadingColumns}>
              <SelectTrigger><SelectValue placeholder={loadingColumns ? "Loading columns..." : "Select column"} /></SelectTrigger>
              <SelectContent>{tableColumns.map((column) => <SelectItem key={column.name} value={column.name}>{column.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label>Language Column</Label>
            <Select value={form.language_column} onValueChange={(v) => setForm({ ...form, language_column: v })} disabled={!form.table_name || loadingColumns}>
              <SelectTrigger><SelectValue placeholder={loadingColumns ? "Loading columns..." : "Select column"} /></SelectTrigger>
              <SelectContent>{tableColumns.map((column) => <SelectItem key={column.name} value={column.name}>{column.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex items-center gap-2"><Switch checked={form.is_active} onCheckedChange={(v) => setForm({ ...form, is_active: v })} /><Label>Active</Label></div>
      </ConfigFormModal>
    </>
  );
}
