import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/context/ThemeContext';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { AppShell } from '@/components/layout/AppShell';
import { Logo } from '@/components/common/Logo';

// Pages
import { Login } from '@/pages/auth/Login';
import { Bootstrap } from '@/pages/auth/Bootstrap';
import { SetupWizard } from '@/pages/setup/SetupWizard';
import { Discover } from '@/pages/discover/Discover';
import { Requests } from '@/pages/requests/Requests';
import { Downloads } from '@/pages/downloads/Downloads';
import { Library } from '@/pages/library/Library';
import { Indexers } from '@/pages/indexers/Indexers';
import { Subtitles } from '@/pages/subtitles/Subtitles';
import { Health } from '@/pages/health/Health';
import { Settings } from '@/pages/settings/Settings';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const ProtectedRoute: React.FC<{ children: React.ReactNode; adminOnly?: boolean }> = ({
  children,
  adminOnly = false,
}) => {
  const { user, isAdmin, isLoading, setupStatus } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 dark:bg-slate-950 gap-4">
        <Logo size="lg" />
        <div className="flex items-center gap-2 text-xs text-slate-400 font-medium animate-pulse">
          Connecting to Unifierr...
        </div>
      </div>
    );
  }

  if (setupStatus && !setupStatus.has_admin) {
    return <Navigate to="/bootstrap" replace />;
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (adminOnly && !isAdmin) {
    return <Navigate to="/discover" replace />;
  }

  return <>{children}</>;
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              {/* Public Auth Routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/bootstrap" element={<Bootstrap />} />

              {/* Setup Wizard */}
              <Route
                path="/setup"
                element={
                  <ProtectedRoute adminOnly>
                    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 p-4 sm:p-8">
                      <div className="max-w-4xl mx-auto mb-6 flex items-center justify-between">
                        <Logo size="md" />
                      </div>
                      <SetupWizard />
                    </div>
                  </ProtectedRoute>
                }
              />

              {/* Main Application with AppShell */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppShell />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<Navigate to="/discover" replace />} />
                <Route path="/discover" element={<Discover />} />
                <Route path="/requests" element={<Requests />} />
                <Route path="/library" element={<Library />} />

                {/* Admin Only Routes */}
                <Route
                  path="/downloads"
                  element={
                    <ProtectedRoute adminOnly>
                      <Downloads />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/indexers"
                  element={
                    <ProtectedRoute adminOnly>
                      <Indexers />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/subtitles"
                  element={
                    <ProtectedRoute adminOnly>
                      <Subtitles />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/health"
                  element={
                    <ProtectedRoute adminOnly>
                      <Health />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/settings"
                  element={
                    <ProtectedRoute adminOnly>
                      <Settings />
                    </ProtectedRoute>
                  }
                />
              </Route>

              {/* Catch all fallback */}
              <Route path="*" element={<Navigate to="/discover" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};
