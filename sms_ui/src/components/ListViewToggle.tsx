import { useEffect, useState } from "react";
import { Grid2X2, List } from "lucide-react";
import { Button } from "@/components/ui/button";

export type ListView = "list" | "grid";

export function useListView(storageKey: string): [ListView, (view: ListView) => void] {
  const [view, setView] = useState<ListView>(() =>
    localStorage.getItem(storageKey) === "grid" ? "grid" : "list"
  );

  useEffect(() => {
    localStorage.setItem(storageKey, view);
  }, [storageKey, view]);

  return [view, setView];
}

export default function ListViewToggle({
  view,
  onChange,
}: {
  view: ListView;
  onChange: (view: ListView) => void;
}) {
  return (
    <div className="inline-flex rounded-md border bg-background p-0.5" role="group" aria-label="View mode">
      <Button
        type="button"
        variant={view === "list" ? "secondary" : "ghost"}
        size="icon"
        className="h-8 w-8"
        aria-label="List view"
        aria-pressed={view === "list"}
        title="List view"
        onClick={() => onChange("list")}
      >
        <List className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant={view === "grid" ? "secondary" : "ghost"}
        size="icon"
        className="h-8 w-8"
        aria-label="Grid view"
        aria-pressed={view === "grid"}
        title="Grid view"
        onClick={() => onChange("grid")}
      >
        <Grid2X2 className="h-4 w-4" />
      </Button>
    </div>
  );
}