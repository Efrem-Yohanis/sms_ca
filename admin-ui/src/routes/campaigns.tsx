import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/campaigns")({
  head: () => ({ meta: [
    { title: "Campaigns | Safaricom" },
    { name: "description", content: "Monitor every SMS campaign across all users and accounts." },
    { property: "og:title", content: "Campaigns | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Monitor every SMS campaign across all users and accounts." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="Campaigns" />,
});
