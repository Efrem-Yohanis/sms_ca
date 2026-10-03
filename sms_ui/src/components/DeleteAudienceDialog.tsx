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
import { useState } from "react";
import { deleteAudienceById } from "@/lib/api/audiences";
import { toast } from "sonner";

interface DeleteAudienceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: number | null;
  audienceName?: string;
  onSuccess: () => void;
}

export default function DeleteAudienceDialog({
  open,
  onOpenChange,
  campaignId,
  audienceName,
  onSuccess,
}: DeleteAudienceDialogProps) {
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!campaignId) return;
    setDeleting(true);
    try {
      await deleteAudienceById(campaignId);
      toast.success("Audience deleted successfully");
      onOpenChange(false);
      onSuccess();
    } catch (err: any) {
      toast.error(err?.message || "Failed to delete audience");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Audience</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to delete{" "}
            {audienceName ? <strong>{audienceName}</strong> : "this audience"}? This action cannot
            be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleting ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
