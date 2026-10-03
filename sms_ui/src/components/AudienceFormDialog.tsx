import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { createAudience, updateAudience, fetchAudienceDetail } from "@/lib/api/audiences";
import type { ApiAudienceDetail, AudienceRecipient } from "@/lib/api/audiences";

interface AudienceFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  audienceId?: number | null;
  onSuccess: () => void;
}

export default function AudienceFormDialog({
  open,
  onOpenChange,
  audienceId,
  onSuccess,
}: AudienceFormDialogProps) {
  const isEdit = !!audienceId;
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [campaign, setCampaign] = useState("");
  const [recipientsText, setRecipientsText] = useState("");

  useEffect(() => {
    if (open && audienceId) {
      setFetching(true);
      fetchAudienceDetail(audienceId)
        .then((d: ApiAudienceDetail) => {
          setCampaign(String(d.campaign));
          const preview = d.recipients_preview || [];
          setRecipientsText(preview.map((r) => `${r.msisdn},${r.lang}`).join("\n"));
        })
        .catch(() => toast.error("Failed to load audience data"))
        .finally(() => setFetching(false));
    } else if (open) {
      setCampaign("");
      setRecipientsText("");
    }
  }, [open, audienceId]);

  function parseRecipients(text: string): AudienceRecipient[] {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [msisdn, lang = "en"] = line.split(",").map((s) => s.trim());
        return { msisdn, lang };
      });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const recipients = parseRecipients(recipientsText);
    if (!campaign || recipients.length === 0) {
      toast.error("Please provide a campaign ID and at least one recipient");
      return;
    }
    setLoading(true);
    try {
      if (isEdit) {
        await updateAudience(audienceId!, { recipients });
        toast.success("Audience updated successfully");
      } else {
        await createAudience({ campaign: Number(campaign), recipients });
        toast.success("Audience created successfully");
      }
      onOpenChange(false);
      onSuccess();
    } catch (err: any) {
      toast.error(err?.message || "Operation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Audience" : "Create Audience"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the audience recipients below."
              : "Fill in the campaign ID and recipients to create a new audience."}
          </DialogDescription>
        </DialogHeader>
        {fetching ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Loading...</div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="campaign">Campaign ID *</Label>
              <Input
                id="campaign"
                type="number"
                value={campaign}
                onChange={(e) => setCampaign(e.target.value)}
                placeholder="e.g. 1"
                required
                disabled={isEdit}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="recipients">Recipients (one per line: msisdn,lang) *</Label>
              <Textarea
                id="recipients"
                value={recipientsText}
                onChange={(e) => setRecipientsText(e.target.value)}
                placeholder={"+251911234567,en\n+251922345678,am"}
                rows={6}
              />
              <p className="text-xs text-muted-foreground">
                {parseRecipients(recipientsText).length} recipient(s) parsed
              </p>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "Saving..." : isEdit ? "Update" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
