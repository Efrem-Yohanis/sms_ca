import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ConfigTable, { type Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  fetchAssignedConfigurations,
  type AudioCallConfig,
} from "@/lib/api/configurations";

export default function AudioCallConfigsTab() {
  const [data, setData] = useState<AudioCallConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<AudioCallConfig | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAssignedConfigurations()
      .then((assigned) => {
        if (active) setData(assigned.audio_call);
      })
      .catch((error: unknown) => {
        if (active) {
          toast.error(
            error instanceof Error
              ? error.message
              : "Failed to load assigned audio-call APIs",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const columns: Column<AudioCallConfig>[] = [
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Base URL", accessor: (row) => row.base_url, searchable: (row) => row.base_url },
    { header: "Endpoint", accessor: (row) => row.call_endpoint },
    { header: "Calling number", accessor: (row) => row.calling_number },
    { header: "Auth", accessor: (row) => row.auth_type },
    { header: "Rate", accessor: (row) => `${row.rate_limit_per_second}/sec` },
  ];

  return (
    <>
      <ConfigTable
        title="Assigned Audio-Call APIs"
        columns={columns}
        data={data}
        loading={loading}
        readOnly
        onView={setCurrent}
      />
      <ConfigFormModal
        open={current !== null}
        onClose={() => setCurrent(null)}
        title="Audio-Call API Details"
        readOnly
      >
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Description</Label><Input value={current?.description ?? ""} disabled /></div>
        <div><Label>Base URL</Label><Input value={current?.base_url ?? ""} disabled /></div>
        <div><Label>Call endpoint</Label><Input value={current?.call_endpoint ?? ""} disabled /></div>
        <div><Label>HTTP method</Label><Input value={current?.http_method ?? ""} disabled /></div>
        <div><Label>Authentication</Label><Input value={current?.auth_type ?? ""} disabled /></div>
        <div><Label>Calling number</Label><Input value={current?.calling_number ?? ""} disabled /></div>
        <div>
          <Label>Rate limits</Label>
          <Input
            value={`${current?.rate_limit_per_second ?? ""}/sec, ${current?.rate_limit_per_minute ?? ""}/min`}
            disabled
          />
        </div>
        <div><Label>Maximum retries</Label><Input value={String(current?.max_retries ?? "")} disabled /></div>
        <div className="sm:col-span-2">
          <Label>Provider request field mapping</Label>
          <pre className="mt-1.5 overflow-auto rounded-md border bg-muted p-3 text-xs">
            {JSON.stringify(current?.request_field_mapping ?? {}, null, 2)}
          </pre>
        </div>
        <div><Label>Active</Label><Input value={current?.is_active ? "Yes" : "No"} disabled /></div>
      </ConfigFormModal>
    </>
  );
}
