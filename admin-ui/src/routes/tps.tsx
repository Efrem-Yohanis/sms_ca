import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/tps")({
  head: () => ({
    meta: [
      { title: "TPS | Safaricom" },
      { name: "description", content: "Configure default sending rates and per-user TPS limits." },
      { property: "og:title", content: "TPS | Safaricom Ethiopia SMS Campaign Platform" },
      {
        property: "og:description",
        content: "Configure default sending rates and per-user TPS limits.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <AdminConsole initialPage="TPS" />,
});
