import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/n-addresses")({
  head: () => ({
    meta: [
      { title: "N-Addresses | Safaricom" },
      {
        name: "description",
        content: "Configure default recipient limits and per-user N-address limits.",
      },
      { property: "og:title", content: "N-Addresses | Safaricom Ethiopia SMS Campaign Platform" },
      {
        property: "og:description",
        content: "Configure default recipient limits and per-user N-address limits.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <AdminConsole initialPage="N-Addresses" />,
});
