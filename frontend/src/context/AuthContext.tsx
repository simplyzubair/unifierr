import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { User, SetupStatus } from '@/types/api';
import { authApi, setupApi } from '@/api';

interface AuthContextType {
  user: User | null;
  setupStatus: SetupStatus | null;
  isLoading: boolean;
  isAdmin: boolean;
  login: (data: { username: string; password: string }) => Promise<User>;
  bootstrap: (data: { username: string; password: string }) => Promise<User>;
  logout: () => Promise<void>;
  refreshStatus: () => Promise<SetupStatus | null>;
  refreshUser: () => Promise<User | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshStatus = useCallback(async (): Promise<SetupStatus | null> => {
    try {
      const status = await setupApi.getStatus();
      setSetupStatus(status);
      return status;
    } catch {
      return null;
    }
  }, []);

  const refreshUser = useCallback(async (): Promise<User | null> => {
    try {
      const u = await authApi.me();
      setUser(u);
      return u;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    const init = async () => {
      try {
        const [status, currentUser] = await Promise.allSettled([
          setupApi.getStatus(),
          authApi.me(),
        ]);

        if (!mounted) return;

        if (status.status === 'fulfilled') {
          setSetupStatus(status.value);
        }
        if (currentUser.status === 'fulfilled') {
          setUser(currentUser.value);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    init();
    return () => {
      mounted = false;
    };
  }, []);

  const login = async (data: { username: string; password: string }): Promise<User> => {
    const loggedInUser = await authApi.login(data);
    setUser(loggedInUser);
    await refreshStatus();
    return loggedInUser;
  };

  const bootstrap = async (data: { username: string; password: string }): Promise<User> => {
    const adminUser = await authApi.bootstrap(data);
    setUser(adminUser);
    await refreshStatus();
    return adminUser;
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      await refreshStatus();
      window.location.href = '/login';
    }
  };

  const isAdmin = user?.role === 'admin';

  return (
    <AuthContext.Provider
      value={{
        user,
        setupStatus,
        isLoading,
        isAdmin,
        login,
        bootstrap,
        logout,
        refreshStatus,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
