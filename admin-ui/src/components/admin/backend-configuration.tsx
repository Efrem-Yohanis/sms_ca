import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Pencil, Plus, Power, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  deleteConfig,
  listConfig,
  saveConfig,
  type ApiConfig,
} from "@/lib/admin-api";
import type { UserRecord } from "@/components/admin/users-management";

export type BackendConfigPage =
  | "SMSC Accounts"
  | "Sender IDs"
  | "Channels"
  | "TPS"
  | "N-Addresses";

type EndpointConfig = {
  endpoint: string;
  name: string;
  columns: string[];
};

const pageConfigs: Record<BackendConfigPage, EndpointConfig> = {
  "SMSC Accounts": {
    endpoint: "smsc-configs",
    name: "SMSC connection",
    columns: ["Name", "Base URL", "Authentication", "TPS", "Assigned users"],
  },
  "Sender IDs": {
    endpoint: "sender-ids",
    name: "Sender ID",
    columns: ["Sender ID", "Display name", "Type", "SMSC connections", "Assigned users"],
  },
  Channels: {
    endpoint: "channels",
    name: "Channel",
    columns: ["Code", "Name", "SMSC connections", "Assigned users"],
  },
  TPS: {
    endpoint: "tps-configs",
    name: "TPS limit",
    columns: ["Name", "Messages per second", "Description", "Status", "Assigned users"],
  },
  "N-Addresses": {
    endpoint: "n-addresses",
    name: "N-address",
    columns: ["Value", "Type", "SMSC", "Channel", "Sender ID", "Assigned users"],
  },
};

type RelatedConfigs = {
  smscs: ApiConfig[];
  senders: ApiConfig[];
  channels: ApiConfig[];
};

const defaultValues = (page: BackendConfigPage): Record<string, unknown> => {
  switch (page) {
    case "SMSC Accounts":
      return {
        name: "",
        description: "",
        base_url: "",
        send_endpoint: "/api/send",
        http_method: "POST",
        auth_type: "none",
        api_key: "",
        api_secret: "",
        username: "",
        password: "",
        rate_limit_per_second: 100,
        rate_limit_per_minute: 3000,
        max_retries: 3,
        retry_backoff_seconds: 5,
        max_addresses_per_request: 1000,
        request_timeout_seconds: 30,
        connect_timeout_seconds: 10,
        is_default: false,
        is_active: true,
        extra_headers: {},
        extra_params: {},
        assigned_user_ids: [],
      };
    case "Sender IDs":
      return {
        sender_id: "",
        name: "",
        description: "",
        sender_type: "ALPHANUMERIC",
        country: "",
        tps_limit: null,
        is_default: false,
        is_active: true,
        smsc_ids: [],
        assigned_user_ids: [],
      };
    case "Channels":
      return {
        code: "",
        name: "",
        is_active: true,
        assigned_user_ids: [],
        smsc_bindings: [],
      };
    case "TPS":
      return {
        name: "",
        description: "",
        global_tps: 100,
        is_default: false,
        is_active: true,
        assigned_user_ids: [],
      };
    case "N-Addresses":
      return {
        value: "",
        address_type: "MSISDN",
        smsc: "",
        channel: "",
        sender_id: "",
        is_active: true,
        tps_cap: null,
        assigned_user_ids: [],
        notes: "",
      };
  }
};

function numberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.map(Number).filter(Number.isFinite) : [];
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function assignedUserIds(config: ApiConfig) {
  return numberArray(config.assigned_user_ids);
}

function useRelatedConfigs() {
  const [related, setRelated] = useState<RelatedConfigs>({
    smscs: [],
    senders: [],
    channels: [],
  });
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      listConfig("smsc-configs"),
      listConfig("sender-ids"),
      listConfig("channels"),
    ])
      .then(([smscs, senders, channels]) => {
        if (active) setRelated({ smscs, senders, channels });
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load configuration options.");
      });
    return () => {
      active = false;
    };
  }, []);

  return { related, error };
}

