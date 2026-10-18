import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, Link, createRootRouteWithContext, useRouter, useLocation, HeadContent, Scripts, type ErrorComponentProps } from "@tanstack/react-router";
import { useEffect, useState, type ReactNode } from "react";
import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { AdminApiError, clearAdminTokens, getAccessToken, getCurrentAdmin } from "../lib/admin-api";

function NotFoundComponent() { return <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background"><h1 className="font-display text-4xl font-bold">Page not found</h1><Link to="/" className="text-primary underline">Return to overview</Link></div>; }
function ErrorComponent({ error, reset }: ErrorComponentProps) { const router = useRouter(); useEffect(() => { reportLovableError(error, { boundary: "tanstack_root_error_component" }); }, [error]); return <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background"><h1 className="font-display text-2xl font-bold">This page didn't load</h1><button onClick={() => { router.invalidate(); reset(); }} className="text-primary underline">Try again</button></div>; }
export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({ meta: [{ charSet: "utf-8" }, { name: "viewport", content: "width=device-width, initial-scale=1" }], links: [{ rel: "stylesheet", href: appCss }, { rel: "preconnect", href: "https://fonts.googleapis.com" }, { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" }, { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" }, { rel: "icon", href: "/safaricom-logo.png", type: "image/png" }] }),
  shellComponent: RootShell, component: RootComponent, notFoundComponent: NotFoundComponent, errorComponent: ErrorComponent,
});
function RootShell({ children }: { children: ReactNode }) { return <html lang="en"><head><HeadContent /></head><body>{children}<Scripts /></body></html>; }
function RootComponent() { const { queryClient } = Route.useRouteContext(); return <QueryClientProvider client={queryClient}><AdminOnly /></QueryClientProvider>; }

function AdminOnly() {
  const location = useLocation();
  const router = useRouter();
  const isPublicPage = location.pathname === "/login" || location.pathname === "/reset-password";
  const [state, setState] = useState<"checking" | "allowed" | "wrong-role" | "unavailable">("checking");
  const [verificationAttempt, setVerificationAttempt] = useState(0);
  const [verificationError, setVerificationError] = useState("");

  useEffect(() => {
    if (isPublicPage) {
      setState("allowed");
      return;
    }
    if (!getAccessToken()) {
      setState("checking");
      void router.navigate({ to: "/login" });
      return;
    }
    let active = true;
    setState("checking");
    setVerificationError("");
    getCurrentAdmin()
      .then((user) => {
        if (!active) return;
        if (user.role === "ADMIN") setState("allowed");
        else setState("wrong-role");
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof AdminApiError && error.status === 401) {
          clearAdminTokens();
          void router.navigate({ to: "/login" });
          return;
        }
        setVerificationError(error instanceof Error ? error.message : "Could not verify administrator access.");
        setState("unavailable");
      });
    return () => { active = false; };
  }, [isPublicPage, location.pathname, router, verificationAttempt]);

  if (isPublicPage) return <Outlet />;
  if (state === "wrong-role") return <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6 text-center"><h1 className="font-display text-2xl font-bold">Admin access required</h1><p className="text-muted-foreground">This account cannot access the administration portal.</p><a className="text-primary underline" href="http://localhost:3000/login">Open Campaign Manager</a></main>;
  if (state === "unavailable") return <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background p-6 text-center"><h1 className="font-display text-2xl font-bold">Admin service unavailable</h1><p className="max-w-lg text-sm text-muted-foreground">{verificationError}</p><button className="text-primary underline" onClick={() => setVerificationAttempt((attempt) => attempt + 1)}>Retry</button></main>;
  if (state !== "allowed") return <main className="flex min-h-screen items-center justify-center gap-3 bg-background text-sm text-muted-foreground" role="status"><span aria-hidden="true" className="size-5 animate-spin rounded-full border-2 border-current border-r-transparent" />Checking administrator access…</main>;
  return <Outlet />;
}
