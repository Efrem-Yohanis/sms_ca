import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/smsc-accounts")({
  head: () => ({ meta: [
    { title: "SMSC Accounts | Safaricom" },
    { name: "description", content: "Manage SMSC gateway connections for every user account." },
    { property: "og:title", content: "SMSC Accounts | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Manage SMSC gateway connections for every user account." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="SMSC Accounts" />,
});
