import { useMemo, useState, type FormEvent } from "react";
import {
  Download,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  LockOpen,
  Pencil,
  Plus,
  Power,
  Search,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type UserStatus = "Active" | "Inactive" | "Locked" | "Pending";

export type UserRecord = {
  profileId: number;
  userId: number;
  name: string;
  email: string;
  company: string;
  initials: string;
  status: UserStatus;
  smsc: number;
  sender: number;
  channels: number;
  tps: number;
  n: number;
  login: string;
  tone: string;
  username?: string;
  apiRole?: "ADMIN" | "CAMPAIGN_MANAGER";
  notes?: string;
  firstName?: string;
  lastName?: string;
  department?: string;
  role?: string;
  lastLoginAt?: string;
  requirePasswordChange?: boolean;
  assignedSmscs: number[];
  assignedSenderIds: number[];
  assignedChannels: number[];
  assignedTpsConfigs: number[];
  assignedNAddressConfigs: number[];
  assignedNAddresses: number[];
};

export type UserAssignmentOptions = {
  smscs: { id: number; label: string }[];
  senderIds: { id: number; label: string }[];
  channels: { id: number; label: string }[];
  tpsConfigs: { id: number; label: string }[];
  nAddressConfigs: { id: number; label: string }[];
  nAddresses: { id: number; label: string }[];
};

export type UserSaveInput = {
  username: string;
  email: string;
  firstName: string;
  lastName: string;
  department: string;
  role: "ADMIN" | "CAMPAIGN_MANAGER";
  password: string;
  isActive: boolean;
  isLocked: boolean;
  notes: string;
  tpsLimit: number | null;
  assignedSmscs: number[];
  assignedSenderIds: number[];
  assignedChannels: number[];
  assignedTpsConfigs: number[];
  assignedNAddressConfigs: number[];
  assignedNAddresses: number[];
};

type UserForm = {
  username: string;
  email: string;
  firstName: string;
  lastName: string;
  department: string;
  role: string;
  notes: string;
  password: string;
  confirmPassword: string;
};

const roles = ["Admin", "Campaign Manager"];
const pageSize = 20;

const emptyForm = (): UserForm => ({
  username: "",
  email: "",
  firstName: "",
  lastName: "",
  department: "",
  role: "",
  notes: "",
  password: "",
  confirmPassword: "",
});

function getNameParts(user: UserRecord) {
  const parts = user.name.trim().split(/\s+/);
  return {
    firstName: user.firstName ?? parts.shift() ?? "",
    lastName: user.lastName ?? parts.join(" "),
  };
}

function getUsername(user: UserRecord) {
  return user.username ?? user.email.split("@")[0] ?? "";
}

function StatusBadge({ status }: { status: UserStatus }) {
  const colors: Record<UserStatus, string> = {
    Active: "bg-success-soft text-success",
    Inactive: "bg-muted text-muted-foreground",
    Locked: "bg-danger-soft text-destructive",
    Pending: "bg-warning-soft text-warning",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[11px] font-semibold ${colors[status]}`}>
      <span className="size-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

function formatExactLogin(user: UserRecord) {
  if (!user.lastLoginAt) return "No login recorded";
  return new Date(user.lastLoginAt).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function UserFormDialog({
  users,
  user,
  onClose,
  onSave,
}: {
  users: UserRecord[];
  user: UserRecord | null;
  onClose: () => void;
  onSave: (record: UserRecord, payload: UserSaveInput) => Promise<void>;
}) {
  const nameParts = user ? getNameParts(user) : { firstName: "", lastName: "" };
  const [form, setForm] = useState<UserForm>(() =>
    user
      ? {
          ...emptyForm(),
          username: getUsername(user),
          email: user.email,
          ...nameParts,
          department: user.department ?? user.company,
          role: user.role ?? "",
          notes: user.notes ?? "",
        }
      : emptyForm(),
  );
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [saving, setSaving] = useState(false);

  const setValue = <K extends keyof UserForm>(key: K, value: UserForm[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (error) setError("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const username = form.username.trim();
    const email = form.email.trim();
    const firstName = form.firstName.trim();
    const lastName = form.lastName.trim();
    const department = form.department.trim();

    if (!username || !email || !department || !form.role) {
      setError("Complete all required fields.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("Enter a valid email address.");
      return;
    }

    const duplicate = users.find(
      (candidate) =>
        candidate !== user &&
        (getUsername(candidate).toLowerCase() === username.toLowerCase() ||
          candidate.email.toLowerCase() === email.toLowerCase()),
    );
    if (duplicate) {
      setError(
        getUsername(duplicate).toLowerCase() === username.toLowerCase()
          ? "That username is already in use."
          : "That email address is already in use.",
      );
      return;
    }

    if (!user && form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (user && form.password && form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    const name = [firstName, lastName].filter(Boolean).join(" ");
    const record: UserRecord = {
        ...(user ?? {
          profileId: 0,
          userId: 0,
          initials: "",
          status: "Pending" as const,
          smsc: 0,
          sender: 0,
          channels: 0,
          tps: 100,
          n: 250,
          login: "Never",
          tone: "mint",
          assignedSmscs: [],
          assignedSenderIds: [],
          assignedChannels: [],
          assignedTpsConfigs: [],
          assignedNAddressConfigs: [],
          assignedNAddresses: [],
        }),
        username,
        email,
        firstName,
        lastName,
        name: name || username,
        initials: (name || username)
          .split(/\s+/)
          .map((part) => part[0])
          .slice(0, 2)
          .join("")
          .toUpperCase(),
        department,
        company: department,
        role: form.role,
        notes: form.notes,
        tps: user?.tps ?? 0,
        assignedSmscs: user?.assignedSmscs ?? [],
        assignedSenderIds: user?.assignedSenderIds ?? [],
        assignedChannels: user?.assignedChannels ?? [],
        assignedTpsConfigs: user?.assignedTpsConfigs ?? [],
        assignedNAddressConfigs: user?.assignedNAddressConfigs ?? [],
        assignedNAddresses: user?.assignedNAddresses ?? [],
      };
    setSaving(true);
    setError("");
    try {
      await onSave(record, {
        username,
        email,
        firstName,
        lastName,
        department,
        role: form.role === "Admin" ? "ADMIN" : "CAMPAIGN_MANAGER",
        password: form.password,
        isActive: user ? user.status !== "Inactive" : true,
        isLocked: user?.status === "Locked",
        notes: form.notes,
        tpsLimit: user?.tps ?? null,
        assignedSmscs: user?.assignedSmscs ?? [],
        assignedSenderIds: user?.assignedSenderIds ?? [],
        assignedChannels: user?.assignedChannels ?? [],
        assignedTpsConfigs: user?.assignedTpsConfigs ?? [],
        assignedNAddressConfigs: user?.assignedNAddressConfigs ?? [],
        assignedNAddresses: user?.assignedNAddresses ?? [],
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save user.");
    } finally {
      setSaving(false);
    }
  };

  const fieldClass =
    "mt-1.5 h-9 bg-background text-sm";

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
        aria-labelledby="user-form-title"
        onSubmit={submit}
        className="admin-scroll max-h-[90vh] w-full max-w-[640px] overflow-y-auto rounded-md border border-border bg-card shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <div>
            <h2 id="user-form-title" className="font-display text-lg font-bold">
              {user ? "Edit user" : "Create user"}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Account details and role changes take effect immediately.
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X />
          </Button>
        </div>

        <div className="grid gap-4 p-6 sm:grid-cols-2">
          <label className="block text-xs font-semibold">
            Username <span className="text-destructive">*</span>
            <Input
              required
              autoComplete="username"
              maxLength={150}
              value={form.username}
              onChange={(event) => setValue("username", event.target.value)}
              placeholder="e.g. jdoe"
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-semibold">
            Email <span className="text-destructive">*</span>
            <Input
              required
              type="email"
              autoComplete="email"
              maxLength={254}
              value={form.email}
              onChange={(event) => setValue("email", event.target.value)}
              placeholder="name@example.com"
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-semibold">
            First name
            <Input
              autoComplete="given-name"
              maxLength={150}
              value={form.firstName}
              onChange={(event) => setValue("firstName", event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-semibold">
            Last name
            <Input
              autoComplete="family-name"
              maxLength={150}
              value={form.lastName}
              onChange={(event) => setValue("lastName", event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-semibold">
            Department <span className="text-destructive">*</span>
            <Input
              required
              maxLength={120}
              value={form.department}
              onChange={(event) => setValue("department", event.target.value)}
              placeholder="Type a department"
              className={fieldClass}
            />
          </label>
          <label className="block text-xs font-semibold">
            Role / Group <span className="text-destructive">*</span>
            <select
              required
              value={form.role}
              onChange={(event) => setValue("role", event.target.value)}
              className="mt-1.5 h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="" disabled>
                Select a role
              </option>
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-semibold sm:col-span-2">
            Notes
            <textarea
              value={form.notes}
              onChange={(event) => setValue("notes", event.target.value)}
              className="mt-1.5 min-h-20 w-full rounded-md border border-input bg-background p-3 text-sm font-normal"
            />
          </label>
          <label className="block text-xs font-semibold sm:col-span-2">
            Password {!user && <span className="text-destructive">*</span>}
            <span className="relative mt-1.5 block">
              <Input
                required={!user}
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                minLength={user ? undefined : 8}
                maxLength={128}
                value={form.password}
                onChange={(event) => setValue("password", event.target.value)}
                placeholder={user ? "Leave blank to keep current password" : "At least 8 characters"}
                className="h-9 bg-background pr-10 text-sm"
              />
              <button
                type="button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((visible) => !visible)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </span>
            {!user && <span className="mt-1 block text-[11px] font-normal text-muted-foreground">At least 8 characters</span>}
          </label>
          <label className="block text-xs font-semibold sm:col-span-2">
            Confirm password {!user && <span className="text-destructive">*</span>}
            <span className="relative mt-1.5 block">
              <Input
                required={!user || Boolean(form.password)}
                type={showConfirmPassword ? "text" : "password"}
                autoComplete="new-password"
                maxLength={128}
                value={form.confirmPassword}
                onChange={(event) => setValue("confirmPassword", event.target.value)}
                className="h-9 bg-background pr-10 text-sm"
              />
              <button
                type="button"
                aria-label={showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"}
                onClick={() => setShowConfirmPassword((visible) => !visible)}
                className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
              >
                {showConfirmPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </span>
          </label>

          {error && (
            <p role="alert" className="text-xs font-medium text-destructive sm:col-span-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : user ? "Save changes" : "Create user"}</Button>
        </div>
      </form>
    </div>
  );
}

export function UserEditor({
  users,
  user,
  onClose,
  onSave,
}: {
  users: UserRecord[];
  user: UserRecord;
  onClose: () => void;
  onSave: (record: UserRecord, payload: UserSaveInput) => Promise<void>;
}) {
  return (
    <UserFormDialog
      users={users}
      user={user}
      onClose={onClose}
      onSave={onSave}
    />
  );
}

export function UsersManagement({
  users,
  setUsers,
  onPersistUser,
  onDeleteUser,
  onUpdateAccount,
  onOpenUser,
  onNotice,
}: {
  users: UserRecord[];
  setUsers: (users: UserRecord[] | ((current: UserRecord[]) => UserRecord[])) => void;
  onPersistUser: (
    user: UserRecord | null,
    record: UserRecord,
    payload: UserSaveInput,
  ) => Promise<UserRecord>;
  onDeleteUser: (user: UserRecord) => Promise<void>;
  onUpdateAccount: (
    user: UserRecord,
    changes: { isActive: boolean; isLocked: boolean },
  ) => Promise<UserRecord>;
  onOpenUser: (user: UserRecord) => void;
  onNotice: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("All roles");
  const [departmentFilter, setDepartmentFilter] = useState("All departments");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [selected, setSelected] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<UserRecord | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const departments = useMemo(
    () => [...new Set(users.map((user) => user.department ?? user.company).filter(Boolean))].sort(),
    [users],
  );
  const filteredUsers = useMemo(() => {
    const search = query.trim().toLowerCase();
    return users.filter((user) => {
      const name = user.name.toLowerCase();
      const department = (user.department ?? user.company).toLowerCase();
      return (
        (!search ||
          `${getUsername(user)} ${name} ${user.email} ${department}`.toLowerCase().includes(search)) &&
        (roleFilter === "All roles" || (user.role ?? "") === roleFilter) &&
        (departmentFilter === "All departments" || department === departmentFilter.toLowerCase()) &&
        (statusFilter === "All statuses" || user.status === statusFilter)
      );
    });
  }, [users, query, roleFilter, departmentFilter, statusFilter]);

  const pageCount = Math.max(1, Math.ceil(filteredUsers.length / pageSize));
  const visibleUsers = filteredUsers.slice((page - 1) * pageSize, page * pageSize);
  const visibleUserIds = visibleUsers.map(getUsername);
  const allVisibleSelected =
    visibleUserIds.length > 0 && visibleUserIds.every((username) => selected.includes(username));

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const saveUser = async (record: UserRecord, payload: UserSaveInput) => {
    const saved = await onPersistUser(editing, record, payload);
    setUsers((current) =>
      editing
        ? current.map((candidate) => (candidate.profileId === editing.profileId ? saved : candidate))
        : [saved, ...current],
    );
    setFormOpen(false);
    setEditing(null);
    setPage(1);
    onNotice(editing ? "User changes saved." : "User created.");
  };

  const removeUsers = async (usernames: string[]) => {
    if (!window.confirm(`Delete ${usernames.length} selected user${usernames.length === 1 ? "" : "s"}?`)) {
      return;
    }
    try {
      for (const user of users.filter((candidate) => usernames.includes(getUsername(candidate)))) {
        await onDeleteUser(user);
        setUsers((current) => current.filter((candidate) => candidate.profileId !== user.profileId));
      }
      setSelected((current) => current.filter((username) => !usernames.includes(username)));
      onNotice(`${usernames.length} user${usernames.length === 1 ? "" : "s"} deleted.`);
    } catch (reason) {
      onNotice(reason instanceof Error ? reason.message : "Could not delete selected users.");
    }
  };

  const exportSelected = () => {
    const rows = users.filter((user) => selected.includes(getUsername(user)));
    const escapeCsv = (value: string) => `"${value.replaceAll('"', '""')}"`;
    const csv = [
      ["Username", "First name", "Last name", "Email", "Department", "Role", "Status"],
      ...rows.map((user) => {
        const { firstName, lastName } = getNameParts(user);
        return [
          getUsername(user),
          firstName,
          lastName,
          user.email,
          user.department ?? user.company,
          user.role ?? "",
          user.status,
        ];
      }),
    ]
      .map((row) => row.map(escapeCsv).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "users.csv";
    anchor.click();
    URL.revokeObjectURL(url);
    onNotice(`${rows.length} user${rows.length === 1 ? "" : "s"} exported.`);
  };

  const toggleStatus = async (user: UserRecord) => {
    if (user.status === "Locked") {
      onNotice("Unlock this user before changing their active status.");
      return;
    }
    const status: UserStatus = user.status === "Active" ? "Inactive" : "Active";
    try {
      const updated = await onUpdateAccount(user, {
        isActive: status === "Active",
        isLocked: false,
      });
      setUsers((current) =>
        current.map((candidate) => (candidate.profileId === user.profileId ? updated : candidate)),
      );
      onNotice(`${user.name} ${status === "Inactive" ? "deactivated" : "reactivated"}.`);
    } catch (reason) {
      onNotice(reason instanceof Error ? reason.message : "Could not update user status.");
    }
  };

  const toggleLock = async (user: UserRecord) => {
    const locked = user.status !== "Locked";
    try {
      const updated = await onUpdateAccount(user, {
        isActive: user.status !== "Inactive",
        isLocked: locked,
      });
      setUsers((current) =>
        current.map((candidate) => (candidate.profileId === user.profileId ? updated : candidate)),
      );
      onNotice(`${user.name} ${locked ? "locked" : "unlocked"}.`);
    } catch (reason) {
      onNotice(reason instanceof Error ? reason.message : "Could not update lock status.");
    }
  };

  const changePage = (nextPage: number) => {
    setPage(Math.min(pageCount, Math.max(1, nextPage)));
    setSelected([]);
  };

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-[27px] font-bold">Users</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage user accounts, roles, and access.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus /> Create User
        </Button>
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-wrap items-center gap-2 border-b border-border p-4">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="Search users"
              placeholder="Search by name, email, department..."
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
                setSelected([]);
              }}
              className="bg-background pl-9 text-xs"
            />
          </div>
          <select
            aria-label="Filter by role"
            value={roleFilter}
            onChange={(event) => {
              setRoleFilter(event.target.value);
              setPage(1);
              setSelected([]);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option>All roles</option>
            {roles.map((role) => (
              <option key={role}>{role}</option>
            ))}
            {[...new Set(users.map((user) => user.role).filter((role): role is string => Boolean(role)))]
              .filter((role) => !roles.includes(role))
              .map((role) => (
                <option key={role}>{role}</option>
              ))}
          </select>
          <select
            aria-label="Filter by department"
            value={departmentFilter}
            onChange={(event) => {
              setDepartmentFilter(event.target.value);
              setPage(1);
              setSelected([]);
            }}
            className="h-9 rounded-md border border-input bg-background px-2 text-xs"
          >
            <option>All departments</option>
            {departments.map((department) => (
              <option key={department}>{department}</option>
            ))}
          </select>
        </div>

        {selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-4 py-3">
            <span className="mr-auto text-xs font-medium">
              {selected.length} selected
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
              void (async () => {
                try {
                  for (const user of users.filter((candidate) => selected.includes(getUsername(candidate)))) {
                    if (user.status === "Locked") continue;
                    const updated = await onUpdateAccount(user, { isActive: false, isLocked: false });
                    setUsers((current) => current.map((candidate) =>
                      candidate.profileId === user.profileId ? updated : candidate,
                    ));
                  }
                  setSelected([]);
                  onNotice("Selected users disabled.");
                } catch (reason) {
                  onNotice(reason instanceof Error ? reason.message : "Could not disable selected users.");
                }
              })();
              }}
            >
              Disable
            </Button>
            <Button size="sm" variant="outline" onClick={exportSelected}>
              <Download /> Export
            </Button>
            <Button size="sm" variant="destructive" onClick={() => removeUsers(selected)}>
              <Trash2 /> Delete
            </Button>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[1050px] text-left text-xs">
            <thead className="bg-surface text-[10px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label="Select all visible users"
                    checked={allVisibleSelected}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...new Set([...current, ...visibleUserIds])]
                          : current.filter((username) => !visibleUserIds.includes(username)),
                      )
                    }
                    className="accent-primary"
                  />
                </th>
                {["Username", "Name", "Email", "Department", "Role / Group", "Status", "Last login", "Actions"].map(
                  (heading) => (
                    <th key={heading} className="whitespace-nowrap px-4 py-3 font-semibold">
                      {heading}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {visibleUsers.map((user) => {
                const username = getUsername(user);
                return (
                  <tr key={username} className="border-t border-border hover:bg-surface">
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${username}`}
                        checked={selected.includes(username)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, username]
                              : current.filter((item) => item !== username),
                          )
                        }
                        className="accent-primary"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Button
                        variant="ghost"
                        onClick={() => onOpenUser(user)}
                        className="h-auto justify-start p-0 font-mono text-xs font-semibold text-primary underline-offset-4 hover:bg-transparent hover:underline"
                        aria-label={`View details for ${username}`}
                      >
                        {username}
                      </Button>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <Button
                        variant="ghost"
                        onClick={() => onOpenUser(user)}
                        className="h-auto justify-start p-0 text-left text-xs font-semibold hover:bg-transparent"
                      >
                        {user.name}
                      </Button>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{user.email}</td>
                    <td className="px-4 py-3 text-muted-foreground">{user.department ?? user.company}</td>
                    <td className="px-4 py-3">{user.role ?? "—"}</td>
                    <td className="px-4 py-3"><StatusBadge status={user.status} /></td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground" title={formatExactLogin(user)}>
                      {user.login}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Edit ${username}`}
                          title="Edit user"
                          onClick={() => {
                            setEditing(user);
                            setFormOpen(true);
                          }}
                        >
                          <Pencil />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`${user.status === "Locked" ? "Unlock" : "Lock"} ${username}`}
                          title={user.status === "Locked" ? "Unlock user" : "Lock user"}
                          onClick={() => toggleLock(user)}
                        >
                          {user.status === "Locked" ? <LockOpen /> : <Lock />}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={user.status === "Active" ? `Deactivate ${username}` : `Reactivate ${username}`}
                          title={user.status === "Active" ? "Deactivate user" : "Reactivate user"}
                          disabled={user.status === "Locked"}
                          onClick={() => toggleStatus(user)}
                        >
                          <Power />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Reset password for ${username}`}
                          title="Reset password"
                          onClick={() => {
                            setEditing(user);
                            setFormOpen(true);
                            onNotice("Enter a new password and confirmation, then save the user.");
                          }}
                        >
                          <KeyRound />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Delete ${username}`}
                          title="Delete user"
                          className="text-destructive hover:text-destructive"
                          onClick={() => removeUsers([username])}
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
          {visibleUsers.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-14 text-center">
              <Users className="size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">No users match these filters.</p>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
          <span className="text-xs text-muted-foreground">
            Showing {filteredUsers.length ? (page - 1) * pageSize + 1 : 0}–
            {Math.min(page * pageSize, filteredUsers.length)} of {filteredUsers.length} users
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => changePage(page - 1)}
            >
              ‹ Prev
            </Button>
            {Array.from({ length: pageCount }, (_, index) => index + 1).map((number) => (
              <Button
                key={number}
                variant={page === number ? "secondary" : "ghost"}
                size="sm"
                aria-current={page === number ? "page" : undefined}
                onClick={() => changePage(number)}
              >
                {number}
              </Button>
            ))}
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pageCount}
              onClick={() => changePage(page + 1)}
            >
              Next ›
            </Button>
          </div>
        </div>
      </div>

      {formOpen && (
        <UserFormDialog
          key={editing ? getUsername(editing) : "new-user"}
          users={users}
          user={editing}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
          onSave={saveUser}
        />
      )}
    </>
  );
}
