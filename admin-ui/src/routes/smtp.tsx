import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/smtp")({
  head: () => ({ meta: [
    { title: "Email Config | Safaricom" },
    { name: "description", content: "Manage Admin account email services and password reset email." },
    { property: "og:title", content: "Email Config | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Manage Admin account email services and password reset email." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="Email Config" />,
});
