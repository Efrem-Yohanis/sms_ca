import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/sender-ids")({
  head: () => ({ meta: [
    { title: "Sender IDs | Safaricom" },
    { name: "description", content: "Manage sender IDs registered for messaging users." },
    { property: "og:title", content: "Sender IDs | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Manage sender IDs registered for messaging users." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="Sender IDs" />,
});
