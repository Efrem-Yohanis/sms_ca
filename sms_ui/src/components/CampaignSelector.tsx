import { useState, useEffect } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchCampaigns } from "@/lib/api";
import type { ApiCampaign } from "@/lib/api";

interface CampaignSelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  className?: string;
}

export default function CampaignSelector({ value, onValueChange, className }: CampaignSelectorProps) {
  const [campaigns, setCampaigns] = useState<ApiCampaign[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        // Fetch a large page to get all campaigns
        const res = await fetchCampaigns({ page: 1, pageSize: 100 });
        setCampaigns(res.results);
      } catch (e) {
        console.error("Failed to load campaigns", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <Skeleton className="h-10 w-full" />;

  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className={className}>
        <SelectValue placeholder="Select a campaign" />
      </SelectTrigger>
      <SelectContent>
        {campaigns.map((c) => (
          <SelectItem key={c.id} value={String(c.id)}>
            #{c.id} — {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
