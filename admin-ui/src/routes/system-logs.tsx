import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/system-logs")({
  head: () => ({ meta: [
    { title: "System Logs | Safaricom" },
    { name: "description", content: "Review platform activity and system events across all users." },
    { property: "og:title", content: "System Logs | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Review platform activity and system events across all users." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="System Logs" />,
});
