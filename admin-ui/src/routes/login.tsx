import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, Lock, Mail, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { adminLogin, AdminApiError } from "@/lib/admin-api";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in | Safaricom" },
      {
        name: "description",
        content: "Sign in to the Safaricom Ethiopia SMS campaign management platform.",
      },
      { property: "og:title", content: "Sign in | Safaricom Ethiopia SMS Campaign Platform" },
      {
        property: "og:description",
        content: "Administrator sign-in for the Safaricom Ethiopia SMS campaign platform.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: LoginPage,
});

type View = "signin" | "forgot";

function LoginPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return setError("Enter your email address or username.");
    if (!password) return setError("Enter your password.");
    setError("");
    setSubmitting(true);
    try {
      await adminLogin(email.trim(), password);
      await navigate({ to: "/users" });
    } catch (reason) {
      setError(
        reason instanceof AdminApiError && reason.status === 0
          ? `${reason.message} Confirm the API is running at ${import.meta.env.VITE_ADMIN_API_URL || "http://localhost:8002/api/v1"}.`
          : reason instanceof Error
            ? reason.message
            : "Sign in failed.",
      );
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-[400px] rounded-lg border border-border bg-card p-8 shadow-sm">
        {view === "signin" && (
          <form onSubmit={signIn} noValidate>
            <h1 className="font-display text-3xl font-bold">Welcome back</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Sign in to the administration console.
            </p>
            <div className="mt-8 space-y-4">
              <label className="block text-xs font-semibold">
                Email or username
                <div className="relative mt-2">
                  <Mail className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="text"
                    maxLength={255}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Admin email or username"
                    className="pl-9 font-normal"
                  />
                </div>
              </label>
              <label className="block text-xs font-semibold">
                <span className="flex justify-between">
                  Password
                  <button
                    type="button"
                    onClick={() => {
                      setError("");
                      setView("forgot");
                    }}
                    className="font-medium text-primary hover:underline"
                  >
                    Forgot password?
                  </button>
                </span>
                <div className="relative mt-2">
                  <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    type="password"
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="pl-9 font-normal"
                  />
                </div>
              </label>
              {error && (
                <p role="alert" className="text-xs text-destructive">
                  {error}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={submitting}>
                <ShieldCheck /> {submitting ? "Signing in…" : "Sign in"}
              </Button>
            </div>
          </form>
        )}
        {view === "forgot" && (
          <div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="-ml-3 mb-4 text-muted-foreground"
              onClick={() => setView("signin")}
            >
              <ArrowLeft /> Back to sign in
            </Button>
            <h1 className="font-display text-3xl font-bold">Reset password</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Password reset is not available in this console. Ask another Admin to reset your
              account password.
            </p>
            <Button className="mt-8 w-full" onClick={() => setView("signin")}>
              Return to sign in
            </Button>
          </div>
        )}
      </div>
    </main>
  );
}
