import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  CircleCheck,
  CircleX,
  Copy,
  Eye,
  LoaderCircle,
  Plus,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createTestMessage,
  deleteTestMessage,
  fetchTestMessage,
  fetchTestMessages,
  fetchTestSmsOptions,
  resendTestMessage,
  TestSmsApiError,
  type TestMessage,
  type TestMessageInput,
  type TestSmsOption,
} from "@/lib/api/testSms";

const blankForm = (): TestMessageInput => ({
  sender_id: "",
  recipient: "",
  channel_code: "",
  message_content: "",
  test_campaign_id: 9999,
});

function responseText(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function apiMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed. Try again.";
}

function StatusMark({ row }: { row: TestMessage }) {
  if (row.accepted) {
    return <Badge className="gap-1 bg-emerald-700 hover:bg-emerald-700"><CircleCheck className="h-3 w-3" />{row.provider_status || "submitted"}</Badge>;
  }
  return <Badge variant="destructive" className="gap-1"><CircleX className="h-3 w-3" />{row.provider_status || "failed"}</Badge>;
}

export default function TestSms() {
  const [rows, setRows] = useState<TestMessage[]>([]);
  const [senderIds, setSenderIds] = useState<TestSmsOption[]>([]);
  const [channels, setChannels] = useState<TestSmsOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [newOpen, setNewOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<TestMessage | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [form, setForm] = useState<TestMessageInput>(blankForm);
  const [formErrors, setFormErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState("");
  const [sending, setSending] = useState(false);
  const [resending, setResending] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TestMessage | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [messageResponse, assignedOptions] = await Promise.all([
        fetchTestMessages(10),
        fetchTestSmsOptions(),
      ]);
      setRows(messageResponse.results);
      setSenderIds(assignedOptions.senderIds);
      setChannels(assignedOptions.channels);
    } catch (error) {
      toast.error(apiMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  function openNew() {
    setForm({
      ...blankForm(),
      sender_id: senderIds.find((option) => option.is_default)?.sender_id ?? senderIds[0]?.sender_id ?? "",
      channel_code: channels.find((option) => option.code === "sms")?.code ?? channels[0]?.code ?? "",
    });
    setFormErrors({});
    setFormError("");
    setNewOpen(true);
  }

  function fieldError(field: string) {
    return formErrors[field]?.[0];
  }

  async function submitTest() {
    setFormErrors({});
    setFormError("");
    if (!/^\d{7,20}$/.test(form.recipient)) {
      setFormErrors({ recipient: ["Enter 7 to 20 digits."] });
      return;
    }
    if (!form.sender_id || !form.channel_code) {
      setFormError("Choose an active Sender ID and channel.");
      return;
    }
    if (!form.message_content.trim()) {
      setFormErrors({ message_content: ["Message content cannot be blank."] });
      return;
    }

    setSending(true);
    try {
      const result = await createTestMessage(form);
      setNewOpen(false);
      toast[result.accepted ? "success" : "error"](
        result.accepted ? `SMS accepted by provider${result.provider_message_id ? ` · ${result.provider_message_id}` : ""}` : result.error_message || "SMSC rejected the test message",
      );
      await load();
    } catch (error) {
      if (error instanceof TestSmsApiError) {
        setFormErrors(error.fields);
        setFormError(Object.keys(error.fields).length ? "Check the highlighted fields." : error.message);
      } else {
        setFormError(apiMessage(error));
      }
    } finally {
      setSending(false);
    }
  }

  async function openDetail(row: TestMessage) {
    setDetail(row);
    setDetailOpen(true);
    setLoadingDetail(true);
    try {
      setDetail(await fetchTestMessage(row.id));
    } catch (error) {
      toast.error(apiMessage(error));
    } finally {
      setLoadingDetail(false);
    }
  }

  async function resend(row: TestMessage) {
    setResending(row.id);
    try {
      const result = await resendTestMessage(row.id);
      toast[result.accepted ? "success" : "error"](
        result.accepted ? "Test SMS accepted" : result.error_message || "SMSC rejected the resend",
      );
      await load();
      if (detailOpen && detail?.id === row.id) setDetail(await fetchTestMessage(result.id));
    } catch (error) {
      toast.error(apiMessage(error));
    } finally {
      setResending(null);
    }
  }

  async function removeTest() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteTestMessage(deleteTarget.id);
      toast.success("Test message deleted");
      setDeleteTarget(null);
      if (detail?.id === deleteTarget.id) setDetailOpen(false);
      await load();
    } catch (error) {
      toast.error(apiMessage(error));
    } finally {
      setDeleting(false);
    }
  }

  async function copyProviderId() {
    if (!detail?.provider_message_id) return;
    try {
      await navigator.clipboard.writeText(detail.provider_message_id);
      toast.success("Provider ID copied");
    } catch {
      toast.error("Clipboard access is unavailable");
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Tools / SMSC</p>
          <h1 className="mt-1 text-2xl font-semibold">Test SMS</h1>
          <p className="mt-1 text-sm text-muted-foreground">SMSC test submissions</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => void load()} disabled={loading} aria-label="Refresh test history" title="Refresh">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          <Button type="button" onClick={openNew}>
            <Plus className="mr-2 h-4 w-4" />New Test
          </Button>
        </div>
      </header>

      <section aria-labelledby="recent-tests-heading">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="recent-tests-heading" className="text-base font-semibold">Recent Tests</h2>
          <span className="text-xs text-muted-foreground">Last {rows.length} of 10</span>
        </div>
        <div className="overflow-x-auto border border-border">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Recipient</th>
                <th className="px-4 py-3 font-medium">Sender</th>
                <th className="px-4 py-3 font-medium">Channel</th>
                <th className="px-4 py-3 font-medium">Message</th>
                <th className="px-4 py-3 font-medium">Result</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">Loading test history…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">No test messages yet.</td></tr>
              ) : rows.map((row) => (
                <tr key={row.id} className="border-t border-border align-middle hover:bg-muted/30">
                  <td className="px-4 py-3 font-semibold tabular-nums">{row.recipient}</td>
                  <td className="px-4 py-3">{row.sender_id}</td>
                  <td className="px-4 py-3"><Badge variant="outline">{row.channel_code.toUpperCase()}</Badge></td>
                  <td className="max-w-[240px] truncate px-4 py-3 text-muted-foreground" title={row.message_content}>{row.message_content}</td>
                  <td className="px-4 py-3"><StatusMark row={row} /></td>
                  <td className="px-4 py-3 tabular-nums text-muted-foreground">{row.duration_ms} ms</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button type="button" size="icon" variant="ghost" title="Resend" aria-label={`Resend test ${row.id}`} disabled={resending === row.id} onClick={() => void resend(row)}>
                        {resending === row.id ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      </Button>
                      <Button type="button" size="icon" variant="ghost" title="View details" aria-label={`View test ${row.id}`} onClick={() => void openDetail(row)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button type="button" size="icon" variant="ghost" title="Delete" aria-label={`Delete test ${row.id}`} onClick={() => setDeleteTarget(row)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Dialog open={newOpen} onOpenChange={(open) => { if (!sending) setNewOpen(open); }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>New Test SMS</DialogTitle>
            <DialogDescription>Submit directly to the active SMSC configuration.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="test-sms-sender">Sender ID <span className="text-destructive">*</span></Label>
              <Select value={form.sender_id} onValueChange={(sender_id) => setForm((previous) => ({ ...previous, sender_id }))}>
                <SelectTrigger id="test-sms-sender"><SelectValue placeholder="Choose a Sender ID" /></SelectTrigger>
                <SelectContent>{senderIds.map((option) => <SelectItem key={option.id} value={option.sender_id ?? option.name}>{option.sender_id} · {option.name}</SelectItem>)}</SelectContent>
              </Select>
              {fieldError("sender_id") && <p className="text-xs text-destructive">{fieldError("sender_id")}</p>}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="test-sms-recipient">Recipient <span className="text-destructive">*</span></Label>
              <Input id="test-sms-recipient" value={form.recipient} inputMode="numeric" autoComplete="off" maxLength={20} placeholder="251799120001" onChange={(event) => setForm((previous) => ({ ...previous, recipient: event.target.value.replace(/\D/g, "").slice(0, 20) }))} aria-invalid={Boolean(fieldError("recipient"))} />
              {fieldError("recipient") && <p className="text-xs text-destructive">{fieldError("recipient")}</p>}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="test-sms-channel">Channel <span className="text-destructive">*</span></Label>
              <Select value={form.channel_code} onValueChange={(channel_code) => setForm((previous) => ({ ...previous, channel_code }))}>
                <SelectTrigger id="test-sms-channel"><SelectValue placeholder="Choose a channel" /></SelectTrigger>
                <SelectContent>{channels.map((option) => <SelectItem key={option.id} value={option.code ?? option.name}>{option.name} · {option.code}</SelectItem>)}</SelectContent>
              </Select>
              {fieldError("channel_code") && <p className="text-xs text-destructive">{fieldError("channel_code")}</p>}
            </div>

            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="test-sms-message">Message <span className="text-destructive">*</span></Label>
                <span className={`text-xs ${form.message_content.length >= 950 ? "text-amber-700" : "text-muted-foreground"}`}>{form.message_content.length} / 1000</span>
              </div>
              <Textarea id="test-sms-message" value={form.message_content} maxLength={1000} rows={4} onChange={(event) => setForm((previous) => ({ ...previous, message_content: event.target.value }))} aria-invalid={Boolean(fieldError("message_content"))} />
              {fieldError("message_content") && <p className="text-xs text-destructive">{fieldError("message_content")}</p>}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="test-sms-campaign-id">Test Campaign Tag</Label>
              <Input id="test-sms-campaign-id" type="number" min={0} max={999999} value={form.test_campaign_id} onChange={(event) => setForm((previous) => ({ ...previous, test_campaign_id: Number(event.target.value) }))} />
              {fieldError("test_campaign_id") && <p className="text-xs text-destructive">{fieldError("test_campaign_id")}</p>}
            </div>
            {formError && <p role="alert" className="text-sm text-destructive">{formError}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setNewOpen(false)} disabled={sending}>Cancel</Button>
            <Button type="button" onClick={() => void submitTest()} disabled={sending || senderIds.length === 0 || channels.length === 0}>
              {sending ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              {sending ? "Sending…" : "Send Test"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Test #{detail?.id} · {detail?.recipient}</DialogTitle>
            <DialogDescription>{detail?.sender_id} · {detail?.channel_code.toUpperCase()}</DialogDescription>
          </DialogHeader>
          {loadingDetail || !detail ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground"><LoaderCircle className="mr-2 h-4 w-4 animate-spin" />Loading details</div>
          ) : (
            <div className="space-y-5">
              <section className="grid gap-3 border-b border-border pb-4 sm:grid-cols-2 lg:grid-cols-4">
                <div><p className="text-xs text-muted-foreground">Result</p><div className="mt-1"><StatusMark row={detail} /></div></div>
                <div><p className="text-xs text-muted-foreground">Provider ID</p><p className="mt-1 break-all font-mono text-sm">{detail.provider_message_id || "—"}</p></div>
                <div><p className="text-xs text-muted-foreground">HTTP status</p><p className="mt-1 text-sm">{detail.http_status ?? "—"}</p></div>
                <div><p className="text-xs text-muted-foreground">Duration</p><p className="mt-1 text-sm">{detail.duration_ms} ms</p></div>
                <div className="sm:col-span-2 lg:col-span-4"><p className="text-xs text-muted-foreground">Submitted at</p><p className="mt-1 text-sm">{new Date(detail.created_at).toLocaleString()}</p></div>
                {detail.error_message && <p className="sm:col-span-2 lg:col-span-4 text-sm text-destructive">{detail.error_message}</p>}
              </section>
              <Payload title={`${detail.request_method} ${detail.request_url}`} value={detail.request_payload} />
              <Payload title="SMSC Response" value={detail.response_payload} />
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => void copyProviderId()} disabled={!detail?.provider_message_id}>
              <Copy className="mr-2 h-4 w-4" />Copy Provider ID
            </Button>
            {detail && <Button type="button" onClick={() => void resend(detail)} disabled={resending === detail.id}>
              {resending === detail.id ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}Resend
            </Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open && !deleting) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete test message?</AlertDialogTitle>
            <AlertDialogDescription>This only deletes the test record. It does not affect campaign messages.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={deleting} onClick={(event) => { event.preventDefault(); void removeTest(); }}>
              {deleting ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}

function Payload({ title, value }: { title: string; value: unknown }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <pre className="max-h-64 overflow-auto border border-border bg-muted/40 p-3 text-xs leading-relaxed"><code>{responseText(value)}</code></pre>
    </section>
  );
}