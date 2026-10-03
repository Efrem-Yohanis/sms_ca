import {
  LayoutDashboard,
  Megaphone,
  Users,
  CalendarClock,
  MessageSquareText,
  BarChart3,
  Settings,
  Send,
} from "lucide-react";
import { NavLink } from "@/components/NavLink";
import { useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Campaigns", url: "/campaigns", icon: Megaphone },
  { title: "Audiences", url: "/audiences", icon: Users },
  { title: "Schedules", url: "/schedules", icon: CalendarClock },
  { title: "Messages", url: "/messages", icon: MessageSquareText },
  { title: "Reports", url: "/reports", icon: BarChart3 },
  { title: "Configurations", url: "/configurations", icon: Settings },
];

const TOOL_ITEMS = [
  { title: "Test SMS", url: "/test-sms", icon: Send },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();

  function isActive(url: string) {
    if (url === "/") return location.pathname === "/";
    return location.pathname.startsWith(url);
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="h-14 flex items-center px-4 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center bg-sidebar-primary text-sidebar-primary-foreground shrink-0">
            <Megaphone className="h-4 w-4" />
          </div>
          {!collapsed && (
            <span className="text-sm font-bold tracking-wide text-sidebar-accent-foreground whitespace-nowrap">
              SMS Campaign Manager
            </span>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-sidebar-foreground/50 uppercase text-[10px] tracking-widest">
            Navigation
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink
                      to={item.url}
                      end={item.url === "/"}
                      className="hover:bg-sidebar-accent/50"
                      activeClassName="bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel className="text-sidebar-foreground/50 uppercase text-[10px] tracking-widest">
            Tools
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {TOOL_ITEMS.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.url)}
                    tooltip={item.title}
                  >
                    <NavLink
                      to={item.url}
                      className="hover:bg-sidebar-accent/50"
                      activeClassName="bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                    >
                      <item.icon className="h-4 w-4" />
                      <span>{item.title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-4 py-3">
        {!collapsed && (
          <p className="text-[10px] text-sidebar-foreground/40">
            © {new Date().getFullYear()} SMS Campaign Manager
          </p>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
