import { useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, Check, Pencil, Plus, Power, Search, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { UserRecord } from "@/components/admin/users-management";
import {
  initializeConfigurationEntries,
  updateConfigurationEntries,
  useConfigurationEntries,
  type ConfigEntry,
  type ConfigPage,
} from "@/components/admin/configuration-store";

type ConfigDefinition = {
  columns: string[];
  fields: string[];
  initial: ConfigEntry[];
};

const definitions: Record<ConfigPage, ConfigDefinition> = {
  "SMSC Accounts": {
    columns: ["Account", "Owner", "Base URL", "Auth", "Rate limit"],
    fields: ["Account name", "Owner", "Base URL", "Auth type", "Rate limit"],
    initial: [
      {
        id: "smsc-primary",
        values: ["Primary gateway", "Olivia Chen", "api.gateway-one.com", "Bearer", "120/s"],
        active: true,
        subscriberEmails: ["olivia@acme.co"],
      },
      {
        id: "smsc-brightly",
        values: ["Brightly SMS", "Marcus Rivera", "api.brightly.net", "Basic", "80/s"],
        active: true,
        subscriberEmails: ["marcus@brightly.io"],
      },
      {
        id: "smsc-northstar",
        values: ["Northstar primary", "Aisha Patel", "sms.northstar.com", "Bearer", "150/s"],
        active: true,
        subscriberEmails: ["aisha@northstar.com"],
      },
      {
        id: "smsc-meridian",
        values: ["Meridian backup", "James Okafor", "api.meridian.co", "Basic", "60/s"],
        active: false,
        subscriberEmails: ["james@meridian.co"],
      },
    ],
  },
  "Sender IDs": {
    columns: ["Sender ID", "Name", "Owner", "Default"],
    fields: ["Sender ID", "Display name", "Owner", "Default"],
    initial: [
      {
        id: "sender-acme",
        values: ["ACME", "Acme Marketing", "Olivia Chen", "Yes"],
        active: true,
        subscriberEmails: ["olivia@acme.co"],
      },
      {
        id: "sender-brightly",
        values: ["BRIGHTLY", "Brightly Updates", "Marcus Rivera", "Yes"],
        active: true,
        subscriberEmails: ["marcus@brightly.io"],
      },
      {
        id: "sender-northstar",
        values: ["NORTHSTAR", "Northstar Alerts", "Aisha Patel", "Yes"],
        active: true,
        subscriberEmails: ["aisha@northstar.com"],
      },
      {
        id: "sender-meridian",
        values: ["MERIDIAN", "Meridian Health", "James Okafor", "Yes"],
        active: true,
        subscriberEmails: ["james@meridian.co"],
      },
    ],
  },
  Channels: {
    columns: ["Code", "Channel", "Assigned users"],
    fields: ["Channel code", "Channel name", "Assigned users"],
    initial: [
      {
        id: "channel-sms",
        values: ["SMS", "Standard SMS", "6 users"],
        active: true,
        subscriberEmails: [
          "olivia@acme.co",
          "marcus@brightly.io",
          "aisha@northstar.com",
          "james@meridian.co",
          "sofia@orbit.io",
          "daniel@pulse.com",
        ],
      },
      {
        id: "channel-flash",
        values: ["FLASH", "Flash SMS", "3 users"],
        active: true,
        subscriberEmails: ["olivia@acme.co", "aisha@northstar.com", "sofia@orbit.io"],
      },
      {
        id: "channel-unicode",
        values: ["UNICODE", "Unicode SMS", "3 users"],
        active: true,
        subscriberEmails: ["marcus@brightly.io", "james@meridian.co", "daniel@pulse.com"],
      },
    ],
  },
};

initializeConfigurationEntries({
  "SMSC Accounts": definitions["SMSC Accounts"].initial,
  "Sender IDs": definitions["Sender IDs"].initial,
  Channels: definitions.Channels.initial,
});

function SubscriberPicker({
  users,
  selectedEmails,
  onChange,
}: {
  users: UserRecord[];
  selectedEmails: string[];
  onChange: (emails: string[]) => void;
}) {
  return (
    <fieldset className="space-y-2 sm:col-span-2">
      <legend className="text-xs font-semibold">Subscribed users</legend>
      <div className="max-h-40 space-y-2 overflow-y-auto rounded-md border border-border p-3">
        {users.map((user) => (
          <label key={user.email} className="flex items-center gap-2 text-xs font-normal">
            <input
              type="checkbox"
              checked={selectedEmails.includes(user.email)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selectedEmails, user.email]
                    : selectedEmails.filter((email) => email !== user.email),
                )
              }
            />
            {user.name} <span className="text-muted-foreground">({user.email})</span>
          </label>
        ))}
        {users.length === 0 && (
          <p className="text-xs text-muted-foreground">No users are available.</p>
        )}
      </div>
    </fieldset>
  );
}

