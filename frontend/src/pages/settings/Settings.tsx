import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { servicesApi, authApi, systemApi, jobsApi } from '@/api';
import { useAuth } from '@/context/AuthContext';
import { ErrorCard } from '@/components/common/ErrorCard';
import { Modal } from '@/components/common/Modal';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TableSkeleton } from '@/components/common/Skeleton';
import type { ServiceOut, User, HealthStatus, Job, SystemSettings } from '@/types/api';
import {
  Settings as SettingsIcon,
  Layers,
  Users as UsersIcon,
  KeyRound,
  Download,
  Upload,
  Globe,
  Info,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Trash2,
  Plus,
  Wand2,
  Shield,
} from 'lucide-react';

type SettingsTab = 'apps' | 'network' | 'users' | 'account' | 'backup' | 'remote' | 'about';

export const Settings: React.FC = () => {
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<SettingsTab>('apps');
  const [error, setError] = useState<Error | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // ---------------- APPS TAB ----------------
  const [services, setServices] = useState<ServiceOut[]>([]);
  const [servicesLoading, setServicesLoading] = useState(false);
  const [testStatus, setTestStatus] = useState<Record<number, HealthStatus>>({});
  const [actionLoading, setActionLoading] = useState<Record<number, string>>({});

  // Login details modal (passwords Unifierr generated for Jellyfin, qBittorrent, Radarr, ...)
  const [loginModal, setLoginModal] = useState<{ name: string; username: string; password: string } | null>(
    null,
  );
  // Logs modal
  const [logsModal, setLogsModal] = useState<{ id: number; name: string; content: string } | null>(null);

  // Edit connection modal
  const [editService, setEditService] = useState<ServiceOut | null>(null);
  const [editForm, setEditForm] = useState({
    base_url: '',
    api_key: '',
    username: '',
    password: '',
    enabled: true,
  });

  // Forget service dialog
  const [forgetTarget, setForgetTarget] = useState<ServiceOut | null>(null);

  // Update container image job polling
  const [updateJobModal, setUpdateJobModal] = useState<Job | null>(null);

  // ---------------- NETWORK TAB ----------------
  const [networkSettings, setNetworkSettings] = useState<SystemSettings | null>(null);
  const [networkForm, setNetworkForm] = useState({
    vpn_enabled: false,
    vpn_provider: '',
    vpn_type: 'openvpn' as 'openvpn' | 'wireguard',
    vpn_server_countries: '',
    download_client: 'qbittorrent' as 'qbittorrent' | 'sabnzbd' | 'nzbget',
    trash_profiles: false,
  });
  const [networkSecrets, setNetworkSecrets] = useState({ vpn_username: '', vpn_password: '', wireguard_private_key: '' });
const [networkSaving, setNetworkSaving] = useState(false);
const [showUsenetClients, setShowUsenetClients] = useState(false);

  // ---------------- USERS TAB ----------------
  const [usersList, setUsersList] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [addUserModal, setAddUserModal] = useState(false);
  const [newUserForm, setNewUserForm] = useState({ username: '', password: '', role: 'user' as 'admin' | 'user' });
  const [deleteUserId, setDeleteUserId] = useState<number | null>(null);

  // ---------------- ACCOUNT TAB ----------------
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);

  // ---------------- BACKUP TAB ----------------
  const [restoring, setRestoring] = useState(false);
  const [restoreConfirmFile, setRestoreConfirmFile] = useState<File | null>(null);

  // Load services or users on tab change
  useEffect(() => {
    setError(null);
    setSuccessMsg(null);
    if (activeTab === 'apps') loadServices();
    if (activeTab === 'users' && isAdmin) loadUsers();
    if (activeTab === 'network' && isAdmin) loadNetworkSettings();
  }, [activeTab]);

  const loadNetworkSettings = async () => {
    try {
      const settings = await systemApi.getSettings();
      setNetworkSettings(settings);
      setShowUsenetClients(settings.download_client === 'sabnzbd' || settings.download_client === 'nzbget');
      setNetworkForm({
        vpn_enabled: settings.vpn_enabled ?? false,
        vpn_provider: settings.vpn_provider ?? '',
        vpn_type: settings.vpn_type ?? 'openvpn',
        vpn_server_countries: settings.vpn_server_countries ?? '',
        download_client: settings.download_client ?? 'qbittorrent',
        trash_profiles: settings.trash_profiles ?? false,
      });
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleSaveNetwork = async (event: React.FormEvent) => {
    event.preventDefault();
    setNetworkSaving(true);
    setError(null);
    try {
      const settings = await systemApi.updateSettings({
        ...networkForm,
        ...(networkSecrets.vpn_username ? { vpn_username: networkSecrets.vpn_username } : {}),
        ...(networkSecrets.vpn_password ? { vpn_password: networkSecrets.vpn_password } : {}),
        ...(networkSecrets.wireguard_private_key
          ? { wireguard_private_key: networkSecrets.wireguard_private_key }
          : {}),
      });
      setNetworkSettings(settings);
      setNetworkSecrets({ vpn_username: '', vpn_password: '', wireguard_private_key: '' });
      setSuccessMsg('Network settings saved. VPN credentials are stored encrypted.');
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setNetworkSaving(false);
    }
  };

  const loadServices = async () => {
    setServicesLoading(true);
    try {
      const data = await servicesApi.getServices();
      setServices(data);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setServicesLoading(false);
    }
  };

  const loadUsers = async () => {
    setUsersLoading(true);
    try {
      const list = await authApi.getUsers();
      setUsersList(list);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setUsersLoading(false);
    }
  };

  // Service actions
  const handleTestService = async (id: number) => {
    setActionLoading((prev) => ({ ...prev, [id]: 'testing' }));
    try {
      const res = await servicesApi.testService(id);
      if (res.status) {
        const status = res.status;
        setTestStatus((prev) => ({ ...prev, [id]: status }));
      }
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setActionLoading((prev) => ({ ...prev, [id]: '' }));
    }
  };

  const handleRestartService = async (id: number) => {
    setActionLoading((prev) => ({ ...prev, [id]: 'restarting' }));
    try {
      await servicesApi.restartService(id);
      setSuccessMsg('Service restarted successfully.');
      await loadServices();
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setActionLoading((prev) => ({ ...prev, [id]: '' }));
    }
  };

  const handleUpdateServiceImage = async (id: number) => {
    setActionLoading((prev) => ({ ...prev, [id]: 'updating' }));
    try {
      const { job_id } = await servicesApi.updateImage(id);
      // Poll update job
      const poll = setInterval(async () => {
        try {
          const j = await jobsApi.getJob(job_id);
          setUpdateJobModal(j);
          if (j.status === 'done' || j.status === 'failed') {
            clearInterval(poll);
            setActionLoading((prev) => ({ ...prev, [id]: '' }));
            loadServices();
          }
        } catch {
          clearInterval(poll);
          setActionLoading((prev) => ({ ...prev, [id]: '' }));
        }
      }, 1500);
    } catch (err: unknown) {
      setError(err as Error);
      setActionLoading((prev) => ({ ...prev, [id]: '' }));
    }
  };

  const handleShowLogin = async (s: ServiceOut) => {
    try {
      const res = await servicesApi.getCredentials(s.id);
      setLoginModal({ name: s.name, username: res.username ?? '', password: res.password ?? '' });
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleShowLogs = async (s: ServiceOut) => {
    try {
      const res = await servicesApi.getLogs(s.id, 200);
      setLogsModal({ id: s.id, name: s.name, content: res.logs || 'No logs recorded.' });
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleSaveConnection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editService) return;
    try {
      await servicesApi.updateService(editService.id, {
        base_url: editForm.base_url || undefined,
        api_key: editForm.api_key || undefined,
        username: editForm.username || undefined,
        password: editForm.password || undefined,
        enabled: editForm.enabled,
      });
      setEditService(null);
      setSuccessMsg(`Connection settings updated for ${editService.name}.`);
      await loadServices();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleForgetService = async () => {
    if (!forgetTarget) return;
    try {
      await servicesApi.deleteService(forgetTarget.id);
      setForgetTarget(null);
      setSuccessMsg(`Forgot ${forgetTarget.name}. No files or containers were deleted.`);
      await loadServices();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  // User actions
  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await authApi.createUser(newUserForm);
      setAddUserModal(false);
      setNewUserForm({ username: '', password: '', role: 'user' });
      setSuccessMsg('New user created successfully.');
      await loadUsers();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteUserId) return;
    try {
      await authApi.deleteUser(deleteUserId);
      setDeleteUserId(null);
      setSuccessMsg('User removed.');
      await loadUsers();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  // Password change
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmNewPassword) {
      setError(new Error('New passwords do not match.'));
      return;
    }
    if (newPassword.length < 12) {
      setError(new Error('New password must be at least 12 characters long.'));
      return;
    }

    setPasswordSubmitting(true);
    try {
      await authApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
      setSuccessMsg('Your password has been changed successfully.');
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setPasswordSubmitting(false);
    }
  };

  // Backup & Restore
  const handleDownloadBackup = async () => {
    try {
      const blob = await systemApi.getBackup();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `unifierr-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleFileRestoreSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setRestoreConfirmFile(file);
    }
  };

  const handleExecuteRestore = async () => {
    if (!restoreConfirmFile) return;
    setRestoring(true);
    setError(null);
    try {
      await systemApi.restoreBackup(restoreConfirmFile);
      setRestoreConfirmFile(null);
      setSuccessMsg('System restored successfully! Please log in again.');
      setTimeout(() => {
        window.location.href = '/login';
      }, 2000);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <SettingsIcon className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            System Settings
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Manage connected services, user accounts, security, and backups.
          </p>
        </div>

        {isAdmin && (
          <button
            type="button"
            onClick={() => navigate('/setup')}
            className="flex items-center gap-1.5 rounded-xl border border-brand-200 dark:border-brand-900/60 bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 px-3.5 py-2 text-xs font-semibold hover:bg-brand-100 transition self-start sm:self-auto"
          >
            <Wand2 className="h-3.5 w-3.5" /> Re-open Setup Wizard
          </button>
        )}
      </div>

      {/* Tabs navigation */}
      <div className="flex flex-wrap gap-1 rounded-2xl bg-slate-200/70 p-1 dark:bg-slate-800/80">
        <button
          type="button"
          onClick={() => setActiveTab('apps')}
          className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
            activeTab === 'apps'
              ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
              : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
          }`}
        >
          <Layers className="h-3.5 w-3.5" /> Apps & Services
        </button>

        {isAdmin && (
          <button
            type="button"
            onClick={() => setActiveTab('network')}
            className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
              activeTab === 'network'
                ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            <Shield className="h-3.5 w-3.5" /> Network & VPN
          </button>
        )}

        {isAdmin && (
          <button
            type="button"
            onClick={() => setActiveTab('users')}
            className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
              activeTab === 'users'
                ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            <UsersIcon className="h-3.5 w-3.5" /> Users
          </button>
        )}

        <button
          type="button"
          onClick={() => setActiveTab('account')}
          className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
            activeTab === 'account'
              ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
              : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
          }`}
        >
          <KeyRound className="h-3.5 w-3.5" /> Account & Password
        </button>

        {isAdmin && (
          <button
            type="button"
            onClick={() => setActiveTab('backup')}
            className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
              activeTab === 'backup'
                ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            <Download className="h-3.5 w-3.5" /> Backup & Restore
          </button>
        )}

        <button
          type="button"
          onClick={() => setActiveTab('remote')}
          className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
            activeTab === 'remote'
              ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
              : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
          }`}
        >
          <Globe className="h-3.5 w-3.5" /> Remote Access Guide
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('about')}
          className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
            activeTab === 'about'
              ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
              : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
          }`}
        >
          <Info className="h-3.5 w-3.5" /> About
        </button>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {successMsg && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/30 p-3.5 text-xs font-semibold text-emerald-800 dark:text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            {successMsg}
          </div>
          <button type="button" onClick={() => setSuccessMsg(null)} className="text-emerald-600 hover:opacity-80">
            Dismiss
          </button>
        </div>
      )}

      {/* ---------------- APPS TAB CONTENT ---------------- */}
      {activeTab === 'apps' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase text-slate-500">Connected Services</h2>
          </div>

          {servicesLoading ? (
            <TableSkeleton rows={4} />
          ) : services.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {services.map((svc) => {
                const isActing = actionLoading[svc.id];
                const t = testStatus[svc.id];

                return (
                  <div
                    key={svc.id}
                    className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-xs"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-bold text-base text-slate-900 dark:text-white capitalize">
                            {svc.name}
                          </h3>
                          {svc.managed && (
                            <span className="rounded bg-brand-100 text-brand-800 dark:bg-brand-950 dark:text-brand-300 text-[10px] font-semibold px-1.5 py-0.2">
                              Docker Managed
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs">
                          {svc.base_url}
                        </div>
                      </div>

                      {svc.status?.ok ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-semibold">
                          <CheckCircle2 className="h-3 w-3 text-emerald-500" /> Connected
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 px-2 py-0.5 text-[10px] font-semibold">
                          <XCircle className="h-3 w-3 text-red-500" /> Disconnected
                        </span>
                      )}
                    </div>

                    {t && (
                      <div className="text-xs p-2 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-100 dark:border-slate-800">
                        {t.ok ? (
                          <span className="text-emerald-600 font-semibold flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" /> Connection test successful ({t.message})
                          </span>
                        ) : (
                          <span className="text-red-600 font-semibold flex items-center gap-1">
                            <XCircle className="h-3 w-3" /> Connection test failed: {t.message}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Action buttons */}
                    <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
                      <button
                        type="button"
                        onClick={() => handleTestService(svc.id)}
                        disabled={!!isActing}
                        className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition"
                      >
                        {isActing === 'testing' ? 'Testing...' : 'Test'}
                      </button>

                      {svc.managed && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleRestartService(svc.id)}
                            disabled={!!isActing}
                            className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition"
                          >
                            {isActing === 'restarting' ? 'Restarting...' : 'Restart'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleUpdateServiceImage(svc.id)}
                            disabled={!!isActing}
                            className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition"
                          >
                            {isActing === 'updating' ? 'Updating...' : 'Update Image'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleShowLogs(svc)}
                            className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition"
                          >
                            View Logs
                          </button>
                        </>
                      )}

                      {svc.has_login && (
                        <button
                          type="button"
                          onClick={() => handleShowLogin(svc)}
                          className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition"
                        >
                          Show login
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => {
                          setEditService(svc);
                          setEditForm({
                            base_url: svc.base_url,
                            api_key: '',
                            username: '',
                            password: '',
                            enabled: svc.enabled,
                          });
                        }}
                        className="rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 px-2.5 py-1 font-medium transition text-brand-600 dark:text-brand-400"
                      >
                        Edit
                      </button>

                      <button
                        type="button"
                        onClick={() => setForgetTarget(svc)}
                        className="rounded-lg hover:bg-red-50 dark:hover:bg-red-950/40 text-slate-400 hover:text-red-600 px-2.5 py-1 font-medium transition ml-auto"
                        title="Forget from Unifierr"
                      >
                        Forget
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-8 text-center text-xs text-slate-500 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
              No services registered. Run the Setup Wizard to connect your apps.
            </div>
          )}
        </div>
      )}

      {activeTab === 'network' && isAdmin && (
        <form onSubmit={handleSaveNetwork} className="max-w-2xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-6 shadow-xs">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">VPN routing</h2>
            <p className="mt-1 text-xs text-slate-500">New qBittorrent and Prowlarr containers can share Gluetun's VPN network. Existing containers and their configuration are never changed automatically.</p>
          </div>
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={networkForm.vpn_enabled}
              onChange={(event) => setNetworkForm({ ...networkForm, vpn_enabled: event.target.checked })}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            <span className="text-sm font-semibold text-slate-900 dark:text-white">Route downloads through VPN</span>
          </label>

          {networkForm.vpn_enabled && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                VPN provider (Gluetun name)
                <input
                  type="text"
                  required
                  value={networkForm.vpn_provider}
                  onChange={(event) => setNetworkForm({ ...networkForm, vpn_provider: event.target.value })}
                  placeholder="e.g. protonvpn"
                  className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-white"
                />
              </label>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                VPN type
                <select
                  value={networkForm.vpn_type}
                  onChange={(event) => setNetworkForm({ ...networkForm, vpn_type: event.target.value === 'wireguard' ? 'wireguard' : 'openvpn' })}
                  className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-white"
                >
                  <option value="openvpn">OpenVPN</option>
                  <option value="wireguard">WireGuard</option>
                </select>
              </label>
              {networkForm.vpn_type === 'openvpn' ? (
                <>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                    VPN username {networkSettings?.vpn_has_openvpn_credentials && <span className="font-normal">(saved; leave blank to keep)</span>}
                    <input type="text" autoComplete="off" value={networkSecrets.vpn_username} onChange={(event) => setNetworkSecrets({ ...networkSecrets, vpn_username: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm" />
                  </label>
                  <label className="block text-xs font-medium text-slate-600 dark:text-slate-400">
                    VPN password {networkSettings?.vpn_has_openvpn_credentials && <span className="font-normal">(saved; leave blank to keep)</span>}
                    <input type="password" autoComplete="new-password" value={networkSecrets.vpn_password} onChange={(event) => setNetworkSecrets({ ...networkSecrets, vpn_password: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm" />
                  </label>
                </>
              ) : (
                <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 sm:col-span-2">
                  WireGuard private key {networkSettings?.vpn_has_wireguard_key && <span className="font-normal">(saved; leave blank to keep)</span>}
                  <input type="password" autoComplete="new-password" value={networkSecrets.wireguard_private_key} onChange={(event) => setNetworkSecrets({ ...networkSecrets, wireguard_private_key: event.target.value })} className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm" />
                </label>
              )}
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 sm:col-span-2">
                Server countries (optional)
                <input type="text" value={networkForm.vpn_server_countries} onChange={(event) => setNetworkForm({ ...networkForm, vpn_server_countries: event.target.value })} placeholder="e.g. Switzerland" className="mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm" />
              </label>
              <p className="text-xs text-slate-500 sm:col-span-2">Credentials are encrypted at rest. Use the exact provider name supported by Gluetun. Changing these settings does not rewrite an existing VPN container.</p>
            </div>
          )}

          <div className="border-t border-slate-100 dark:border-slate-800 pt-4 space-y-4">
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">Download client</h3>
<p className="mt-0.5 text-xs text-slate-500">Choose how downloads work. qBittorrent is for torrents; SABnzbd and NZBGet are optional Usenet clients and need a Usenet provider.</p>
              <select
                value={networkForm.download_client}
                onChange={(event) => setNetworkForm({ ...networkForm, download_client: event.target.value as 'qbittorrent' | 'sabnzbd' | 'nzbget' })}
                className="mt-2 w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-white"
              >
<option value="qbittorrent">qBittorrent (torrents)</option>
{showUsenetClients && <>
  <option value="sabnzbd">SABnzbd (Usenet)</option>
  <option value="nzbget">NZBGet (Usenet)</option>
  </>}
</select>
<button type="button" onClick={() => setShowUsenetClients((shown) => !shown)} className="mt-1 text-xs text-brand-600 hover:underline dark:text-brand-400">
  {showUsenetClients ? 'Hide optional Usenet clients' : 'Show optional Usenet clients'}
</button>
            </div>

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={networkForm.trash_profiles}
                onChange={(event) => setNetworkForm({ ...networkForm, trash_profiles: event.target.checked })}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              />
              <span className="text-sm">
                <span className="font-semibold text-slate-900 dark:text-white">Use TRaSH-Guides quality profiles</span>
                <span className="block text-xs text-slate-500 mt-0.5">Applies the recommended TRaSH quality profile and custom formats to Radarr and Sonarr during wiring. Your own profiles are never changed.</span>
              </span>
            </label>
          </div>

          <div className="flex justify-end border-t border-slate-100 dark:border-slate-800 pt-4">
            <button type="submit" disabled={networkSaving} className="rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold px-4 py-2 text-xs disabled:opacity-50">
              {networkSaving ? 'Saving…' : 'Save Network Settings'}
            </button>
          </div>
        </form>
      )}

      {/* ---------------- USERS TAB CONTENT ---------------- */}
      {activeTab === 'users' && isAdmin && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold uppercase text-slate-500">System Users</h2>
            <button
              type="button"
              onClick={() => setAddUserModal(true)}
              className="flex items-center gap-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white px-3.5 py-2 text-xs font-semibold shadow-xs transition"
            >
              <Plus className="h-4 w-4" /> Add User
            </button>
          </div>

          {usersLoading ? (
            <TableSkeleton rows={3} />
          ) : (
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden divide-y divide-slate-100 dark:divide-slate-800/80 shadow-xs">
              {usersList.map((u) => (
                <div key={u.id} className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-9 w-9 rounded-full bg-brand-100 text-brand-700 dark:bg-brand-950 dark:text-brand-300 flex items-center justify-center font-bold text-xs uppercase">
                      {u.username.charAt(0)}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                        {u.username}
                        {u.id === user?.id && (
                          <span className="text-[10px] text-brand-600 dark:text-brand-400 font-semibold">(You)</span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 capitalize">{u.role}</div>
                    </div>
                  </div>

                  {u.id !== user?.id && (
                    <button
                      type="button"
                      onClick={() => setDeleteUserId(u.id)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
                      title="Remove user"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ---------------- ACCOUNT TAB CONTENT ---------------- */}
      {activeTab === 'account' && (
        <div className="max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-5 shadow-xs">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">Change Password</h2>
            <p className="text-xs text-slate-500 mt-0.5">Update your password to keep your account secure.</p>
          </div>

          <form onSubmit={handleChangePassword} className="space-y-4 text-xs">
            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Current Password
              </label>
              <input
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3.5 py-2"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                New Password (at least 12 characters)
              </label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3.5 py-2"
              />
            </div>

            <div>
              <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Confirm New Password
              </label>
              <input
                type="password"
                required
                value={confirmNewPassword}
                onChange={(e) => setConfirmNewPassword(e.target.value)}
                className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3.5 py-2"
              />
            </div>

            <button
              type="submit"
              disabled={passwordSubmitting}
              className="w-full rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-4 shadow-sm transition disabled:opacity-50"
            >
              {passwordSubmitting ? 'Updating...' : 'Update Password'}
            </button>
          </form>
        </div>
      )}

      {/* ---------------- BACKUP & RESTORE TAB ---------------- */}
      {activeTab === 'backup' && isAdmin && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Download Backup */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xs">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400 w-fit">
              <Download className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900 dark:text-white">Download System Backup</h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Creates an encrypted ZIP bundle containing your Unifierr database, secret encryption key, and saved settings. Keep this file safe.
              </p>
            </div>
            <button
              type="button"
              onClick={handleDownloadBackup}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold px-4 py-2.5 text-xs shadow-xs transition hover:opacity-90"
            >
              <Download className="h-4 w-4" /> Export Backup Archive (.zip)
            </button>
          </div>

          {/* Restore Backup */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4 shadow-xs">
            <div className="p-3 rounded-2xl bg-amber-50 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400 w-fit">
              <Upload className="h-6 w-6" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900 dark:text-white">Restore from Backup</h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Restore your previous Unifierr database and configuration from a backup archive.
              </p>
            </div>

            <label className="inline-flex items-center gap-2 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold px-4 py-2.5 text-xs shadow-xs transition hover:bg-slate-100 cursor-pointer">
              <Upload className="h-4 w-4" /> Select Backup File to Restore
              <input
                type="file"
                accept=".zip"
                onChange={handleFileRestoreSelect}
                className="hidden"
              />
            </label>
          </div>
        </div>
      )}

      {/* ---------------- REMOTE ACCESS GUIDE TAB ---------------- */}
      {activeTab === 'remote' && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-xs max-w-3xl">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Globe className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Remote Access & Security Guide
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                How to access Unifierr, Jellyfin, and your media apps securely from anywhere in the world.
              </p>
            </div>
          </div>

          <div className="rounded-xl border border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/30 p-4 text-xs text-red-900 dark:text-red-200 space-y-1.5">
            <div className="flex items-center gap-2 font-bold text-sm">
              <AlertTriangle className="h-4 w-4 text-red-600 shrink-0" />
              Never port-forward without HTTPS and strong authentication
            </div>
            <p className="leading-relaxed">
              Exposing raw HTTP ports directly to the open internet allows unauthorized attackers to intercept traffic and passwords. Always use a secure VPN or encrypted reverse proxy.
            </p>
          </div>

          <div className="space-y-4 text-xs text-slate-600 dark:text-slate-300">
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 space-y-2">
              <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 text-[10px] text-white">1</span>
                Option A (Recommended): Tailscale Mesh VPN
              </h3>
              <p className="leading-relaxed">
                Tailscale creates a private, encrypted WireGuard mesh network connecting your devices. No port forwarding, no router changes, and 100% free for personal use. Install Tailscale on your host machine and on your phone or laptop to access Unifierr seamlessly.
              </p>
            </div>

            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 space-y-2">
              <h3 className="font-bold text-sm text-slate-900 dark:text-white flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 text-[10px] text-white">2</span>
                Option B: Cloudflare Tunnel or Caddy Reverse Proxy
              </h3>
              <p className="leading-relaxed">
                If you have your own domain name and want friends or family to stream without installing VPN software, use a reverse proxy like Cloudflare Tunnel or Caddy with automated HTTPS certificates.
              </p>
              <div className="rounded-lg bg-white dark:bg-slate-900 p-2.5 font-mono text-[11px] border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200">
                # Enable secure cookies when running behind HTTPS:
                <br />
                UNIFIERR_SECURE_COOKIES=true
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------- ABOUT TAB ---------------- */}
      {activeTab === 'about' && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-xs max-w-2xl">
          <div>
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">About Unifierr</h2>
            <p className="text-sm text-slate-500 mt-1">
              Open-source, beginner-friendly media stack manager.
            </p>
          </div>

          <div className="text-xs text-slate-600 dark:text-slate-300 space-y-3 leading-relaxed">
            <p>
              Unifierr was built to solve the biggest headache in self-hosting: the initial maze of Docker networking, volume mounts, permission errors, API keys, and app-to-app integrations.
            </p>
            <p>
              By uniting Radarr, Sonarr, Prowlarr, qBittorrent, Bazarr, and Jellyfin/Plex under a unified TRaSH storage architecture, Unifierr gives you a smooth, streaming-app-grade experience from day one.
            </p>
          </div>

          <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500">
            <span>Version: 1.0.0</span>
            <span>MIT License • Self-Hosted Freedom</span>
          </div>
        </div>
      )}

      {/* Login Details Modal */}
      <Modal isOpen={!!loginModal} onClose={() => setLoginModal(null)} title={`Login for ${loginModal?.name}`} maxWidth="md">
        <div className="space-y-3 text-sm">
          <p className="text-slate-600 dark:text-slate-400">
            Unifierr created this login for you. Use it to open {loginModal?.name} directly. Keep it private.
          </p>
          <div>
            <div className="text-xs font-semibold text-slate-500">Username</div>
            <code className="block rounded-lg bg-slate-100 dark:bg-slate-900 px-3 py-2 select-all">{loginModal?.username}</code>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500">Password</div>
            <code className="block rounded-lg bg-slate-100 dark:bg-slate-900 px-3 py-2 select-all break-all">
              {loginModal?.password || 'Not stored'}
            </code>
          </div>
        </div>
      </Modal>

      {/* Service Logs Modal */}
      <Modal
        isOpen={!!logsModal}
        onClose={() => setLogsModal(null)}
        title={`Logs: ${logsModal?.name}`}
        maxWidth="2xl"
      >
        <pre className="p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] max-h-96 overflow-y-auto leading-relaxed">
          {logsModal?.content}
        </pre>
      </Modal>

      {/* Edit Service Modal */}
      <Modal
        isOpen={!!editService}
        onClose={() => setEditService(null)}
        title={`Edit Connection: ${editService?.name}`}
        maxWidth="md"
      >
        <form onSubmit={handleSaveConnection} className="space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Base URL
            </label>
            <input
              type="text"
              required
              value={editForm.base_url}
              onChange={(e) => setEditForm({ ...editForm, base_url: e.target.value })}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2 font-mono"
            />
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">
              API Key / Token (leave blank to keep current)
            </label>
            <input
              type="password"
              value={editForm.api_key}
              onChange={(e) => setEditForm({ ...editForm, api_key: e.target.value })}
              placeholder="••••••••••••••••"
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setEditService(null)}
              className="rounded-xl px-4 py-2 text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold px-4 py-2"
            >
              Save Settings
            </button>
          </div>
        </form>
      </Modal>

      {/* Forget Service Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!forgetTarget}
        onClose={() => setForgetTarget(null)}
        onConfirm={handleForgetService}
        title={`Forget ${forgetTarget?.name}?`}
        description={`This will remove ${forgetTarget?.name} from Unifierr's interface. Important: No containers, settings, or media files will be deleted.`}
        confirmLabel="Forget Service"
        isDestructive
      />

      {/* Add User Modal */}
      <Modal
        isOpen={addUserModal}
        onClose={() => setAddUserModal(false)}
        title="Add New User"
      >
        <form onSubmit={handleAddUser} className="space-y-4 text-xs">
          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Username</label>
            <input
              type="text"
              required
              value={newUserForm.username}
              onChange={(e) => setNewUserForm({ ...newUserForm, username: e.target.value })}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2"
            />
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Password</label>
            <input
              type="password"
              required
              value={newUserForm.password}
              onChange={(e) => setNewUserForm({ ...newUserForm, password: e.target.value })}
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2"
            />
          </div>

          <div>
            <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Role</label>
            <select
              value={newUserForm.role}
              onChange={(e) =>
                setNewUserForm({ ...newUserForm, role: e.target.value as 'admin' | 'user' })
              }
              className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-3 py-2"
            >
              <option value="user">Standard User (Discover, Requests, Library)</option>
              <option value="admin">Administrator (Full Access)</option>
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setAddUserModal(false)}
              className="rounded-xl px-4 py-2 text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold px-4 py-2"
            >
              Create User
            </button>
          </div>
        </form>
      </Modal>

      {/* Container Update Job Modal */}
      <Modal
        isOpen={!!updateJobModal}
        onClose={() => setUpdateJobModal(null)}
        title="Updating Container Image"
      >
        <div className="space-y-3 text-xs">
          <p className="text-slate-500">
            Pulling updated image and recreating the container with existing storage mounts.
          </p>
          <div className="p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] max-h-48 overflow-y-auto">
            {updateJobModal?.log?.join('\n') || 'Starting update...'}
          </div>
          {updateJobModal?.status === 'done' && (
            <div className="text-emerald-600 font-semibold flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4" /> Container updated successfully!
            </div>
          )}
          {updateJobModal?.status === 'failed' && (
            <div className="text-red-600 font-semibold flex items-center gap-1.5">
              <XCircle className="h-4 w-4" /> Container update failed. Check logs above.
            </div>
          )}
        </div>
      </Modal>

      {/* Delete User Confirm */}
      <ConfirmDialog
        isOpen={!!deleteUserId}
        onClose={() => setDeleteUserId(null)}
        onConfirm={handleDeleteUser}
        title="Delete User"
        description="Are you sure you want to delete this user? They will lose access immediately."
        confirmLabel="Delete"
        isDestructive
      />

      {/* Restore Backup Confirm Dialog */}
      <ConfirmDialog
        isOpen={!!restoreConfirmFile}
        onClose={() => setRestoreConfirmFile(null)}
        onConfirm={handleExecuteRestore}
        title="Restore Backup Warning"
        description={`Restoring "${restoreConfirmFile?.name}" will overwrite the current database and settings with the contents of the archive. Are you sure you want to continue?`}
        confirmLabel={restoring ? 'Restoring...' : 'Confirm Restore'}
        isDestructive
      />
    </div>
  );
};
