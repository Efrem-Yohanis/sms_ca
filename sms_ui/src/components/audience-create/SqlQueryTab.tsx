import { useState } from "react";
import { Database } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useConnections } from "./useDbSchema";
import type { AudienceSqlSelection } from "@/types/campaign";
import { LANGUAGE_LABELS, SUPPORTED_LANGUAGES, type Language } from "@/types/campaign";

interface Props {
  initialConfig?: AudienceSqlSelection | null;
  onConfigChange: (config: AudienceSqlSelection | null) => void;
  defaultLanguage?: Language;
  onDefaultLanguageChange?: (language: Language) => void;
}

export default function SqlQueryTab({ initialConfig, onConfigChange, defaultLanguage, onDefaultLanguageChange }: Props) {
  const [connection, setConnection] = useState(initialConfig?.source_database_id ? String(initialConfig.source_database_id) : "");
  const [query, setQuery] = useState(initialConfig?.source_sql ?? "");
  const { connections, loading } = useConnections();

  function updateConfig(nextConnection: string, nextQuery: string) {
    onConfigChange(nextConnection && nextQuery.trim() ? { source_database_id: Number(nextConnection), source_sql: nextQuery.trim() } : null);
  }

  return (
    <div className="space-y-4">
      <div>
        <Label className="text-base font-medium">Build audience from SQL</Label>
        <p className="mt-1 text-xs text-muted-foreground">Choose a database and provide one read-only SELECT query. Return `msisdn` and optionally `language`; missing languages use the campaign default.</p>
      </div>
      <div className="space-y-1.5">
        <Label>Database connection *</Label>
        <Select value={connection} onValueChange={(value) => { setConnection(value); updateConfig(value, query); }}>
          <SelectTrigger><SelectValue placeholder={loading ? "Loading connections..." : "Select database"} /></SelectTrigger>
          <SelectContent>{connections.map((item) => <SelectItem key={item.id} value={item.id}>{item.name} ({item.type})</SelectItem>)}</SelectContent>
        </Select>
        {connections.length === 0 && !loading && <p className="text-xs text-muted-foreground">Add a database connection in Configurations first.</p>}
      </div>
      <div className="space-y-1.5">
        <Label>SQL query *</Label>
        <Textarea value={query} onChange={(event) => { setQuery(event.target.value); updateConfig(connection, event.target.value); }} rows={8} className="font-mono text-sm" placeholder={'SELECT phone AS msisdn, language FROM subscribers WHERE active = 1'} />
      </div>
      {defaultLanguage && onDefaultLanguageChange && (
        <div className="space-y-1.5">
          <Label>Default language when SQL omits `language`</Label>
          <Select value={defaultLanguage} onValueChange={(value) => onDefaultLanguageChange(value as Language)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{SUPPORTED_LANGUAGES.map((language) => <SelectItem key={language} value={language}>{LANGUAGE_LABELS[language]}</SelectItem>)}</SelectContent>
          </Select>
        </div>
      )}
      <div className="flex items-center gap-2 text-xs text-muted-foreground"><Database className="h-4 w-4" />Query is saved with this campaign and executed during the audience build.</div>
    </div>
  );
}