function getRows(page: BackendConfigPage, configs: ApiConfig[], related: RelatedConfigs) {
  const byId = (items: ApiConfig[], id: unknown) =>
    items.find((item) => item.id === Number(id));

  return configs.map((config) => {
    switch (page) {
      case "SMSC Accounts":
        return [
          config.name,
          config.base_url,
          config.auth_type,
          config.rate_limit_per_second,
          assignedUserIds(config).length,
        ].map(formatValue);
      case "Sender IDs":
        return [
          config.sender_id,
          config.name,
          config.sender_type,
          numberArray(config.bound_smsc_ids)
            .map((id) => byId(related.smscs, id)?.name)
            .filter(Boolean)
            .join(", "),
          assignedUserIds(config).length,
        ].map(formatValue);
      case "Channels":
        return [
          config.code,
          config.name,
          Array.isArray(config.bound_smsc_bindings)
            ? config.bound_smsc_bindings
                .map((binding) => {
                  if (!binding || typeof binding !== "object") return "";
                  const smscId = (binding as Record<string, unknown>).smsc;
                  return byId(related.smscs, smscId)?.name ?? "";
                })
                .filter(Boolean)
                .join(", ")
            : "",
          assignedUserIds(config).length,
        ].map(formatValue);
      case "TPS":
        return [
          config.name,
          config.global_tps,
          config.description,
          config.is_active ? "Active" : "Inactive",
          assignedUserIds(config).length,
        ].map(formatValue);
      case "N-Addresses":
        return [
          config.value,
          config.address_type,
          byId(related.smscs, config.smsc)?.name,
          byId(related.channels, config.channel)?.name,
          byId(related.senders, config.sender_id)?.sender_id,
          numberArray(config.assigned_user_ids).length,
        ].map(formatValue);
    }
  });
}

function configPayload(
  page: BackendConfigPage,
  values: Record<string, unknown>,
  current?: ApiConfig,
) {
  const number = (key: string, fallback: number) => {
    const parsed = Number(values[key]);
    return Number.isFinite(parsed) ? parsed : fallback;
  };
  const bool = (key: string) => Boolean(values[key]);
  const assignments = numberArray(values.assigned_user_ids);

  switch (page) {
    case "SMSC Accounts":
      return {
        ...values,
        rate_limit_per_second: number("rate_limit_per_second", 100),
        rate_limit_per_minute: number("rate_limit_per_minute", 3000),
        max_retries: number("max_retries", 3),
        retry_backoff_seconds: number("retry_backoff_seconds", 5),
        max_addresses_per_request: number("max_addresses_per_request", 1000),
        request_timeout_seconds: number("request_timeout_seconds", 30),
        connect_timeout_seconds: number("connect_timeout_seconds", 10),
        is_default: bool("is_default"),
        is_active: bool("is_active"),
        assigned_user_ids: assignments,
      };
    case "Sender IDs":
      return {
        ...values,
        sender_type: String(values.sender_type),
        tps_limit: values.tps_limit === "" || values.tps_limit === null ? null : number("tps_limit", 1),
        smsc_ids: numberArray(values.smsc_ids),
        assigned_user_ids: assignments,
        is_default: bool("is_default"),
        is_active: bool("is_active"),
      };
    case "Channels": {
      const selectedSmscs = numberArray(values.smsc_ids);
      const existingBindings = Array.isArray(current?.bound_smsc_bindings)
        ? current.bound_smsc_bindings.filter(
            (binding): binding is Record<string, unknown> =>
              Boolean(binding) && typeof binding === "object",
          )
        : [];
      const bindings = selectedSmscs.map((smsc) => {
        const existing = existingBindings.find((binding) => Number(binding.smsc) === smsc);
        return {
          smsc,
          default_tps: existing?.default_tps ?? 100,
          priority: existing?.priority ?? 100,
          allowed_sender_ids: numberArray(existing?.allowed_sender_ids),
        };
      });
      return {
        code: String(values.code ?? ""),
        name: String(values.name ?? ""),
        is_active: bool("is_active"),
        assigned_user_ids: assignments,
        smsc_bindings: bindings,
      };
    }
    case "TPS":
      return {
        name: String(values.name ?? ""),
        description: String(values.description ?? ""),
        global_tps: number("global_tps", 100),
        is_default: bool("is_default"),
        is_active: bool("is_active"),
        assigned_user_ids: assignments,
      };
    case "N-Addresses":
      return {
        value: String(values.value ?? ""),
        address_type: String(values.address_type ?? "MSISDN"),
        smsc: number("smsc", 0),
        channel: values.channel ? number("channel", 0) : null,
        sender_id: values.sender_id ? number("sender_id", 0) : null,
        is_active: bool("is_active"),
        tps_cap: values.tps_cap === "" || values.tps_cap === null ? null : number("tps_cap", 1),
        assigned_user_ids: assignments,
        notes: String(values.notes ?? ""),
      };
  }
}

