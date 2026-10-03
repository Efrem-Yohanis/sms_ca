import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Campaign } from "@/types/campaign";
import { LANGUAGE_LABELS, SCHEDULE_TYPE_LABELS, DAY_LABELS } from "@/types/campaign";
import type { Language } from "@/types/campaign";

interface Props {
  campaign: Campaign;
  open: boolean;
  onClose: () => void;
}

export default function CampaignDetailDialog({ campaign, open, onClose }: Props) {
  const c = campaign;

  const filledLangs = (Object.entries(c.message_content.content) as [Language, string][])
    .filter(([, text]) => text.trim())
    .map(([lang]) => LANGUAGE_LABELS[lang]);

  const langText = filledLangs.length > 1
    ? filledLangs.slice(0, -1).join(", ") + " and " + filledLangs[filledLangs.length - 1]
    : filledLangs[0] || "none";

  const daysText = c.schedule.run_days?.map((d) => DAY_LABELS[d] || `Day ${d}`).join(", ") || "";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Campaign Details</DialogTitle>
        </DialogHeader>
        <div className="font-serif text-base leading-relaxed text-foreground space-y-4 py-2">
          <p>
            The campaign <strong>"{c.name}"</strong>
            {c.sender_id && <> with sender ID <strong>"{c.sender_id}"</strong></>}
            {" "}is scheduled from{" "}
            <strong>{c.schedule.start_date}</strong>
            {c.schedule.end_date && <> to <strong>{c.schedule.end_date}</strong></>}.
            It runs <strong>{SCHEDULE_TYPE_LABELS[c.schedule.schedule_type]}</strong>
            {daysText && <> on <strong>{daysText}</strong></>}.
            Messages are delivered in <strong>{langText}</strong> (default: {LANGUAGE_LABELS[c.message_content.default_language]}).
            Audience: <strong>{c.audience.total_count.toLocaleString()} recipients</strong>
            {c.audience.invalid_count > 0 && <> ({c.audience.invalid_count} invalid)</>}.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
