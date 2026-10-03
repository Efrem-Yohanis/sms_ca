import { createFileRoute } from "@tanstack/react-router";
import { AdminConsole } from "@/components/admin/console";

export const Route = createFileRoute("/kafka-monitor")({
  head: () => ({ meta: [
    { title: "Kafka Monitor | Safaricom" },
    { name: "description", content: "Watch event streams, consumer groups, and throughput for the messaging platform." },
    { property: "og:title", content: "Kafka Monitor | Safaricom Ethiopia SMS Campaign Platform" },
    { property: "og:description", content: "Watch event streams, consumer groups, and throughput for the messaging platform." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: () => <AdminConsole initialPage="Kafka Monitor" />,
});
