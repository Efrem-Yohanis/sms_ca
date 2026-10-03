import type { ComponentType } from "react";

interface SectionProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export function Section({ icon: Icon, title, children, action }: SectionProps) {
  return (
    <div className="bg-card border shadow-soft">
      <div className="flex items-center justify-between px-5 py-3.5 border-b">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center bg-muted">
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          <h2 className="text-sm font-semibold">{title}</h2>
        </div>
        {action}
      </div>
      <div className="px-5 py-4">{children}</div>
    </div>
  );
}

export function Field({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <span className="text-muted-foreground text-xs uppercase tracking-wider">{label}</span>
      <p className={`mt-1 font-medium text-sm ${className || ""}`}>{value}</p>
    </div>
  );
}

export function StatCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-muted/50 px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-lg font-bold ${color || ""}`}>{value}</p>
    </div>
  );
}
