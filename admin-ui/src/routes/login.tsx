import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, Lock, Mail, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  adminLogin,
  AdminApiError,
  changeInitialAdminPassword,
  requestAdminPasswordResetLink,
} from "@/lib/admin-api";

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

type View = "signin" | "force-change" | "forgot" | "email-sent";

function LoginPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<View>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return setError("Enter your email address or username.");
    if (!password) return setError("Enter your password.");
    setError("");
    setSubmitting(true);
    try {
      const result = await adminLogin(email.trim(), password);
      if ("must_change_password" in result) {
        setView("force-change");
      } else {
        await navigate({ to: "/users" });
      }
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

  const changeTemporaryPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (newPassword.length < 8) return setError("Password must be at least 8 characters.");
    if (newPassword !== confirmPassword) return setError("Passwords do not match.");
    setSubmitting(true);
    setError("");
    try {
      await changeInitialAdminPassword(email.trim(), password, newPassword);
      setPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setView("signin");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not change the temporary password.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const requestResetLink = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await requestAdminPasswordResetLink(email.trim());
      setView("email-sent");
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Could not request a password reset link.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const passwordFields = (
    <>
      <label className="block text-xs font-semibold">
        New password
        <Input
          type="password"
          minLength={8}
          autoComplete="new-password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          className="mt-2 font-normal"
        />
        <span className="mt-1 block font-normal text-muted-foreground">At least 8 characters</span>
      </label>
      <label className="block text-xs font-semibold">
        Confirm password
        <Input
          type="password"
          minLength={8}
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          className="mt-2 font-normal"
        />
      </label>
    </>
  );

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-sm space-y-6">
        <header className="space-y-2 text-center">
          <img
            src="/safaricom-logo.png"
            alt="Safaricom"
            className="mx-auto h-11 w-[180px] object-contain"
          />
          <h1 className="text-2xl font-semibold tracking-tight">SMS Campaign Manager</h1>
          <p className="text-sm text-muted-foreground">Safaricom Ethiopia administration portal</p>
        </header>
        <Card className="border-0 shadow-elevated">
          <CardContent className="p-6">
            {view === "signin" && (
              <form onSubmit={signIn} noValidate>
                <div className="space-y-4">
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
            {view === "force-change" && (
              <form onSubmit={changeTemporaryPassword}>
                <h1 className="font-display text-3xl font-bold">Change your password</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  Your temporary password must be changed before you can continue.
                </p>
                <div className="mt-8 space-y-4">
                  {passwordFields}
                  {error && (
                    <p role="alert" className="text-xs text-destructive">
                      {error}
                    </p>
                  )}
                  <Button type="submit" className="w-full" disabled={submitting}>
                    {submitting ? "Changing…" : "Change password"}
                  </Button>
                </div>
              </form>
            )}
            {view === "forgot" && (
              <form onSubmit={requestResetLink}>
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
                  We’ll email a secure password reset link if an active account matches this
                  address.
                </p>
                <label className="mt-5 block text-xs font-semibold">
                  Email address
                  <Input
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="mt-2 font-normal"
                  />
                </label>
                {error && (
                  <p role="alert" className="mt-3 text-xs text-destructive">
                    {error}
                  </p>
                )}
                <Button type="submit" className="mt-5 w-full" disabled={submitting}>
                  {submitting ? "Sending…" : "Email me a reset link"}
                </Button>
              </form>
            )}
            {view === "email-sent" && (
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
                <h1 className="font-display text-3xl font-bold">Check your email</h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  If an active account matches <strong className="text-foreground">{email}</strong>,
                  we’ve sent a secure password reset link. It expires in 10 minutes.
                </p>
                <p className="mt-4 text-xs text-muted-foreground">
                  If it isn’t in your inbox, check your spam folder. You can safely close this page.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} Safaricom Ethiopia
        </p>
      </div>
    </main>
  );
}
