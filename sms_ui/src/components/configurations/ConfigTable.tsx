import { ReactNode, useState, useMemo } from "react";
import { Search, Plus, Eye, Pencil, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export interface Column<T> {
  header: string;
  accessor: (row: T) => ReactNode;
  searchable?: (row: T) => string;
}

interface Props<T extends { id: number; is_active: boolean }> {
  title: string;
  columns: Column<T>[];
  data: T[];
  loading: boolean;
  readOnly?: boolean;
  onAdd?: () => void;
  onView: (item: T) => void;
  onEdit?: (item: T) => void;
  onDelete?: (id: number) => void;
  onToggleActive?: (item: T) => void;
  extraActions?: (item: T) => ReactNode;
}


export default function ConfigTable<T extends { id: number; is_active: boolean }>({
  title,
  columns,
  data,
  loading,
  readOnly = false,
  onAdd,
  onView,
  onEdit,
  onDelete,
  onToggleActive,
  extraActions,
}: Props<T>) {
  const [search, setSearch] = useState("");
  const [deleteId, setDeleteId] = useState<number | null>(null);

  const filtered = useMemo(() => {
    if (!search) return data;
    const q = search.toLowerCase();
    return data.filter((row) =>
      columns.some((c) => c.searchable?.(row)?.toLowerCase().includes(q))
    );
  }, [data, search, columns]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-foreground">{title}</h2>
        <div className="flex gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
          {!readOnly && onAdd && (
            <Button onClick={onAdd} size="sm">
              <Plus className="h-4 w-4 mr-1" /> Add
            </Button>
          )}
        </div>
      </div>

      <div className="border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              {columns.map((c, i) => (
                <th key={i} className="text-left px-4 py-3 font-medium text-muted-foreground">
                  {c.header}
                </th>
              ))}
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  {columns.map((_, j) => (
                    <td key={j} className="px-4 py-3">
                      <Skeleton className="h-4 w-24" />
                    </td>
                  ))}
                  <td className="px-4 py-3"><Skeleton className="h-5 w-16" /></td>
                  <td className="px-4 py-3"><Skeleton className="h-8 w-24 ml-auto" /></td>
                </tr>
              ))
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={columns.length + 2} className="px-4 py-8 text-center text-muted-foreground">
                  No items found
                </td>
              </tr>
            ) : (
              filtered.map((row) => (
                <tr key={row.id} className="border-b border-border hover:bg-muted/30 transition-colors">
                  {columns.map((c, i) => (
                    <td key={i} className="px-4 py-3 text-foreground">{c.accessor(row)}</td>
                  ))}
                  <td className="px-4 py-3">
                    <Badge
                      variant={row.is_active ? "default" : "secondary"}
                      className={readOnly || !onToggleActive ? "" : "cursor-pointer"}
                      onClick={() => !readOnly && onToggleActive?.(row)}
                    >
                      {row.is_active ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 justify-end">
                      <Button variant="ghost" size="icon" onClick={() => onView(row)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                      {!readOnly && (
                        <>
                          {extraActions?.(row)}
                          {onEdit && (
                            <Button variant="ghost" size="icon" onClick={() => onEdit(row)}>
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          {onDelete && (
                            <Button variant="ghost" size="icon" onClick={() => setDeleteId(row.id)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {!readOnly && onDelete && (
      <AlertDialog open={deleteId !== null} onOpenChange={() => setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this item?</AlertDialogTitle>
            <AlertDialogDescription>This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteId !== null) onDelete(deleteId);
                setDeleteId(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      )}
    </div>
  );
}
