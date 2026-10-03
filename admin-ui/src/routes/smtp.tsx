import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/smtp")({
  head: () => ({ meta: [
    { title: "SMTP | Safaricom" },
    { name: "description", content: "Manage SMTP connections used by the messaging platform." },
    { property: "og:title", content: "SMTP | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Manage SMTP connections used by the messaging platform." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="SMTP" />,
});