function ConfigEditor({
  page,
  config,
  users,
  related,
  onClose,
  onSave,
}: {
  page: BackendConfigPage;
  config: ApiConfig | null;
  users: UserRecord[];
  related: RelatedConfigs;
  onClose: () => void;
  onSave: (values: Record<string, unknown>) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...defaultValues(page),
    ...(config ?? {}),
    assigned_user_ids: config ? assignedUserIds(config) : [],
    smsc_ids:
      page === "Sender IDs"
        ? numberArray(config?.bound_smsc_ids)
        : page === "Channels" && Array.isArray(config?.bound_smsc_bindings)
          ? config.bound_smsc_bindings.flatMap((binding) =>
              binding && typeof binding === "object"
                ? [Number((binding as Record<string, unknown>).smsc)]
                : [],
            )
          : numberArray(config?.smsc_ids),
  }));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const setValue = (name: string, value: unknown) =>
    setValues((current) => ({ ...current, [name]: value }));
  const setMulti = (name: string, value: number, checked: boolean) => {
    const current = numberArray(values[name]);
    setValue(
      name,
      checked ? [...new Set([...current, value])] : current.filter((item) => item !== value),
    );
  };
  const toggleLabel = (name: string, label: string, value: boolean) => (
    <label key={name} className="flex items-center gap-2 text-xs font-medium">
      <input
        type="checkbox"
        checked={Boolean(values[name])}
        onChange={(event) => setValue(name, event.target.checked)}
        aria-label={label}
      />
      {label}
      <span className="sr-only">{String(value)}</span>
    </label>
  );
  const textField = (
    name: string,
    label: string,
    type = "text",
    required = false,
    sensitive = false,
  ) => (
    <label key={name} className="block text-xs font-semibold">
      {label}
      <Input
        required={required}
        type={type}
        min={type === "number" ? "1" : undefined}
        step={type === "number" ? "1" : undefined}
        value={String(values[name] ?? "")}
        placeholder={sensitive && config ? "Leave blank to keep saved value" : undefined}
        onChange={(event) => setValue(name, event.target.value)}
        className="mt-1.5 bg-background"
      />
    </label>
  );
  const selectField = (
    name: string,
    label: string,
    options: (string | { id: number; text: string })[],
    required = true,
  ) => (
    <label key={name} className="block text-xs font-semibold">
      {label}
      <select
        required={required}
        value={String(values[name] ?? "")}
        onChange={(event) => setValue(name, event.target.value)}
        className="mt-1.5 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
      >
        <option value="">{required ? "Select…" : "Not assigned"}</option>
        {options.map((option) => (
          <option
            key={typeof option === "string" ? option : option.id}
            value={typeof option === "string" ? option : option.id}
          >
            {typeof option === "string" ? option : option.text}
          </option>
        ))}
      </select>
    </label>
  );
  const checkboxList = (name: string, label: string, options: { id: number; text: string }[]) => (
    <fieldset key={name} className="space-y-2 sm:col-span-2">
      <legend className="mb-2 text-xs font-semibold">{label}</legend>
      <div className="max-h-36 space-y-2 overflow-y-auto rounded-md border border-border p-3">
        {options.map((option) => (
          <label key={option.id} className="flex items-center gap-2 text-xs font-normal">
            <input
              type="checkbox"
              checked={numberArray(values[name]).includes(option.id)}
              onChange={(event) => setMulti(name, option.id, event.target.checked)}
            />
            {option.text}
          </label>
        ))}
        {options.length === 0 && <p className="text-xs text-muted-foreground">No options available.</p>}
      </div>
    </fieldset>
  );

  const fields = () => {
    const managerOptions = users
      .filter((user) => user.role === "Campaign Manager" && user.status !== "Inactive")
      .map((user) => ({ id: user.userId, text: `${user.name} (${user.email})` }));
    const smscOptions = related.smscs.map((item) => ({
      id: item.id,
      text: String(item.name ?? `SMSC ${item.id}`),
    }));
    const senderOptions = related.senders.map((item) => ({
      id: item.id,
      text: String(item.sender_id ?? item.name ?? `Sender ${item.id}`),
    }));
    const channelOptions = related.channels.map((item) => ({
      id: item.id,
      text: String(item.name ?? item.code ?? `Channel ${item.id}`),
    }));

    switch (page) {
      case "SMSC Accounts":
        return [
          textField("name", "Connection name", "text", true),
          textField("base_url", "Base URL", "url", true),
          textField("send_endpoint", "Send endpoint", "text", true),
          selectField("http_method", "HTTP method", ["POST", "GET", "PUT"]),
          selectField("auth_type", "Authentication", ["none", "api_key", "bearer", "basic"]),
          textField("api_key", "API key", "password", false, true),
          textField("api_secret", "API secret", "password", false, true),
          textField("username", "Username"),
          textField("password", "Password", "password", false, true),
          textField("rate_limit_per_second", "Max TPS", "number", true),
          textField("rate_limit_per_minute", "Max messages per minute", "number", true),
          textField("request_timeout_seconds", "Request timeout (seconds)", "number", true),
          textField("connect_timeout_seconds", "Connection timeout (seconds)", "number", true),
          checkboxList("assigned_user_ids", "Assigned Campaign Managers", managerOptions),
          toggleLabel("is_default", "Default SMSC", Boolean(values.is_default)),
          toggleLabel("is_active", "Enabled", Boolean(values.is_active)),
        ];
      case "Sender IDs":
        return [
          textField("sender_id", "Sender ID value", "text", true),
          textField("name", "Display name", "text", true),
          selectField("sender_type", "Sender ID type", ["ALPHANUMERIC", "NUMERIC", "SHORT_CODE"]),
          textField("country", "Country / region"),
          textField("tps_limit", "Sender TPS limit", "number"),
          checkboxList("smsc_ids", "Allowed SMSC connections", smscOptions),
          checkboxList("assigned_user_ids", "Assigned Campaign Managers", managerOptions),
          toggleLabel("is_default", "Default Sender ID", Boolean(values.is_default)),
          toggleLabel("is_active", "Enabled", Boolean(values.is_active)),
        ];
      case "Channels":
        return [
          textField("code", "Channel code", "text", true),
          textField("name", "Channel name", "text", true),
          checkboxList("smsc_ids", "Linked SMSC connections", smscOptions),
          checkboxList("assigned_user_ids", "Assigned Campaign Managers", managerOptions),
          toggleLabel("is_active", "Enabled", Boolean(values.is_active)),
        ];
      case "TPS":
        return [
          textField("name", "Limit name", "text", true),
          textField("global_tps", "Messages per second", "number", true),
          textField("description", "Description"),
          checkboxList("assigned_user_ids", "Assigned Campaign Managers", managerOptions),
          toggleLabel("is_default", "Default TPS limit", Boolean(values.is_default)),
          toggleLabel("is_active", "Enabled", Boolean(values.is_active)),
        ];
      case "N-Addresses":
        return [
          textField("value", "N-address value", "text", true),
          selectField("address_type", "Address type", ["MSISDN", "ALPHANUMERIC", "POOL"]),
          selectField("smsc", "Bound SMSC", smscOptions),
          selectField("channel", "Bound channel (optional)", channelOptions, false),
          selectField("sender_id", "Bound Sender ID (optional)", senderOptions, false),
          textField("tps_cap", "TPS cap (optional)", "number"),
          checkboxList("assigned_user_ids", "Assigned Campaign Managers", managerOptions),
          toggleLabel("is_active", "Enabled", Boolean(values.is_active)),
          textField("notes", "Notes"),
        ];
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = configPayload(page, values, config ?? undefined);
      await onSave(payload);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save this configuration.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
      <form
        role="dialog"
        aria-modal="true"
        aria-label={`${config ? "Edit" : "Add"} ${pageConfigs[page].name}`}
        onSubmit={submit}
        className="admin-scroll max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-md border border-border bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-display text-lg font-bold">
            {config ? "Edit" : "Add"} {pageConfigs[page].name}
          </h2>
          <Button type="button" variant="ghost" onClick={onClose}>Close</Button>
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-2">{fields()}</div>
        {error && <p role="alert" className="px-5 pb-4 text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
        </div>
      </form>
    </div>
  );
}

export function BackendConfiguration({
  page,
  users,
  onNotice,
}: {
  page: BackendConfigPage;
  users: UserRecord[];
  onNotice: (message: string) => void;
}) {
  const endpoint = pageConfigs[page].endpoint;
  const [configs, setConfigs] = useState<ApiConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ApiConfig | null>(null);
  const [creating, setCreating] = useState(false);
  const { related, error: relatedError } = useRelatedConfigs();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setConfigs(await listConfig(endpoint));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load configurations.");
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rows = useMemo(() => getRows(page, configs, related), [page, configs, related]);
  const filtered = configs
    .map((config, index) => ({ config, values: rows[index] ?? [] }))
    .filter(({ values }) => values.join(" ").toLowerCase().includes(query.trim().toLowerCase()));

  const save = async (payload: Record<string, unknown>) => {
    await saveConfig(endpoint, editing?.id ?? null, payload);
    await refresh();
    setEditing(null);
    setCreating(false);
    onNotice(`${pageConfigs[page].name} saved.`);
  };

  const remove = async (config: ApiConfig) => {
    const name = String(config.name ?? config.sender_id ?? config.value ?? config.code ?? config.id);
    if (!window.confirm(`Delete "${name}"?`)) return;
    try {
      await deleteConfig(endpoint, config.id);
      await refresh();
      onNotice(`${name} deleted.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Could not delete ${name}.`);
    }
  };

  const toggleActive = async (config: ApiConfig) => {
    try {
      await saveConfig(endpoint, config.id, { is_active: !config.is_active });
      await refresh();
      onNotice(`${String(config.name ?? config.sender_id ?? config.value ?? config.code)} ${config.is_active ? "disabled" : "enabled"}.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update status.");
    }
  };

  return (
    <>
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={`Search ${page}`}
              placeholder={`Search ${page.toLowerCase()}...`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="bg-background pl-9 text-xs"
            />
          </div>
          <Button onClick={() => setCreating(true)}><Plus /> Add {pageConfigs[page].name}</Button>
          <Button variant="outline" onClick={() => void refresh()}>Refresh</Button>
        </div>
        {(error || relatedError) && (
          <p role="alert" className="border-b border-border bg-danger-soft px-5 py-3 text-sm text-destructive">
            {error || relatedError}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {pageConfigs[page].columns.map((column) => (
                  <th key={column} className="whitespace-nowrap px-5 py-3 font-semibold">{column}</th>
                ))}
                {page !== "N-Addresses" && <th className="px-5 py-3 font-semibold">Status</th>}
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!loading && filtered.map(({ config, values }) => (
                <tr key={config.id} className="border-t border-border hover:bg-surface">
                  {values.map((value, index) => (
                    <td key={`${config.id}-${index}`} className="whitespace-nowrap px-5 py-4">
                      {value}
                    </td>
                  ))}
                  {page !== "N-Addresses" && (
                    <td className="px-5 py-4">
                      <span className={`rounded px-2 py-1 text-[11px] font-semibold ${config.is_active ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}>
                        {config.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                  )}
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="icon" aria-label={`Edit configuration ${config.id}`} onClick={() => setEditing(config)}><Pencil /></Button>
                      <Button variant="ghost" size="icon" aria-label={`${config.is_active ? "Disable" : "Enable"} configuration ${config.id}`} onClick={() => void toggleActive(config)}><Power /></Button>
                      <Button variant="ghost" size="icon" aria-label={`Delete configuration ${config.id}`} className="text-destructive hover:text-destructive" onClick={() => void remove(config)}><Trash2 /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <p role="status" className="py-12 text-center text-sm text-muted-foreground">Loading configurations…</p>}
          {!loading && filtered.length === 0 && <p className="py-12 text-center text-sm text-muted-foreground">No matching configurations.</p>}
        </div>
        <div className="border-t border-border px-5 py-3 text-xs text-muted-foreground">
          Showing {filtered.length} {page.toLowerCase()}
        </div>
      </div>
      {(creating || editing) && (
        <ConfigEditor
          key={`${page}-${editing?.id ?? "new"}`}
          page={page}
          config={editing}
          users={users}
          related={related}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSave={save}
        />
      )}
    </>
  );
}
