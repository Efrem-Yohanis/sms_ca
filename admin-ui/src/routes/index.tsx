import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Users | Safaricom" },
      {
        name: "description",
        content: "Manage people, access, and account limits across the SMS campaign platform.",
      },
      { property: "og:title", content: "Users | Safaricom Ethiopia SMS Campaign Platform" },
      {
        property: "og:description",
        content: "Manage users and access across the SMS campaign platform.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => <AdminConsole initialPage="Users" />,
});
