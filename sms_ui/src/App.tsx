import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/context/AuthContext";
import { CampaignProvider } from "@/context/CampaignContext";
import AppShell from "@/components/AppShell";
import CampaignList from "@/pages/CampaignList";
import Dashboard from "@/pages/DashboardHome";
import CampaignDetail from "@/pages/CampaignDetail";
import CampaignMessages from "@/pages/CampaignMessages";
import CampaignCreate from "@/pages/CampaignCreate";
import AudienceList from "@/pages/AudienceList";
import AudienceDetail from "@/pages/AudienceDetail";
import AudienceCreate from "@/pages/AudienceCreate";
import ScheduleList from "@/pages/ScheduleList";
import ScheduleCreate from "@/pages/ScheduleCreate";
import ScheduleEdit from "@/pages/ScheduleEdit";
import ScheduleDetail from "@/pages/ScheduleDetail";
import MessageContentList from "@/pages/MessageContentList";
import MessageContentDetail from "@/pages/MessageContentDetail";
import MessageContentCreate from "@/pages/MessageContentCreate";
import MessageContentEdit from "@/pages/MessageContentEdit";
import Configurations from "@/pages/Configurations";
import Reports from "@/pages/ReportSubscriptions";
import TestSms from "@/pages/TestSms";
import NotFound from "./pages/NotFound.tsx";
import Login from "./pages/Login";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <CampaignProvider>
                  <AppShell>
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/dashboard" element={<Dashboard />} />
                      <Route path="/campaigns" element={<CampaignList />} />
                      <Route path="/campaigns/new" element={<CampaignCreate />} />
                      <Route path="/campaigns/:id" element={<CampaignDetail />} />
                      <Route path="/campaigns/:id/messages" element={<CampaignMessages />} />
                      <Route path="/campaigns/:id/edit" element={<CampaignCreate />} />
                      <Route path="/audiences" element={<AudienceList />} />
                      <Route path="/audiences/create" element={<AudienceCreate />} />
                      <Route path="/audiences/:id" element={<AudienceDetail />} />
                      <Route path="/schedules" element={<ScheduleList />} />
                      <Route path="/schedules/create" element={<ScheduleCreate />} />
                      <Route path="/schedules/:id" element={<ScheduleDetail />} />
                      <Route path="/schedules/:id/edit" element={<ScheduleEdit />} />
                      <Route path="/messages" element={<MessageContentList />} />
                      <Route path="/messages/create" element={<MessageContentCreate />} />
                      <Route path="/messages/:id" element={<MessageContentDetail />} />
                      <Route path="/messages/:id/edit" element={<MessageContentEdit />} />
                      <Route path="/reports" element={<Reports />} />
                      <Route path="/test-sms" element={<TestSms />} />
                      <Route path="/configurations" element={<Configurations />} />
                      <Route path="*" element={<NotFound />} />
                    </Routes>
                  </AppShell>
                </CampaignProvider>
              }
            />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
