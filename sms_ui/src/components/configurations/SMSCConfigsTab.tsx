import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  fetchAssignedConfigurations,
  type SMSCConfig,
} from "@/lib/api/configurations";

export default function SMSCConfigsTab() {
  const [data, setData] = useState<SMSCConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<SMSCConfig | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAssignedConfigurations()
      .then((assigned) => {
        if (active) setData(assigned.smsc);
      })
      .catch((error: unknown) => {
        if (active) {
          toast.error(error instanceof Error ? error.message : "Failed to load assigned SMSC configurations");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const columns: Column<SMSCConfig>[] = [
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Base URL", accessor: (row) => row.base_url, searchable: (row) => row.base_url },
    { header: "Auth", accessor: (row) => row.auth_type },
    { header: "Rate", accessor: (row) => `${row.rate_limit_per_second}/sec` },
    { header: "Default", accessor: (row) => row.is_default ? "Yes" : "No" },
  ];

  return (
    <>
      <ConfigTable
        title="Assigned SMSC Configurations"
        columns={columns}
        data={data}
        loading={loading}
        readOnly
        onView={(item) => setCurrent(item)}
      />
      <ConfigFormModal
        open={current !== null}
        onClose={() => setCurrent(null)}
        title="SMSC Configuration Details"
        readOnly
      >
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Description</Label><Input value={current?.description ?? ""} disabled /></div>
        <div><Label>Base URL</Label><Input value={current?.base_url ?? ""} disabled /></div>
        <div><Label>Send Endpoint</Label><Input value={current?.send_endpoint ?? ""} disabled /></div>
        <div><Label>HTTP Method</Label><Input value={current?.http_method ?? ""} disabled /></div>
        <div><Label>Authentication</Label><Input value={current?.auth_type ?? ""} disabled /></div>
        <div>
          <Label>Rate limits</Label>
          <Input value={`${current?.rate_limit_per_second ?? ""}/sec, ${current?.rate_limit_per_minute ?? ""}/min`} disabled />
        </div>
        <div><Label>Active</Label><Input value={current?.is_active ? "Yes" : "No"} disabled /></div>
      </ConfigFormModal>
    </>
  );
}
