import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetchCampaignMessages } from "@/lib/api/messages";
import { LANGUAGE_LABELS } from "@/types/campaign";

const PAGE_SIZE = 50;

export default function CampaignMessages() {
  const { id } = useParams<{ id: string }>();
  const campaignId = Number(id);
  const [page, setPage] = useState(1);
  const messagesQuery = useQuery({
    queryKey: ["campaign-messages", campaignId, page],
    queryFn: () => fetchCampaignMessages(campaignId, page, PAGE_SIZE),
    enabled: Number.isInteger(campaignId) && campaignId > 0,
  });

  const result = messagesQuery.data;
  const totalPages = Math.ceil((result?.count ?? 0) / PAGE_SIZE);

  return (
    <div className="space-y-5">
      <div>
        <Link to={`/campaigns/${campaignId}`} className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Campaign
        </Link>
        <h1 className="text-xl font-semibold">Message Queue</h1>
        <p className="mt-1 text-sm text-muted-foreground">Campaign #{campaignId} · {result?.count ?? 0} messages</p>
      </div>

      {messagesQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">Loading messages…</p>
      ) : messagesQuery.error ? (
        <p className="text-sm text-destructive">Unable to load campaign messages.</p>
      ) : (result?.results.length ?? 0) === 0 ? (
        <p className="border-y py-10 text-center text-sm text-muted-foreground">No messages have been built for this campaign.</p>
      ) : (
        <div className="overflow-x-auto border-y">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Recipient</TableHead>
                <TableHead>Language</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Parts</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Batch</TableHead>
                <TableHead>Built</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {result?.results.map((message) => (
                <TableRow key={message.id}>
                  <TableCell className="whitespace-nowrap font-mono text-xs">{message.recipient}</TableCell>
                  <TableCell>{message.language_code ? LANGUAGE_LABELS[message.language_code as keyof typeof LANGUAGE_LABELS] ?? message.language_code : "—"}</TableCell>
                  <TableCell className="min-w-64 max-w-[520px] whitespace-pre-wrap">{message.message_content}</TableCell>
                  <TableCell>{message.message_parts}</TableCell>
                  <TableCell><Badge variant="outline">{message.status}</Badge></TableCell>
                  <TableCell className="font-mono text-xs">{message.batch_id || "—"}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{message.built_at ? new Date(message.built_at).toLocaleString() : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Page {page} of {totalPages}</span>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" aria-label="Previous page" disabled={page <= 1 || messagesQuery.isFetching} onClick={() => setPage(page - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Next page" disabled={page >= totalPages || messagesQuery.isFetching} onClick={() => setPage(page + 1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
