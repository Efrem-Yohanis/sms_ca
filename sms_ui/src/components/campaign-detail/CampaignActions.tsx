import { Play, Pause, Square, CheckCircle, Repeat, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Campaign } from "@/types/campaign";
import { startCampaign, pauseCampaign, resumeCampaign, stopCampaign, completeCampaign, archiveCampaign } from "@/lib/api";
import { toast } from "sonner";
import { useState } from "react";

interface CampaignActionsProps {
  campaign: Campaign;
  onActionComplete: () => void;
}

export function CampaignActions({ campaign, onActionComplete }: CampaignActionsProps) {
  const [acting, setActing] = useState(false);
  const id = Number(campaign.id);

  async function handleAction(action: () => Promise<{ message: string }>, label: string) {
    setActing(true);
    try {
      const result = await action();
      toast.success(result.message || `${label} successful`);
      onActionComplete();
    } catch (err: any) {
      toast.error(`Failed to ${label.toLowerCase()}: ${err.message}`);
    } finally {
      setActing(false);
    }
  }

  const isRecurring = campaign.schedule?.schedule_type !== "once";

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {campaign.can_start && (
        <Button size="sm" disabled={acting} onClick={() => handleAction(() => startCampaign(id), "Start")} className="gap-1.5">
          <Play className="h-3.5 w-3.5" /> Start Campaign
        </Button>
      )}
      {campaign.can_pause && (
        <Button size="sm" variant="outline" disabled={acting} onClick={() => handleAction(() => pauseCampaign(id), "Pause")} className="gap-1.5">
          <Pause className="h-3.5 w-3.5" /> Pause
        </Button>
      )}
      {campaign.can_resume && (
        <Button size="sm" disabled={acting} onClick={() => handleAction(() => resumeCampaign(id), "Resume")} className="gap-1.5">
          <Play className="h-3.5 w-3.5" /> Resume
        </Button>
      )}
      {campaign.can_stop && (
        <Button size="sm" variant="destructive" disabled={acting} onClick={() => handleAction(() => stopCampaign(id), "Stop")} className="gap-1.5">
          <Square className="h-3.5 w-3.5" /> Stop
        </Button>
      )}
      {campaign.can_complete && (
        <Button size="sm" variant="outline" disabled={acting} onClick={() => handleAction(() => completeCampaign(id), "Complete")} className="gap-1.5">
          <CheckCircle className="h-3.5 w-3.5" /> Complete
        </Button>
      )}
      {campaign.status === "completed" && (
        <Button size="sm" variant="outline" disabled={acting} onClick={() => handleAction(() => archiveCampaign(id), "Archive")} className="gap-1.5">
          <Archive className="h-3.5 w-3.5" /> Archive
        </Button>
      )}
      {isRecurring && campaign.status !== "archived" && campaign.status !== "completed" && (
        <span className="flex items-center gap-1 text-xs text-muted-foreground ml-2">
          <Repeat className="h-3 w-3" /> Auto-resets each cycle
        </span>
      )}
    </div>
  );
}
