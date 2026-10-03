import { useState } from "react";
import { Languages, Radio, Database, Send, Mail, UserCog, Gauge } from "lucide-react";
import { cn } from "@/lib/utils";
import LanguagesTab from "@/components/configurations/LanguagesTab";
import ChannelsTab from "@/components/configurations/ChannelsTab";
import DataSourcesTab from "@/components/configurations/DataSourcesTab";
import SenderIdsTab from "@/components/configurations/SenderIdsTab";
import EmailServicesTab from "@/components/configurations/EmailServicesTab";
import CustomerProfileConfigsTab from "@/components/configurations/CustomerProfileConfigsTab";
import SMSCConfigsTab from "@/components/configurations/SMSCConfigsTab";
import SenderLimitsTab from "@/components/configurations/SenderLimitsTab";

const TABS = [
  { key: "languages", label: "Languages", icon: Languages },
  { key: "channels", label: "Channels", icon: Radio },
  { key: "sources", label: "Data Sources", icon: Database },
  { key: "sender", label: "Sender IDs", icon: Send },
  { key: "email", label: "Email Services", icon: Mail },
  { key: "profile", label: "Customer Profile", icon: UserCog },
  { key: "smsc", label: "SMSC Config", icon: Radio },
  { key: "limits", label: "Sender Limits", icon: Gauge },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function Configurations() {
  const [tab, setTab] = useState<TabKey>("languages");

  return (
    <div className="p-4 md:p-6 space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Configurations</h1>

      {/* Tab bar */}
      <div className="flex flex-wrap gap-2 border-b border-border pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t.key
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
            )}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {tab === "languages" && <LanguagesTab />}
      {tab === "channels" && <ChannelsTab />}
      {tab === "sources" && <DataSourcesTab />}
      {tab === "sender" && <SenderIdsTab />}
      {tab === "email" && <EmailServicesTab />}
      {tab === "profile" && <CustomerProfileConfigsTab />}
      {tab === "smsc" && <SMSCConfigsTab />}
      {tab === "limits" && <SenderLimitsTab />}
    </div>
  );
}
