import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { confirmPasswordResetToken } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";

function getResetCredentials() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const challenge = Number(fragment.get("challenge"));
  const token = fragment.get("token") || "";
  return {
    challenge: Number.isInteger(challenge) && challenge > 0 ? challenge : null,
    token,
  };
}

export default function ResetPassword() {
  const navigate = useNavigate();
  const [credentials] = useState(getResetCredentials);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!credentials.challenge || !credentials.token) {
      setError(
        "This reset link is invalid. Request a new one from the sign-in page.",
      );
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

    setLoading(true);
    setError("");
    try {
      await confirmPasswordResetToken(
        credentials.challenge,
        credentials.token,
        newPassword,
      );
      window.history.replaceState(
        window.history.state,
        "",
        window.location.pathname,
      );
      toast.success("Password reset. Sign in with your new password.");
      navigate("/login");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not reset your password.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <header className="space-y-2 text-center">
          <img
            src="/safaricom-logo.png"
            alt="Safaricom"
            className="mx-auto h-11 w-[180px] object-contain"
          />
          <h1 className="text-2xl font-semibold tracking-tight">
            Choose a new password
          </h1>
          <p className="text-sm text-muted-foreground">
            Secure your SMS Campaign Manager account with a new password.
          </p>
        </header>
        <Card className="border-0 shadow-elevated">
          <CardContent className="space-y-5 p-6">
            {credentials.challenge && credentials.token ? (
              <form onSubmit={submit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="new-password">New password</Label>
                  <Input
                    id="new-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    required
                  />
                  <p className="text-xs text-muted-foreground">
                    Use at least 8 characters.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">Confirm new password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    required
                  />
                </div>
                {error && (
                  <p role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                )}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Updating password…" : "Reset password"}
                </Button>
              </form>
            ) : (
              <div className="space-y-4">
                <p role="alert" className="text-sm text-destructive">
                  This reset link is incomplete or invalid. Request a new link
                  to continue.
                </p>
                <Button asChild className="w-full">
                  <Link to="/login">Return to sign in</Link>
                </Button>
              </div>
            )}
            {credentials.challenge && credentials.token && (
              <p className="text-center text-xs text-muted-foreground">
                Reset links expire after 10 minutes and can be used only once.
              </p>
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
