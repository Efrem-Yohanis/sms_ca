import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  changeTemporaryPassword,
  confirmPasswordResetPin,
  login,
  requestPasswordResetPin,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const navigate = useNavigate();
  const { setAuth } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<"signin" | "force-change" | "forgot" | "reset-pin">("signin");
  const [pin, setPin] = useState("");
  const [resetEmail, setResetEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const data = await login(username, password);
      if ("must_change_password" in data) {
        setView("force-change");
        return;
      }
      setAuth(data.access, data.refresh, username);
      toast.success("Logged in successfully");
      navigate("/");
    } catch (err: unknown) {
      setError("Login failed: " + (err instanceof Error ? err.message : "Invalid credentials"));
    } finally {
      setLoading(false);
    }
  };

  const changeFirstPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) return setError("Password must be at least 8 characters.");
    if (newPassword !== confirmPassword) return setError("Passwords do not match.");
    setLoading(true);
    setError("");
    try {
      await changeTemporaryPassword(username, password, newPassword);
      setPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setView("signin");
      toast.success("Password changed. Sign in with your new password.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not change the temporary password.");
    } finally {
      setLoading(false);
    }
  };

  const sendResetPin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await requestPasswordResetPin(resetEmail);
      setView("reset-pin");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not request a reset PIN.");
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) return setError("Password must be at least 8 characters.");
    if (newPassword !== confirmPassword) return setError("Passwords do not match.");
    setLoading(true);
    setError("");
    try {
      await confirmPasswordResetPin(resetEmail, pin, newPassword);
      setPassword("");
      setPin("");
      setNewPassword("");
      setConfirmPassword("");
      setView("signin");
      toast.success("Password reset. Sign in with your new password.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <img
            src="/safaricom-logo.png"
            alt="Safaricom"
            className="mx-auto h-11 w-[180px] object-contain"
          />
          <h1 className="text-2xl font-semibold tracking-tight">SMS Campaign Manager</h1>
          <p className="text-sm text-muted-foreground">Safaricom Ethiopia campaign management</p>
        </div>

        <Card className="shadow-elevated border-0">
          <CardContent className="pt-6">
            {view === "signin" && <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="h-10"
                />
              </div>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <Label htmlFor="password">Password</Label>
                  <button type="button" className="text-xs text-primary hover:underline" onClick={() => { setResetEmail(username.includes("@") ? username : ""); setView("forgot"); setError(""); }}>Forgot password?</button>
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="h-10 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full h-10 shadow-soft" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </Button>
            </form>}
            {view === "force-change" && <form onSubmit={changeFirstPassword} className="space-y-4">
              <h2 className="text-xl font-semibold">Change your password</h2>
              <p className="text-sm text-muted-foreground">Your temporary password must be changed before you can continue.</p>
              <div className="space-y-2">
                <Label htmlFor="new-password">New password</Label>
                <Input id="new-password" type="password" minLength={8} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required />
                <p className="text-xs text-muted-foreground">At least 8 characters</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm-password">Confirm password</Label>
                <Input id="confirm-password" type="password" minLength={8} autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required />
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>{loading ? "Changing…" : "Change password"}</Button>
            </form>}
            {view === "forgot" && <form onSubmit={sendResetPin} className="space-y-4">
              <h2 className="text-xl font-semibold">Reset password</h2>
              <p className="text-sm text-muted-foreground">Enter the email address registered to your account. We’ll send a reset PIN.</p>
              <div className="space-y-2">
                <Label htmlFor="reset-email">Email address</Label>
                <Input id="reset-email" type="email" autoComplete="email" value={resetEmail} onChange={event => setResetEmail(event.target.value)} required />
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>{loading ? "Sending…" : "Send reset PIN"}</Button>
              <Button type="button" variant="ghost" className="w-full" onClick={() => setView("signin")}>Back to sign in</Button>
            </form>}
            {view === "reset-pin" && <form onSubmit={resetPassword} className="space-y-4">
              <h2 className="text-xl font-semibold">Enter reset PIN</h2>
              <p className="text-sm text-muted-foreground">A PIN was sent to {resetEmail}. It expires in 10 minutes.</p>
              <div className="space-y-2">
                <Label htmlFor="reset-pin">Reset PIN</Label>
                <Input id="reset-pin" inputMode="numeric" maxLength={6} value={pin} onChange={event => setPin(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="reset-new-password">New password</Label>
                <Input id="reset-new-password" type="password" minLength={8} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="reset-confirm-password">Confirm password</Label>
                <Input id="reset-confirm-password" type="password" minLength={8} autoComplete="new-password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required />
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={loading}>{loading ? "Resetting…" : "Reset password"}</Button>
              <Button type="button" variant="ghost" className="w-full" onClick={() => setView("forgot")}>Back</Button>
            </form>}
          </CardContent>
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          © {new Date().getFullYear()} Safaricom Ethiopia
        </p>
      </div>
    </div>
  );
}
