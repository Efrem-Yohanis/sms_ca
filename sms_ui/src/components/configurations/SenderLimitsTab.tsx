import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ConfigTable, { Column } from "./ConfigTable";
import ConfigFormModal from "./ConfigFormModal";
import {
  fetchAssignedConfigurations,
  type AssignedConfigurations,
  type GlobalTPSConfig,
  type NAddress,
  type NAddressesConfig,
} from "@/lib/api/configurations";

const emptyAssigned: AssignedConfigurations = {
  smsc: [],
  sender_ids: [],
  channels: [],
  tps_configs: [],
  n_address_configs: [],
  n_addresses: [],
  tps_limit: null,
};

export default function SenderLimitsTab() {
  const [assigned, setAssigned] = useState<AssignedConfigurations>(emptyAssigned);
  const [loading, setLoading] = useState(true);
  const [selectedTps, setSelectedTps] = useState<GlobalTPSConfig | null>(null);
  const [selectedRequestLimit, setSelectedRequestLimit] = useState<NAddressesConfig | null>(null);
  const [selectedAddress, setSelectedAddress] = useState<NAddress | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAssignedConfigurations()
      .then((result) => {
        if (active) setAssigned(result);
      })
      .catch((error: unknown) => {
        if (active) {
          toast.error(error instanceof Error ? error.message : "Failed to load assigned TPS and N-address configurations");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const tpsColumns: Column<GlobalTPSConfig>[] = [
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Messages per second", accessor: (row) => String(row.global_tps) },
    { header: "Default", accessor: (row) => row.is_default ? "Yes" : "No" },
  ];
  const requestLimitColumns: Column<NAddressesConfig>[] = [
    { header: "Name", accessor: (row) => row.name, searchable: (row) => row.name },
    { header: "Addresses per request", accessor: (row) => String(row.max_addresses_per_request) },
    { header: "Default", accessor: (row) => row.is_default ? "Yes" : "No" },
  ];
  const addressColumns: Column<NAddress>[] = [
    { header: "Address", accessor: (row) => row.value, searchable: (row) => row.value },
    { header: "Type", accessor: (row) => row.address_type },
    {
      header: "SMSC",
      accessor: (row) => assigned.smsc.find((smsc) => smsc.id === row.smsc)?.name ?? "—",
    },
    {
      header: "Channel",
      accessor: (row) => assigned.channels.find((channel) => channel.id === row.channel)?.name ?? "—",
    },
    {
      header: "Sender ID",
      accessor: (row) => assigned.sender_ids.find((sender) => sender.id === row.sender_id)?.sender_id ?? "—",
    },
  ];

  return (
    <div className="space-y-8">
      <div className="rounded-md border border-border bg-card p-4 text-sm">
        <span className="font-medium">Your TPS limit:</span>{" "}
        {assigned.tps_limit ?? "No per-user limit configured"}
      </div>
      <ConfigTable
        title="Assigned TPS Configurations"
        columns={tpsColumns}
        data={assigned.tps_configs}
        loading={loading}
        readOnly
        onView={(item) => setSelectedTps(item)}
      />
      <ConfigTable
        title="Assigned N-address Request Limits"
        columns={requestLimitColumns}
        data={assigned.n_address_configs}
        loading={loading}
        readOnly
        onView={(item) => setSelectedRequestLimit(item)}
      />
      <ConfigTable
        title="Assigned N-Addresses"
        columns={addressColumns}
        data={assigned.n_addresses}
        loading={loading}
        readOnly
        onView={(item) => setSelectedAddress(item)}
      />

      <ConfigFormModal
        open={selectedTps !== null}
        onClose={() => setSelectedTps(null)}
        title="TPS Configuration Details"
        readOnly
      >
        <div><Label>Name</Label><Input value={selectedTps?.name ?? ""} disabled /></div>
        <div><Label>Description</Label><Input value={selectedTps?.description ?? ""} disabled /></div>
        <div><Label>Messages per second</Label><Input value={String(selectedTps?.global_tps ?? "")} disabled /></div>
      </ConfigFormModal>
      <ConfigFormModal
        open={selectedRequestLimit !== null}
        onClose={() => setSelectedRequestLimit(null)}
        title="N-address Request Limit Details"
        readOnly
      >
        <div><Label>Name</Label><Input value={selectedRequestLimit?.name ?? ""} disabled /></div>
        <div><Label>Description</Label><Input value={selectedRequestLimit?.description ?? ""} disabled /></div>
        <div><Label>Addresses per request</Label><Input value={String(selectedRequestLimit?.max_addresses_per_request ?? "")} disabled /></div>
      </ConfigFormModal>
      <ConfigFormModal
        open={selectedAddress !== null}
        onClose={() => setSelectedAddress(null)}
        title="N-address Details"
        readOnly
      >
        <div><Label>Address</Label><Input value={selectedAddress?.value ?? ""} disabled /></div>
        <div><Label>Type</Label><Input value={selectedAddress?.address_type ?? ""} disabled /></div>
        <div><Label>TPS cap</Label><Input value={selectedAddress?.tps_cap === null || selectedAddress?.tps_cap === undefined ? "None" : String(selectedAddress.tps_cap)} disabled /></div>
        <div><Label>Notes</Label><Input value={selectedAddress?.notes ?? ""} disabled /></div>
      </ConfigFormModal>
    </div>
  );
}
