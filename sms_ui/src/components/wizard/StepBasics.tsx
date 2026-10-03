import { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { WizardData, Channel } from "@/types/campaign";
import { CHANNEL_LABELS } from "@/types/campaign";
import {
  fetchAssignedConfigurations,
  type SenderIdConfig,
  type SupportedChannel,
} from "@/lib/api/configurations";

interface Props {
  data: WizardData;
  errors: Record<string, string>;
  update: (partial: Partial<WizardData>) => void;
}

export default function StepBasics({ data, errors, update }: Props) {
  const [senderIds, setSenderIds] = useState<SenderIdConfig[]>([]);
  const [channels, setChannels] = useState<SupportedChannel[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [optionsError, setOptionsError] = useState("");
  const [ownerEmailDraft, setOwnerEmailDraft] = useState("");
  const [ownerEmailError, setOwnerEmailError] = useState("");

  useEffect(() => {
    let mounted = true;
    fetchAssignedConfigurations()
      .then((assigned) => {
        if (!mounted) return;
        const activeSenderIds = assigned.sender_ids.filter((item) => item.is_active);
        const activeChannels = assigned.channels.filter((item) => item.is_active);
        setSenderIds(activeSenderIds);
        setChannels(activeChannels);

        const senderStillAvailable = activeSenderIds.some((item) => item.sender_id === data.sender_id);
        const selectedChannel = data.channels?.[0];
        const channelStillAvailable = activeChannels.some((item) => item.code === selectedChannel);
        update({
          sender_id: senderStillAvailable ? data.sender_id : "",
          channels: channelStillAvailable
            ? [selectedChannel]
            : activeChannels[0]
              ? [activeChannels[0].code as Channel]
              : [],
        });
      })
      .catch(() => {
        if (mounted) setOptionsError("Unable to load your assigned Sender IDs and channels.");
      })
      .finally(() => {
        if (mounted) setLoadingOptions(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  function addOwnerEmail() {
    const emails = ownerEmailDraft.split(/[\s,;]+/).map((email) => email.trim().toLowerCase()).filter(Boolean);
    if (emails.length === 0) return;
    const invalid = emails.find((email) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email));
    if (invalid) { setOwnerEmailError(`Enter a valid email address: ${invalid}`); return; }
    const nextEmails = [...new Set([...data.owner_emails, ...emails])];
    if (nextEmails.length > 50) { setOwnerEmailError("A campaign can have at most 50 owners."); return; }
    update({ owner_emails: nextEmails });
    setOwnerEmailDraft("");
    setOwnerEmailError("");
  }

  return (
    <div className="space-y-5">
      {/* Name */}
      <div className="space-y-1.5">
        <Label htmlFor="name">Campaign name</Label>
        <Input
          id="name"
          value={data.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="e.g. Summer Sale Kickoff"
        />
        {errors.name && <p className="text-sm text-destructive">{errors.name}</p>}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="owner-email">Owner email addresses</Label>
        <div className="flex gap-2">
          <Input
            id="owner-email"
            type="text"
            value={ownerEmailDraft}
            onChange={(event) => setOwnerEmailDraft(event.target.value)}
            onBlur={addOwnerEmail}
            onKeyDown={(event) => { if (["Enter", ",", ";"].includes(event.key)) { event.preventDefault(); addOwnerEmail(); } }}
            aria-invalid={Boolean(ownerEmailError)}
            placeholder="owner@example.com; another@example.com"
          />
          <Button type="button" variant="outline" size="icon" aria-label="Add owner email" onClick={addOwnerEmail}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        {data.owner_emails.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.owner_emails.map((email) => (
              <Badge key={email} variant="secondary" className="gap-1">
                {email}
                <button
                  type="button"
                  aria-label={`Remove ${email}`}
                  onClick={() => update({ owner_emails: data.owner_emails.filter((value) => value !== email) })}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
        {ownerEmailError && <p className="text-sm text-destructive">{ownerEmailError}</p>}
        <p className="text-xs text-muted-foreground">Up to 50 addresses. Press Enter or leave the field to add them. Owners receive campaign notices and can be selected for email reports.</p>
      </div>

      {/* Sender ID */}
      <div className="space-y-1.5">
        <Label htmlFor="sender_id">Sender ID</Label>
        <Select
          value={data.sender_id}
          onValueChange={(sender_id) => update({ sender_id })}
          disabled={loadingOptions || senderIds.length === 0}
        >
          <SelectTrigger id="sender_id">
            <SelectValue placeholder={loadingOptions ? "Loading sender IDs..." : senderIds.length ? "Select a sender ID" : "No Sender IDs assigned"} />
          </SelectTrigger>
          <SelectContent>
            {senderIds.map((sender) => (
              <SelectItem key={sender.id} value={sender.sender_id}>
                {sender.sender_id} {sender.name ? `- ${sender.name}` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.sender_id && <p className="text-sm text-destructive">{errors.sender_id}</p>}
      </div>

      {/* Channels */}
      <div className="space-y-2">
        <Label htmlFor="channel">Channel</Label>
        <Select
          value={data.channels?.[0] || ""}
          onValueChange={(channel) => update({ channels: [channel as Channel] })}
          disabled={loadingOptions || channels.length === 0}
        >
          <SelectTrigger id="channel">
            <SelectValue placeholder={loadingOptions ? "Loading channels..." : channels.length ? "Select a channel" : "No channels assigned"} />
          </SelectTrigger>
          <SelectContent>
            {channels.map((channel) => (
              <SelectItem key={channel.id} value={channel.code}>
                {CHANNEL_LABELS[channel.code as Channel] || channel.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.channels && <p className="text-sm text-destructive">{errors.channels}</p>}
      </div>

      {optionsError && <p className="text-sm text-destructive">{optionsError}</p>}
    </div>
  );
}