function ConfigurationSubscribers({
  title,
  type,
  users,
  subscriberEmails,
  onBack,
}: {
  title: string;
  type: string;
  users: UserRecord[];
  subscriberEmails: string[];
  onBack: () => void;
}) {
  const subscribers = users.filter((user) => (subscriberEmails ?? []).includes(user.email));
  const itemType =
    type === "SMSC Accounts"
      ? "SMSC account"
      : type === "Sender IDs"
        ? "sender ID"
        : type === "Channels"
          ? "channel"
          : `${type} profile`;

  return (
    <section>
      <Button variant="ghost" size="sm" className="mb-5 -ml-3" onClick={onBack}>
        <ArrowLeft /> Back to {type}
      </Button>
      <div className="mb-6">
        <h2 className="font-display text-2xl font-bold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">Users subscribed to this {itemType}.</p>
      </div>
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="border-b border-border px-5 py-4">
          <h3 className="font-display text-sm font-bold">Subscribed users</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {subscribers.length} {subscribers.length === 1 ? "user" : "users"}
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {["Username", "Name", "Email", "Department", "Role", "Status"].map((column) => (
                  <th key={column} className="whitespace-nowrap px-5 py-3 font-semibold">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {subscribers.map((user) => (
                <tr key={user.email} className="border-t border-border">
                  <td className="whitespace-nowrap px-5 py-4 font-mono font-semibold">
                    {user.username ?? user.email.split("@")[0]}
                  </td>
                  <td className="whitespace-nowrap px-5 py-4">{user.name}</td>
                  <td className="whitespace-nowrap px-5 py-4 text-muted-foreground">
                    {user.email}
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 text-muted-foreground">
                    {user.department ?? user.company}
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 text-muted-foreground">
                    {user.role ?? "—"}
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold">
                      <span className="size-1.5 rounded-full bg-current" />
                      {user.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {subscribers.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No users are subscribed to this configuration.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function ResourceDialog({
  title,
  fields,
  initialValues,
  users,
  initialSubscriberEmails,
  onClose,
  onSubmit,
}: {
  title: string;
  fields: string[];
  initialValues: string[];
  users: UserRecord[];
  initialSubscriberEmails: string[];
  onClose: () => void;
  onSubmit: (values: string[], subscriberEmails: string[]) => void;
}) {
  const [values, setValues] = useState(() => fields.map((_, index) => initialValues[index] ?? ""));
  const [subscriberEmails, setSubscriberEmails] = useState(initialSubscriberEmails);
  const [error, setError] = useState("");

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (values.some((value) => !value.trim())) {
      setError("Complete all fields before saving.");
      return;
    }
    onSubmit(
      values.map((value) => value.trim()),
      subscriberEmails,
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onSubmit={submit}
        className="w-full max-w-lg rounded-md border border-border bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-display text-lg font-bold">{title}</h2>
          <Button type="button" size="icon" variant="ghost" aria-label="Close" onClick={onClose}>
            <X />
          </Button>
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          {fields.map((field, index) => (
            <label key={field} className="block text-xs font-semibold">
              {field}
              <Input
                required
                value={values[index] ?? ""}
                onChange={(event) =>
                  setValues((current) =>
                    current.map((value, valueIndex) =>
                      valueIndex === index ? event.target.value : value,
                    ),
                  )
                }
                className="mt-1.5 h-9 bg-background text-sm"
              />
            </label>
          ))}
          <SubscriberPicker
            users={users}
            selectedEmails={subscriberEmails}
            onChange={setSubscriberEmails}
          />
          {error && (
            <p role="alert" className="text-xs text-destructive sm:col-span-2">
              {error}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </div>
  );
}

export function ConfigurationList({
  page,
  users,
  onNotice,
}: {
  page: ConfigPage;
  users: UserRecord[];
  onNotice: (message: string) => void;
}) {
  const definition = definitions[page];
  const entries = useConfigurationEntries(page);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ConfigEntry | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<ConfigEntry | null>(null);

  const filteredEntries = useMemo(
    () =>
      entries.filter((entry) =>
        entry.values.join(" ").toLowerCase().includes(query.trim().toLowerCase()),
      ),
    [entries, query],
  );

  const saveEntry = (values: string[], subscriberEmails: string[]) => {
    if (editing) {
      updateConfigurationEntries(page, (current) =>
        current.map((entry) =>
          entry.id === editing.id
            ? {
                ...entry,
                values:
                  page === "Channels"
                    ? [values[0] ?? "", values[1] ?? "", `${subscriberEmails.length} users`]
                    : values,
                subscriberEmails,
              }
            : entry,
        ),
      );
      onNotice(`${page} configuration updated in this preview.`);
    } else {
      updateConfigurationEntries(page, (current) => [
        {
          id: `${page}-${Date.now()}`,
          values:
            page === "Channels"
              ? [values[0] ?? "", values[1] ?? "", `${subscriberEmails.length} users`]
              : values,
          active: true,
          subscriberEmails,
        },
        ...current,
      ]);
      onNotice(`${page} configuration added to this preview.`);
    }
    setDialogOpen(false);
    setEditing(null);
  };

  if (selectedEntry) {
    return (
      <ConfigurationSubscribers
        title={selectedEntry.values[0] ?? page}
        type={page}
        users={users}
        subscriberEmails={selectedEntry.subscriberEmails ?? []}
        onBack={() => setSelectedEntry(null)}
      />
    );
  }

  const deleteEntry = (entry: ConfigEntry) => {
    if (!window.confirm(`Delete "${entry.values[0]}"?`)) return;
    updateConfigurationEntries(page, (current) => current.filter((item) => item.id !== entry.id));
    onNotice(`${entry.values[0]} deleted from this preview.`);
  };

  const toggleEntry = (entry: ConfigEntry) => {
    updateConfigurationEntries(page, (current) =>
      current.map((item) => (item.id === entry.id ? { ...item, active: !item.active } : item)),
    );
    onNotice(`${entry.values[0]} ${entry.active ? "deactivated" : "activated"} in this preview.`);
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
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus /> Add{" "}
            {page === "SMSC Accounts" ? "account" : page === "Sender IDs" ? "sender ID" : "channel"}
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {definition.columns.map((column) => (
                  <th key={column} className="whitespace-nowrap px-5 py-3 font-semibold">
                    {column}
                  </th>
                ))}
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((entry) => (
                <tr key={entry.id} className="border-t border-border hover:bg-surface">
                  {entry.values.map((value, index) => (
                    <td
                      key={`${entry.id}-${index}`}
                      className={`whitespace-nowrap px-5 py-4 ${index === 0 ? "font-semibold" : "text-muted-foreground"}`}
                    >
                      {index === 0 ? (
                        <Button
                          variant="link"
                          className="h-auto p-0 font-semibold"
                          onClick={() => setSelectedEntry(entry)}
                        >
                          {value}
                        </Button>
                      ) : (
                        value
                      )}
                    </td>
                  ))}
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${entry.active ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}
                    >
                      <span className="size-1.5 rounded-full bg-current" />
                      {entry.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Edit ${entry.values[0]}`}
                        title="Edit configuration"
                        onClick={() => {
                          setEditing(entry);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`${entry.active ? "Deactivate" : "Activate"} ${entry.values[0]}`}
                        title={entry.active ? "Deactivate configuration" : "Activate configuration"}
                        onClick={() => toggleEntry(entry)}
                      >
                        <Power />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${entry.values[0]}`}
                        title="Delete configuration"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteEntry(entry)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredEntries.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No matching configurations.
            </p>
          )}
        </div>
        <div className="border-t border-border px-5 py-3 text-xs text-muted-foreground">
          Showing {filteredEntries.length} {page.toLowerCase()}
        </div>
      </div>
      {dialogOpen && (
        <ResourceDialog
          key={editing?.id ?? "new"}
          title={`${editing ? "Edit" : "Add"} ${page === "SMSC Accounts" ? "SMSC account" : page === "Sender IDs" ? "sender ID" : "channel"}`}
          fields={definition.fields}
          initialValues={editing?.values ?? []}
          users={users}
          initialSubscriberEmails={editing?.subscriberEmails ?? []}
          onClose={() => {
            setDialogOpen(false);
            setEditing(null);
          }}
          onSubmit={saveEntry}
        />
      )}
    </>
  );
}

type LimitProfile = {
  id: string;
  name: string;
  value: number;
  description: string;
  active: boolean;
  subscriberEmails: string[];
};

function LimitProfileDialog({
  kind,
  profile,
  users,
  onClose,
  onSubmit,
}: {
  kind: "TPS" | "N-address";
  profile: LimitProfile | null;
  users: UserRecord[];
  onClose: () => void;
  onSubmit: (profile: Omit<LimitProfile, "id" | "active">) => void;
}) {
  const [name, setName] = useState(profile?.name ?? "");
  const [value, setValue] = useState(profile ? String(profile.value) : "");
  const [description, setDescription] = useState(profile?.description ?? "");
  const [subscriberEmails, setSubscriberEmails] = useState(profile?.subscriberEmails ?? []);
  const [error, setError] = useState("");

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const tpsValue = Number(value);
    if (!name.trim() || !description.trim() || !Number.isInteger(tpsValue) || tpsValue < 1) {
      setError(`Enter a name, a whole ${kind} value greater than zero, and a description.`);
      return;
    }
    onSubmit({
      name: name.trim(),
      value: tpsValue,
      description: description.trim(),
      subscriberEmails,
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={`${profile ? "Edit" : "Add"} ${kind} profile`}
        onSubmit={submit}
        className="w-full max-w-lg rounded-md border border-border bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-display text-lg font-bold">
            {profile ? `Edit ${kind} profile` : `Add ${kind} profile`}
          </h2>
          <Button type="button" size="icon" variant="ghost" aria-label="Close" onClick={onClose}>
            <X />
          </Button>
        </div>
        <div className="grid gap-4 p-5">
          <label className="block text-xs font-semibold">
            {kind} name
            <Input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={kind === "TPS" ? "e.g. Standard" : "e.g. Standard batch"}
              className="mt-1.5 bg-background"
            />
          </label>
          <SubscriberPicker
            users={users}
            selectedEmails={subscriberEmails}
            onChange={setSubscriberEmails}
          />
          <label className="block text-xs font-semibold">
            {kind === "TPS"
              ? "TPS value (messages per second)"
              : "N-address value (recipients per request)"}
            <Input
              required
              type="number"
              min="1"
              step="1"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder={kind === "TPS" ? "e.g. 100" : "e.g. 250"}
              className="mt-1.5 bg-background"
            />
          </label>
          <label className="block text-xs font-semibold">
            Description
            <Textarea
              required
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={`Describe when this ${kind} profile should be used.`}
              className="mt-1.5 bg-background"
            />
          </label>
          {error && (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </div>
  );
}

export function LimitProfilesList({
  kind,
  users,
  onNotice,
}: {
  kind: "TPS" | "N-address";
  users: UserRecord[];
  onNotice: (message: string) => void;
}) {
  const [profiles, setProfiles] = useState<LimitProfile[]>(() =>
    kind === "TPS"
      ? [
          {
            id: "tps-standard",
            name: "Standard",
            value: 100,
            description: "Default sending rate for regular campaigns.",
            active: true,
            subscriberEmails: [
              "marcus@brightly.io",
              "james@meridian.co",
              "sofia@orbit.io",
              "daniel@pulse.com",
            ],
          },
          {
            id: "tps-high-volume",
            name: "High volume",
            value: 250,
            description: "For larger campaigns with increased throughput.",
            active: true,
            subscriberEmails: ["olivia@acme.co", "aisha@northstar.com"],
          },
          {
            id: "tps-enterprise",
            name: "Enterprise",
            value: 500,
            description: "Highest throughput for approved enterprise users.",
            active: true,
            subscriberEmails: [],
          },
        ]
      : [
          {
            id: "n-address-standard",
            name: "Standard",
            value: 250,
            description: "Default recipient limit for regular requests.",
            active: true,
            subscriberEmails: ["marcus@brightly.io", "james@meridian.co", "sofia@orbit.io"],
          },
          {
            id: "n-address-large-batch",
            name: "Large batch",
            value: 500,
            description: "For campaigns that send to larger recipient groups.",
            active: true,
            subscriberEmails: ["olivia@acme.co", "aisha@northstar.com", "daniel@pulse.com"],
          },
          {
            id: "n-address-enterprise",
            name: "Enterprise",
            value: 1000,
            description: "Highest recipient limit for approved enterprise users.",
            active: true,
            subscriberEmails: [],
          },
        ],
  );
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<LimitProfile | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const profileName = kind === "TPS" ? "TPS" : "N-address";
  const profilesTitle = `${profileName} profiles`;
  const valueColumn = kind === "TPS" ? "Messages / second" : "Recipients / request";

  const filteredProfiles = useMemo(
    () =>
      profiles.filter((profile) =>
        `${profile.name} ${profile.value} ${profile.description}`
          .toLowerCase()
          .includes(query.trim().toLowerCase()),
      ),
    [profiles, query],
  );

  const [selectedProfile, setSelectedProfile] = useState<LimitProfile | null>(null);

  const saveProfile = (details: Omit<LimitProfile, "id" | "active">) => {
    if (editing) {
      setProfiles((current) =>
        current.map((profile) =>
          profile.id === editing.id ? { ...profile, ...details } : profile,
        ),
      );
      onNotice(`${profileName} profile updated in this preview.`);
    } else {
      setProfiles((current) => [
        { id: `${kind.toLowerCase()}-${Date.now()}`, ...details, active: true },
        ...current,
      ]);
      onNotice(`${profileName} profile added to this preview.`);
    }
    setDialogOpen(false);
    setEditing(null);
  };

  const deleteProfile = (profile: LimitProfile) => {
    if (!window.confirm(`Delete the "${profile.name}" ${profileName} profile?`)) return;
    setProfiles((current) => current.filter((item) => item.id !== profile.id));
    onNotice(`${profile.name} ${profileName} profile deleted from this preview.`);
  };

  if (selectedProfile) {
    return (
      <ConfigurationSubscribers
        title={selectedProfile.name}
        type={profileName}
        users={users}
        subscriberEmails={selectedProfile.subscriberEmails ?? []}
        onBack={() => setSelectedProfile(null)}
      />
    );
  }

  return (
    <>
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-wrap items-center gap-3 border-b border-border p-4">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label={`Search ${profilesTitle}`}
              placeholder={`Search ${profilesTitle.toLowerCase()}...`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="bg-background pl-9 text-xs"
            />
          </div>
          <Button
            onClick={() => {
              setEditing(null);
              setDialogOpen(true);
            }}
          >
            <Plus /> Add {profileName} profile
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {[`${profileName} name`, valueColumn, "Description", "Status"].map((column) => (
                  <th key={column} className="whitespace-nowrap px-5 py-3 font-semibold">
                    {column}
                  </th>
                ))}
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProfiles.map((profile) => (
                <tr key={profile.id} className="border-t border-border hover:bg-surface">
                  <td className="whitespace-nowrap px-5 py-4">
                    <Button
                      variant="link"
                      className="h-auto p-0 font-semibold"
                      onClick={() => setSelectedProfile(profile)}
                    >
                      {profile.name}
                    </Button>
                  </td>
                  <td className="whitespace-nowrap px-5 py-4">
                    {profile.value.toLocaleString()} {kind === "TPS" ? "/ sec" : ""}
                  </td>
                  <td className="px-5 py-4 text-muted-foreground">{profile.description}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${profile.active ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}
                    >
                      <span className="size-1.5 rounded-full bg-current" />
                      {profile.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Edit ${profile.name} ${profileName} profile`}
                        onClick={() => {
                          setEditing(profile);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`${profile.active ? "Deactivate" : "Activate"} ${profile.name} ${profileName} profile`}
                        onClick={() => {
                          setProfiles((current) =>
                            current.map((item) =>
                              item.id === profile.id ? { ...item, active: !item.active } : item,
                            ),
                          );
                          onNotice(
                            `${profile.name} ${profileName} profile ${profile.active ? "deactivated" : "activated"} in this preview.`,
                          );
                        }}
                      >
                        <Power />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete ${profile.name} ${profileName} profile`}
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteProfile(profile)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredProfiles.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No matching {profilesTitle.toLowerCase()}.
            </p>
          )}
        </div>
        <div className="border-t border-border px-5 py-3 text-xs text-muted-foreground">
          Showing {filteredProfiles.length} {profilesTitle.toLowerCase()}
        </div>
      </div>
      {dialogOpen && (
        <LimitProfileDialog
          key={`${kind}-${editing?.id ?? "new-profile"}`}
          kind={profileName}
          profile={editing}
          users={users}
          onClose={() => {
            setDialogOpen(false);
            setEditing(null);
          }}
          onSubmit={saveProfile}
        />
      )}
    </>
  );
}

type UserLimit = {
  username: string;
  name: string;
  tps: number | null;
  n: number | null;
  tpsActive: boolean;
  nActive: boolean;
};

type UserLimitAssignment = {
  id: string;
  name: string;
  value: number;
  description: string;
  active: boolean;
};

export function UserLimitAssignments({
  user,
  kind,
  value,
  onSave,
  onNotice,
}: {
  user: UserRecord;
  kind: "TPS" | "N-address";
  value: number;
  onSave: (value: number) => void;
  onNotice: (message: string) => void;
}) {
  const unit = kind === "TPS" ? "messages per second" : "recipients per request";
  const valueHeading = kind === "TPS" ? "Messages / second" : "Recipients / request";
  const [assignments, setAssignments] = useState<UserLimitAssignment[]>([
    {
      id: `${kind}-${user.email}`,
      name: "Current limit",
      value,
      description: `User-specific limit: ${value.toLocaleString()} ${unit}.`,
      active: user.status === "Active",
    },
  ]);
  const [editing, setEditing] = useState<UserLimitAssignment | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [limitValue, setLimitValue] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const openDialog = (assignment?: UserLimitAssignment) => {
    setEditing(assignment ?? null);
    setCreating(!assignment);
    setName(assignment?.name ?? "");
    setLimitValue(assignment ? String(assignment.value) : "");
    setDescription(assignment?.description ?? "");
    setError("");
  };

  const closeDialog = () => {
    setEditing(null);
    setCreating(false);
    setError("");
  };

  const saveAssignment = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedValue = Number(limitValue);
    if (!name.trim() || !description.trim() || !Number.isInteger(parsedValue) || parsedValue < 1) {
      setError(`Enter a name, a whole-number ${kind} limit above zero, and a description.`);
      return;
    }

    const next: UserLimitAssignment = {
      id: editing?.id ?? `${kind}-${user.email}-${Date.now()}`,
      name: name.trim(),
      value: parsedValue,
      description: description.trim(),
      active: editing?.active ?? true,
    };
    setAssignments((current) =>
      editing
        ? current.map((assignment) => (assignment.id === editing.id ? next : assignment))
        : [...current, next],
    );
    onSave(parsedValue);
    onNotice(`${kind} assignment ${editing ? "updated" : "added"} for ${user.name}.`);
    closeDialog();
  };

  const deleteAssignment = (assignment: UserLimitAssignment) => {
    if (!window.confirm(`Delete ${assignment.name} from ${user.name}'s ${kind} assignments?`)) {
      return;
    }
    setAssignments((current) => current.filter((item) => item.id !== assignment.id));
    onNotice(`${assignment.name} removed from ${user.name}'s ${kind} assignments.`);
  };

  return (
    <>
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border p-5">
          <div>
            <h2 className="font-display text-sm font-bold">{kind} assignments</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Assigned {kind} limits for {user.name}.
            </p>
          </div>
          <Button size="sm" onClick={() => openDialog()}>
            <Plus /> Add {kind} limit
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                {["Name", valueHeading, "Description", "Status"].map((heading) => (
                  <th key={heading} className="whitespace-nowrap px-5 py-3 font-semibold">
                    {heading}
                  </th>
                ))}
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((assignment) => (
                <tr key={assignment.id} className="border-t border-border hover:bg-surface">
                  <td className="whitespace-nowrap px-5 py-4 font-semibold">{assignment.name}</td>
                  <td className="whitespace-nowrap px-5 py-4">
                    {assignment.value.toLocaleString()}
                    {kind === "TPS" ? " / sec" : ""}
                  </td>
                  <td className="px-5 py-4 text-muted-foreground">{assignment.description}</td>
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${assignment.active ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}
                    >
                      <span className="size-1.5 rounded-full bg-current" />
                      {assignment.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Edit ${assignment.name}`}
                        onClick={() => openDialog(assignment)}
                      >
                        <Pencil /> Edit
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Delete ${assignment.name}`}
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteAssignment(assignment)}
                      >
                        <Trash2 /> Delete
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {assignments.length === 0 && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No {kind} limits assigned to this user.
            </p>
          )}
        </div>
      </div>
      {(creating || editing) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
          <form
            role="dialog"
            aria-modal="true"
            aria-label={`${editing ? "Edit" : "Add"} ${kind} limit`}
            onSubmit={saveAssignment}
            className="w-full max-w-lg rounded-md border border-border bg-card shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="font-display text-lg font-bold">
                {editing ? "Edit" : "Add"} {kind} limit
              </h2>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close"
                onClick={closeDialog}
              >
                <X />
              </Button>
            </div>
            <div className="grid gap-4 p-5">
              <label className="block text-xs font-semibold">
                Limit name
                <Input
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className="mt-1.5 bg-background"
                />
              </label>
              <label className="block text-xs font-semibold">
                {kind === "TPS" ? "Messages per second" : "Recipients per request"}
                <Input
                  required
                  type="number"
                  min="1"
                  step="1"
                  value={limitValue}
                  onChange={(event) => setLimitValue(event.target.value)}
                  className="mt-1.5 bg-background"
                />
              </label>
              <label className="block text-xs font-semibold">
                Description
                <Textarea
                  required
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  className="mt-1.5 bg-background"
                />
              </label>
              {error && (
                <p role="alert" className="text-xs text-destructive">
                  {error}
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-5 py-4">
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancel
              </Button>
              <Button type="submit">
                <Check /> Save
              </Button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

export function UserLimitsLists({
  users,
  onNotice,
  kind,
}: {
  users: UserRecord[];
  onNotice: (message: string) => void;
  kind: "TPS" | "N-address";
}) {
  const [limits, setLimits] = useState<UserLimit[]>(() =>
    users.map((user) => ({
      username: user.username ?? user.email.split("@")[0] ?? "",
      name: user.name,
      tps: user.tps,
      n: user.n,
      tpsActive: user.status === "Active",
      nActive: user.status === "Active",
    })),
  );
  const [editing, setEditing] = useState<{ username: string; kind: "TPS" | "N-address" } | null>(
    null,
  );
  const [value, setValue] = useState("");

  const beginEdit = (username: string, kind: "TPS" | "N-address", current: number) => {
    setEditing({ username, kind });
    setValue(String(current));
  };

  const saveLimit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextValue = Number(value);
    if (!Number.isFinite(nextValue) || nextValue < 1) {
      onNotice("Enter a limit greater than zero.");
      return;
    }
    setLimits((current) =>
      current.map((limit) => {
        if (limit.username !== editing?.username) return limit;
        return editing.kind === "TPS" ? { ...limit, tps: nextValue } : { ...limit, n: nextValue };
      }),
    );
    onNotice(`${editing?.kind} limit updated in this preview.`);
    setEditing(null);
  };

  const toggleLimit = (username: string, kind: "TPS" | "N-address") => {
    setLimits((current) =>
      current.map((limit) => {
        if (limit.username !== username) return limit;
        return kind === "TPS"
          ? { ...limit, tpsActive: !limit.tpsActive }
          : { ...limit, nActive: !limit.nActive };
      }),
    );
    onNotice(`${username} ${kind} limit status changed in this preview.`);
  };

  const deleteLimit = (username: string, kind: "TPS" | "N-address") => {
    setLimits((current) =>
      current.map((limit) => {
        if (limit.username !== username) return limit;
        return kind === "TPS" ? { ...limit, tps: null } : { ...limit, n: null };
      }),
    );
    onNotice(`${username} ${kind} limit removed from this preview.`);
  };

  const renderTable = (kind: "TPS" | "N-address") => {
    const configuredLimits = limits.filter((limit) =>
      kind === "TPS" ? limit.tps !== null : limit.n !== null,
    );
    return (
      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="border-b border-border px-5 py-4">
          <h2 className="font-display text-sm font-bold">
            {kind === "TPS" ? "TPS limits" : "N-address limits"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            User-specific {kind === "TPS" ? "messages-per-second" : "recipient-per-request"}{" "}
            settings.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-5 py-3 font-semibold">Username</th>
                <th className="px-5 py-3 font-semibold">User</th>
                <th className="px-5 py-3 font-semibold">
                  {kind === "TPS" ? "Messages / second" : "Addresses / request"}
                </th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {configuredLimits.map((limit) => {
                const currentValue = kind === "TPS" ? limit.tps : limit.n;
                const isActive = kind === "TPS" ? limit.tpsActive : limit.nActive;
                if (currentValue === null) return null;
                return (
                  <tr key={limit.username} className="border-t border-border hover:bg-surface">
                    <td className="px-5 py-4 font-mono font-semibold">{limit.username}</td>
                    <td className="px-5 py-4">{limit.name}</td>
                    <td className="px-5 py-4">{currentValue.toLocaleString()}</td>
                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${isActive ? "bg-success-soft text-success" : "bg-muted text-muted-foreground"}`}
                      >
                        <span className="size-1.5 rounded-full bg-current" />
                        {isActive ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Edit ${kind} for ${limit.username}`}
                          title={`Edit ${kind} limit`}
                          onClick={() => beginEdit(limit.username, kind, currentValue)}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`${isActive ? "Deactivate" : "Activate"} ${kind} limit for ${limit.username}`}
                          title={isActive ? `Deactivate ${kind} limit` : `Activate ${kind} limit`}
                          onClick={() => toggleLimit(limit.username, kind)}
                        >
                          <Power />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${kind} limit for ${limit.username}`}
                          title={`Delete ${kind} limit`}
                          className="text-destructive hover:text-destructive"
                          onClick={() => deleteLimit(limit.username, kind)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {configuredLimits.length === 0 && (
            <p className="py-10 text-center text-sm text-muted-foreground">
              No user limits configured.
            </p>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="mt-6">{renderTable(kind)}</div>
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 p-4">
          <form
            role="dialog"
            aria-modal="true"
            aria-label={`Edit ${editing.kind} limit`}
            onSubmit={saveLimit}
            className="w-full max-w-sm rounded-md border border-border bg-card p-5 shadow-xl"
          >
            <h2 className="font-display text-lg font-bold">Edit {editing.kind} limit</h2>
            <p className="mt-1 text-xs text-muted-foreground">{editing.username}</p>
            <label className="mt-5 block text-xs font-semibold">
              {editing.kind === "TPS" ? "Messages per second" : "Addresses per request"}
              <Input
                autoFocus
                type="number"
                min="1"
                required
                value={value}
                onChange={(event) => setValue(event.target.value)}
                className="mt-1.5 bg-background"
              />
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setEditing(null)}>
                Cancel
              </Button>
              <Button type="submit">
                <Check /> Save
              </Button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
