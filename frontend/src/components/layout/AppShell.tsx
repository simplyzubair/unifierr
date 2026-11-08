import React, { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { Logo } from '@/components/common/Logo';
import { systemApi } from '@/api';
import {
  Compass,
  Inbox,
  Download,
  Film,
  Search,
  Subtitles as SubtitlesIcon,
  Activity,
  ArrowUpCircle,
  Settings as SettingsIcon,
  Sun,
  Moon,
  LogOut,
  Menu,
  X,
  User as UserIcon,
  Wand2,
} from 'lucide-react';

interface NavItem {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { name: 'Discover', path: '/discover', icon: Compass },
  { name: 'Requests', path: '/requests', icon: Inbox },
  { name: 'Downloads', path: '/downloads', icon: Download, adminOnly: true },
  { name: 'Library', path: '/library', icon: Film },
  { name: 'Indexers', path: '/indexers', icon: Search, adminOnly: true },
  { name: 'Subtitles', path: '/subtitles', icon: SubtitlesIcon, adminOnly: true },
  { name: 'Health', path: '/health', icon: Activity, adminOnly: true },
  { name: 'Updates', path: '/updates', icon: ArrowUpCircle, adminOnly: true },
  { name: 'Settings', path: '/settings', icon: SettingsIcon, adminOnly: true },
];

export const AppShell: React.FC = () => {
  const { user, isAdmin, logout, setupStatus } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();

  const filteredNavItems = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin);

  // A small dot on "Updates" when a newer version was found by the last check (never contacts the registry).
  const [updateReady, setUpdateReady] = useState(false);
  useEffect(() => {
    if (!isAdmin) return;
    const look = () => systemApi.getUpdate().then((u) => setUpdateReady(!!u.available), () => undefined);
    void look();
    const timer = setInterval(look, 10 * 60 * 1000);
    return () => clearInterval(timer);
  }, [isAdmin]);

  return (
    <div className="flex h-screen w-full bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex flex-col w-64 shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/60 backdrop-blur-md z-30 select-none">
        <div className="flex items-center justify-between p-5 border-b border-slate-100 dark:border-slate-800/80">
          <Logo size="md" />
        </div>

        {/* Wizard reminder banner if setup incomplete and user is admin */}
        {isAdmin && setupStatus && !setupStatus.setup_complete && (
          <div className="p-3 m-3 rounded-xl bg-brand-50 border border-brand-200 dark:bg-brand-950/40 dark:border-brand-900/50 text-xs">
            <div className="flex items-center gap-2 font-semibold text-brand-900 dark:text-brand-300 mb-1">
              <Wand2 className="h-4 w-4 text-brand-600 dark:text-brand-400" />
              Setup in progress
            </div>
            <p className="text-slate-600 dark:text-slate-400 mb-2">Finish setting up your media stack.</p>
            <button
              type="button"
              onClick={() => navigate('/setup')}
              className="w-full py-1.5 px-2 bg-brand-600 hover:bg-brand-500 text-white font-medium rounded-lg text-center transition"
            >
              Open Setup Wizard
            </button>
          </div>
        )}

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {filteredNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-300 font-semibold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100/80 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200'
                  }`
                }
              >
                <Icon className="h-5 w-5 shrink-0" />
                <span>{item.name}</span>
                {item.path === '/updates' && updateReady && (
                  <span className="ml-auto h-2 w-2 rounded-full bg-sky-500" role="img" aria-label="New version available" />
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* User & Theme Section */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-800/80 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="w-8 h-8 rounded-full bg-brand-100 dark:bg-brand-950/80 text-brand-700 dark:text-brand-300 flex items-center justify-center font-bold text-xs uppercase shrink-0">
                {user?.username ? user.username.charAt(0) : <UserIcon className="h-4 w-4" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold truncate text-slate-800 dark:text-slate-200">
                  {user?.username || 'Guest'}
                </div>
                <div className="text-[10px] text-slate-500 dark:text-slate-400 uppercase tracking-wider font-medium">
                  {user?.role || 'User'}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={toggleTheme}
                aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition"
              >
                {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={logout}
                aria-label="Sign out"
                title="Sign out"
                className="p-1.5 rounded-lg text-slate-500 hover:bg-red-50 hover:text-red-600 dark:text-slate-400 dark:hover:bg-red-950/40 dark:hover:text-red-400 transition"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Mobile Top Header */}
        <header className="flex md:hidden items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md z-20">
          <Logo size="sm" />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              className="p-2 rounded-lg text-slate-500 dark:text-slate-400"
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle navigation menu"
              className="p-2 rounded-lg text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </header>

        {/* Mobile Dropdown Drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-1 shadow-lg z-30">
            {filteredNavItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium ${
                      isActive
                        ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-300 font-semibold'
                        : 'text-slate-600 dark:text-slate-400'
                    }`
                  }
                >
                  <Icon className="h-5 w-5" />
                  <span>{item.name}</span>
                  {item.path === '/updates' && updateReady && (
                    <span className="h-2 w-2 rounded-full bg-sky-500" role="img" aria-label="New version available" />
                  )}
                </NavLink>
              );
            })}
            <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <span className="text-xs text-slate-500">{user?.username} ({user?.role})</span>
              <button
                type="button"
                onClick={logout}
                className="text-xs font-semibold text-red-600 dark:text-red-400 flex items-center gap-1"
              >
                <LogOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </div>
          </div>
        )}

        {/* Page Content Body */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <div className="max-w-7xl mx-auto pb-12">
            <Outlet />
          </div>
        </main>

        {/* Mobile Bottom Navigation for Quick Access */}
        <div className="md:hidden flex items-center justify-around border-t border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md py-2 px-1 z-20">
          {filteredNavItems.slice(0, 5).map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  `flex flex-col items-center gap-1 py-1 px-2 text-[10px] font-medium transition ${
                    isActive
                      ? 'text-brand-600 dark:text-brand-400 font-bold'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                  }`
                }
              >
                <Icon className="h-5 w-5" />
                <span>{item.name}</span>
              </NavLink>
            );
          })}
        </div>
      </div>
    </div>
  );
};
