import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  fetchAssignedConfigurations,
  type SupportedChannel,
} from "@/lib/api/configurations";

export default function ChannelsTab() {
  const [data, setData] = useState<SupportedChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState<SupportedChannel | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAssignedConfigurations()
      .then((assigned) => {
        if (active) setData(assigned.channels);
      })
      .catch((error: unknown) => {
        if (active) {
          toast.error(error instanceof Error ? error.message : "Failed to load assigned channels");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const columns: Column<SupportedChannel>[] = [
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Code", accessor: (row) => row.code, searchable: (row) => row.code },
  ];

  return (
    <>
      <ConfigTable
        title="Assigned Channels"
        columns={columns}
        data={data}
        loading={loading}
        readOnly
        onView={(item) => setCurrent(item)}
      />
      <ConfigFormModal
        open={current !== null}
        onClose={() => setCurrent(null)}
        title="Channel Details"
        readOnly
      >
        <div><Label>Name</Label><Input value={current?.name ?? ""} disabled /></div>
        <div><Label>Code</Label><Input value={current?.code ?? ""} disabled /></div>
        <div><Label>Status</Label><Input value={current?.is_active ? "Active" : "Inactive"} disabled /></div>
      </ConfigFormModal>
    </>
  );
}
