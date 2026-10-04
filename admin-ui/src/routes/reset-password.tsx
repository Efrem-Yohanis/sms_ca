import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, LockKeyhole, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { confirmAdminPasswordResetToken } from "@/lib/admin-api";

export const Route = createFileRoute("/reset-password")({
  head: () => ({
    meta: [
      { title: "Reset password | Safaricom" },
      {
        name: "description",
        content: "Choose a new password for your SMS Campaign Platform account.",
      },
    ],
  }),
  component: ResetPasswordPage,
});

function readResetCredentials() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const challenge = Number(fragment.get("challenge"));
  const token = fragment.get("token") || "";
  return {
    challenge: Number.isInteger(challenge) && challenge > 0 ? challenge : null,
    token,
  };
}

function ResetPasswordPage() {
  const navigate = useNavigate();
  const [credentials] = useState(readResetCredentials);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const resetPassword = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!credentials.challenge || !credentials.token) {
      setError("This reset link is invalid. Request a new one from the sign-in page.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Your password must contain at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await confirmAdminPasswordResetToken(credentials.challenge, credentials.token, newPassword);
      window.history.replaceState(window.history.state, "", window.location.pathname);
      await navigate({ to: "/login" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reset your password.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <header className="space-y-2 text-center">
          <img
            src="/safaricom-logo.png"
            alt="Safaricom"
            className="mx-auto h-11 w-[180px] object-contain"
          />
          <h1 className="font-display text-3xl font-bold">Choose a new password</h1>
          <p className="text-sm text-muted-foreground">
            Set a new password for your SMS Campaign Platform account.
          </p>
        </header>
        <Card className="border-0 shadow-elevated">
          <CardContent className="p-6">
            {credentials.challenge && credentials.token ? (
              <form onSubmit={resetPassword} className="space-y-5">
                <div className="flex items-start gap-3 rounded-lg border border-primary/15 bg-primary/5 p-4">
                  <ShieldCheck className="mt-0.5 size-5 shrink-0 text-primary" />
                  <p className="text-xs leading-5 text-muted-foreground">
                    Your secure reset link expires after 10 minutes and can be used only once.
                  </p>
                </div>
                <label className="block text-xs font-semibold">
                  New password
                  <div className="relative mt-2">
                    <LockKeyhole className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      type="password"
                      autoComplete="new-password"
                      minLength={8}
                      required
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      className="pl-9 font-normal"
                    />
                  </div>
                  <span className="mt-1 block font-normal text-muted-foreground">
                    At least 8 characters.
                  </span>
                </label>
                <label className="block text-xs font-semibold">
                  Confirm new password
                  <Input
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    required
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    className="mt-2 font-normal"
                  />
                </label>
                {error && (
                  <p role="alert" className="text-xs text-destructive">
                    {error}
                  </p>
                )}
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "Updating password…" : "Reset password"}
                </Button>
              </form>
            ) : (
              <div className="space-y-4">
                <p role="alert" className="text-sm text-destructive">
                  This reset link is incomplete or invalid. Request a new link to continue.
                </p>
                <Button asChild className="w-full">
                  <Link to="/login">Return to sign in</Link>
                </Button>
              </div>
            )}
            <Button asChild variant="ghost" className="mt-3 w-full">
              <Link to="/login">
                <ArrowLeft /> Back to sign in
              </Link>
            </Button>
          </CardContent>
        </Card>
        <p className="text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} Safaricom Ethiopia
        </p>
      </div>
    </main>
  );
}
