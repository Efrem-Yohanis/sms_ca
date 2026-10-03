import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  fetchAssignedConfigurations,
  type SenderIdConfig,
} from "@/lib/api/configurations";

export default function SenderIdsTab() {
  const [data, setData] = useState<SenderIdConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<SenderIdConfig | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAssignedConfigurations()
      .then((assigned) => {
        if (active) setData(assigned.sender_ids);
      })
      .catch((error: unknown) => {
        if (active) {
          toast.error(error instanceof Error ? error.message : "Failed to load assigned Sender IDs");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const columns: Column<SenderIdConfig>[] = [
    { header: "Sender ID", accessor: (row) => row.sender_id, searchable: (row) => row.sender_id },
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Default", accessor: (row) => row.is_default ? "Yes" : "No" },
  ];

  return (
    <>
      <ConfigTable
        title="Assigned Sender IDs"
        columns={columns}
        data={data}
        loading={loading}
        readOnly
        onView={(item) => setCurrent(item)}
      />
      <ConfigFormModal
        open={current !== null}
        onClose={() => setCurrent(null)}
        title="Sender ID Details"
        readOnly
      >
        <div><Label>Sender ID</Label><Input value={current?.sender_id ?? ""} disabled /></div>
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Description</Label><Textarea value={current?.description ?? ""} disabled /></div>
        <div><Label>Status</Label><Input value={current?.is_active ? "Active" : "Inactive"} disabled /></div>
        <div><Label>Default</Label><Input value={current?.is_default ? "Yes" : "No"} disabled /></div>
      </ConfigFormModal>
    </>
  );
}
