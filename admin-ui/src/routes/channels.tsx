import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/channels")({
  head: () => ({ meta: [
    { title: "Channels | Safaricom" },
    { name: "description", content: "Manage messaging channels available to platform users." },
    { property: "og:title", content: "Channels | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Manage messaging channels available to platform users." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="Channels" />,
});
