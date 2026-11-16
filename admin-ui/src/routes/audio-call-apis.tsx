import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/audio-call-apis")({
  head: () => ({ meta: [
    { title: "Audio Call APIs | Safaricom" },
    { name: "description", content: "Manage outbound audio-call API connections." },
  ] }),
  component: () => <AdminConsole initialPage="Audio Call APIs" />,
});
