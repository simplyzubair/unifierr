import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { setupApi, jobsApi } from '@/api';
import { useAuth } from '@/context/AuthContext';
import { ErrorCard } from '@/components/common/ErrorCard';
import { ProgressBar } from '@/components/common/ProgressBar';
import { Tooltip, JargonHelp } from '@/components/common/Tooltip';
import type {
  EnvironmentReport,
  DetectedApp,
  FolderReport,
  ServiceKind,
  TrashPreset,
  Job,
} from '@/types/api';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HardDrive,
  Cpu,
  Layers,
  ChevronDown,
  ChevronUp,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  Sparkles,
  Server,
  FolderCheck,
  Radio,
  FileCode,
  Sliders,
} from 'lucide-react';

const STEPS = [
  'Welcome & Environment',
  'Storage Layout',
  'Apps & Services',
  'Installing Apps',
  'Connecting Stack',
  'Quality Profiles',
  'Ready to Stream',
];

const DEFAULT_TRASH_PRESETS: TrashPreset[] = [
  {
    id: 'hd-1080p',
    name: '1080p HD (Bluray + WEB)',
    description: 'Best 1080p Blu-ray and WEB-DL releases, blocking low-quality encodes, CAMs, and full discs.',
    radarr_slug: 'hd-bluray-web',
    radarr_profile: 'HD Bluray + WEB',
    sonarr_slug: 'web-1080p',
    sonarr_profile: 'WEB-1080p',
  },
  {
    id: 'uhd-2160p',
    name: '4K UHD (Bluray + WEB)',
    description: 'High-bitrate 2160p 4K Blu-ray and WEB-DL releases with TRaSH release group tiers.',
    radarr_slug: 'uhd-bluray-web',
    radarr_profile: 'UHD Bluray + WEB',
    sonarr_slug: 'web-2160p',
    sonarr_profile: 'WEB-2160p',
  },
  {
    id: 'remux-1080p',
    name: '1080p Remux + WEB (Lossless HD)',
    description: 'Untouched lossless 1080p Blu-ray Remuxes and top-tier 1080p WEB-DL releases.',
    radarr_slug: 'remux-web-1080p',
    radarr_profile: 'Remux + WEB 1080p',
    sonarr_slug: 'remux-web-1080p',
    sonarr_profile: 'Remux + WEB 1080p',
  },
  {
    id: 'remux-2160p',
    name: '4K Remux + WEB (Lossless 4K)',
    description: 'Untouched lossless 2160p UHD Blu-ray Remuxes and top-tier 4K WEB-DL releases.',
    radarr_slug: 'remux-web-2160p',
    radarr_profile: 'Remux + WEB 2160p',
    sonarr_slug: 'remux-web-2160p',
    sonarr_profile: 'Remux + WEB 2160p',
  },
  {
    id: 'web-1080p',
    name: '1080p WEB Only (Compact)',
    description: 'Streaming 1080p WEB-DL releases only for smaller file sizes and fast downloads.',
    radarr_slug: 'web-1080p',
    radarr_profile: 'WEB 1080p',
    sonarr_slug: 'web-1080p',
    sonarr_profile: 'WEB-1080p',
  },
  {
    id: 'web-2160p',
    name: '4K WEB Only',
    description: 'Streaming 2160p 4K WEB-DL releases only.',
    radarr_slug: 'web-2160p',
    radarr_profile: 'WEB 2160p',
    sonarr_slug: 'web-2160p',
    sonarr_profile: 'WEB-2160p',
  },
];

const ALL_APPS: Array<{ kind: ServiceKind; name: string; desc: string; defaultInstall: boolean }> = [
  { kind: 'radarr', name: 'Radarr', desc: 'Finds, downloads, and organizes movies automatically.', defaultInstall: true },
  { kind: 'sonarr', name: 'Sonarr', desc: 'Tracks your favorite TV shows and fetches new episodes.', defaultInstall: true },
  { kind: 'prowlarr', name: 'Prowlarr', desc: 'Syncs torrent trackers and indexers to all your apps.', defaultInstall: true },
  { kind: 'qbittorrent', name: 'qBittorrent', desc: 'Fast, secure download client handling your files.', defaultInstall: true },
  { kind: 'bazarr', name: 'Bazarr', desc: 'Finds missing subtitles in any language automatically.', defaultInstall: true },
  { kind: 'jellyfin', name: 'Jellyfin', desc: 'Free, private streaming server for your personal media.', defaultInstall: true },
  { kind: 'plex', name: 'Plex', desc: 'Popular streaming server with wide device support.', defaultInstall: false },
];

interface CustomAdoptEntry {
  base_url: string;
  api_key: string;
  username: string;
  password: string;
}

export const SetupWizard: React.FC = () => {
  const { refreshStatus } = useAuth();
  const navigate = useNavigate();

  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Step 1: Environment
  const [envReport, setEnvReport] = useState<EnvironmentReport | null>(null);

  // Step 2: Storage
  const [rootFolder, setRootFolder] = useState('/srv/unifierr');
  const [puid, setPuid] = useState(1000);
  const [pgid, setPgid] = useState(1000);
  const [timezone, setTimezone] = useState('Etc/UTC');
  const [showAdvancedStorage, setShowAdvancedStorage] = useState(false);
  const [folderReport, setFolderReport] = useState<FolderReport | null>(null);

  // Step 3: Detection & Selection
  const [detectedApps, setDetectedApps] = useState<DetectedApp[]>([]);
  const [adoptedKinds, setAdoptedKinds] = useState<Set<ServiceKind>>(new Set());
  const [selectedToInstall, setSelectedToInstall] = useState<Set<ServiceKind>>(
    new Set(['radarr', 'sonarr', 'prowlarr', 'qbittorrent', 'bazarr', 'jellyfin'])
  );
  const [mediaServerChoice, setMediaServerChoice] = useState<'jellyfin' | 'plex'>('jellyfin');
  const [customAdoptForm, setCustomAdoptForm] = useState<Record<string, CustomAdoptEntry>>({});
  const [openAdoptAdvanced, setOpenAdoptAdvanced] = useState<Record<string, boolean>>({});

  // Step 4: Install Job
  const [installJob, setInstallJob] = useState<Job | null>(null);
  const [showInstallLogs, setShowInstallLogs] = useState(false);

  // Step 5: Wire Job
  const [wireJob, setWireJob] = useState<Job | null>(null);
  const [showWireLogs, setShowWireLogs] = useState(false);

  // Step 6: TRaSH Quality Profiles
  const [trashPresets, setTrashPresets] = useState<TrashPreset[]>(DEFAULT_TRASH_PRESETS);
  const [selectedTrashProfile, setSelectedTrashProfile] = useState<string>('hd-1080p');
  const [trashJob, setTrashJob] = useState<Job | null>(null);
  const [showTrashLogs, setShowTrashLogs] = useState(false);

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Load environment on mount
  useEffect(() => {
    loadEnvironment();
  }, []);

  const loadEnvironment = async () => {
    setLoading(true);
    setError(null);
    try {
      const env = await setupApi.getEnvironment();
      setEnvReport(env);
      if (env.suggested_root) setRootFolder(env.suggested_root);
      if (env.puid) setPuid(env.puid);
      if (env.pgid) setPgid(env.pgid);
      if (env.timezone) setTimezone(env.timezone);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const loadDetection = async () => {
    setLoading(true);
    setError(null);
    try {
      const apps = await setupApi.detectApps();
      setDetectedApps(apps);

      // If Plex was detected running, switch media server choice to plex
      const hasPlex = apps.some((a) => a.kind === 'plex' && a.reachable_url);
      const hasJellyfin = apps.some((a) => a.kind === 'jellyfin' && a.reachable_url);
      if (hasPlex && !hasJellyfin) {
        setMediaServerChoice('plex');
      }
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Prepare storage
  const handlePrepareStorage = async () => {
    setLoading(true);
    setError(null);
    try {
      const report = await setupApi.prepareFolders({
        root: rootFolder,
        puid: Number(puid),
        pgid: Number(pgid),
        timezone,
      });
      setFolderReport(report);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  // Adopt app
  const handleAdopt = async (kind: ServiceKind) => {
    setLoading(true);
    setError(null);
    try {
      const custom = customAdoptForm[kind] || { base_url: '', api_key: '', username: '', password: '' };
      await setupApi.adopt({
        kind,
        base_url: custom.base_url || undefined,
        api_key: custom.api_key || undefined,
        username: custom.username || undefined,
        password: custom.password || undefined,
      });
      setAdoptedKinds((prev) => new Set([...prev, kind]));
      // Remove from to-install if adopted
      setSelectedToInstall((prev) => {
        const next = new Set(prev);
        next.delete(kind);
        return next;
      });
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  // Step 4: Install apps
  const startInstall = async () => {
    setLoading(true);
    setError(null);

    // Filter to selected apps matching media server choice
    const kindsToInstall = Array.from(selectedToInstall).filter((k) => {
      if (k === 'plex' && mediaServerChoice !== 'plex') return false;
      if (k === 'jellyfin' && mediaServerChoice !== 'jellyfin') return false;
      return true;
    });

    if (kindsToInstall.length === 0) {
      // Nothing to install, skip directly to wire
      setCurrentStep(4);
      startWire();
      return;
    }

    try {
      const { job_id } = await setupApi.install(kindsToInstall);
      pollJob(job_id, (job) => {
        setInstallJob(job);
        if (job.status === 'done') {
          setLoading(false);
        } else if (job.status === 'failed') {
          setLoading(false);
          setError(new Error('App installation encountered a problem. Check step details below.'));
        }
      });
    } catch (err: unknown) {
      setError(err as Error);
      setLoading(false);
    }
  };

  // Step 5: Wire everything
  const startWire = async () => {
    setLoading(true);
    setError(null);
    try {
      const { job_id } = await setupApi.wire();
      pollJob(job_id, (job) => {
        setWireJob(job);
        if (job.status === 'done') {
          setLoading(false);
        } else if (job.status === 'failed') {
          setLoading(false);
        }
      });
    } catch (err: unknown) {
      setError(err as Error);
      setLoading(false);
    }
  };

  // Step 6: Load & Apply TRaSH Quality Profiles
  const loadTrashStatus = async () => {
    try {
      const status = await setupApi.getTrashStatus();
      if (status.available_profiles && status.available_profiles.length > 0) {
        setTrashPresets(status.available_profiles);
      }
      if (status.chosen_profile) {
        setSelectedTrashProfile(status.chosen_profile);
      }
    } catch {
      // keep default presets if endpoint not yet reachable
    }
  };

  const startTrashSync = async () => {
    setLoading(true);
    setError(null);
    try {
      const { job_id } = await setupApi.applyTrash(selectedTrashProfile);
      pollJob(job_id, (job) => {
        setTrashJob(job);
        if (job.status === 'done' || job.status === 'failed') {
          setLoading(false);
        }
      });
    } catch (err: unknown) {
      setError(err as Error);
      setLoading(false);
    }
  };

  // Step 7: Complete
  const handleComplete = async () => {
    setLoading(true);
    setError(null);
    try {
      await setupApi.complete();
      await refreshStatus();
      navigate('/discover');
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const pollJob = (id: string, onUpdate: (job: Job) => void) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

    const check = async () => {
      try {
        const job = await jobsApi.getJob(id);
        onUpdate(job);
        if (job.status === 'done' || job.status === 'failed') {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
        }
      } catch {
        // ignore network hiccups
      }
    };

    check();
    pollIntervalRef.current = setInterval(check, 1500);
  };

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // Format bytes helper
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Stepper Header */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">
            Setup Wizard • Step {currentStep + 1} of {STEPS.length}
          </span>
          <span className="text-xs text-slate-500 font-medium">
            {STEPS[currentStep]}
          </span>
        </div>

        {/* Stepper Dots & Progress */}
        <div className="flex items-center gap-2">
          {STEPS.map((step, idx) => (
            <div key={step} className="flex-1 flex flex-col items-center gap-1.5">
              <div
                className={`h-2 w-full rounded-full transition-all duration-300 ${
                  idx < currentStep
                    ? 'bg-emerald-500'
                    : idx === currentStep
                    ? 'bg-brand-600 dark:bg-brand-500 ring-2 ring-brand-300 dark:ring-brand-900'
                    : 'bg-slate-200 dark:bg-slate-800'
                }`}
              />
              <span className="hidden sm:inline text-[10px] text-center font-medium truncate max-w-[100px] text-slate-500">
                {step}
              </span>
            </div>
          ))}
        </div>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* STEP 0: Welcome & Environment Check */}
      {currentStep === 0 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Sparkles className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Welcome to Unifierr
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                We will guide you through setting up a complete, automated media server in a few simple clicks. No API keys, ports, or Docker network configuration required.
              </p>
            </div>
          </div>

          {/* Environment Report Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2 bg-slate-50/50 dark:bg-slate-950/50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500">Operating System / Platform</span>
                <Cpu className="h-4 w-4 text-slate-400" />
              </div>
              <div className="text-lg font-bold capitalize text-slate-900 dark:text-white flex items-center gap-2">
                <span>{envReport?.platform || 'Detecting...'}</span>
                <span className="text-xs font-normal text-slate-400">
                  {envReport?.in_container ? '(Docker container)' : '(Host)'}
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 space-y-2 bg-slate-50/50 dark:bg-slate-950/50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500">Docker Availability</span>
                <Server className="h-4 w-4 text-slate-400" />
              </div>
              <div className="flex items-center gap-2">
                {envReport?.docker_available ? (
                  <div className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 className="h-4 w-4" />
                    Available ({envReport.docker_version || 'Ready'})
                  </div>
                ) : (
                  <div className="inline-flex items-center gap-1.5 text-sm font-semibold text-red-600 dark:text-red-400">
                    <XCircle className="h-4 w-4" />
                    Not connected
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Docker Error details if not available */}
          {envReport && !envReport.docker_available && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30 p-4 text-sm text-amber-900 dark:text-amber-200 space-y-2">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                Docker engine is not reachable
              </div>
              <p className="text-xs leading-relaxed">
                {envReport.docker_error || 'Unifierr needs access to the Docker socket (/var/run/docker.sock) to manage and connect apps.'}
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-300">
                You can still adopt apps already running on your network if Docker is not present.
              </p>
            </div>
          )}

          {/* Platform Notes */}
          {envReport && envReport.notes && envReport.notes.length > 0 && (
            <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-slate-50/70 dark:bg-slate-950/40">
              <h4 className="text-xs font-semibold uppercase text-slate-600 dark:text-slate-400 mb-2">
                Platform Recommendations:
              </h4>
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300 list-disc list-inside">
                {envReport.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex justify-end pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => {
                setCurrentStep(1);
              }}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition"
            >
              Continue to Storage
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 1: Storage Setup */}
      {currentStep === 1 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <HardDrive className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Storage & Media Folders
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Unifierr sets up the community standard TRaSH folder layout so torrents and library files share one drive and import instantly without double space (<JargonHelp term="Hardlinks" />).
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300 mb-1.5">
                Storage Root Directory
              </label>
              <input
                type="text"
                value={rootFolder}
                onChange={(e) => setRootFolder(e.target.value)}
                placeholder="/srv/unifierr"
                className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 px-4 py-2.5 text-sm font-mono text-slate-900 dark:text-white focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
              <p className="mt-1 text-xs text-slate-500">
                All data, downloads, and app configurations will live under this root path.
              </p>
            </div>

            {/* Advanced Toggle */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowAdvancedStorage(!showAdvancedStorage)}
                className="flex items-center gap-1.5 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline"
              >
                <Sliders className="h-3.5 w-3.5" />
                {showAdvancedStorage ? 'Hide Advanced Permissions' : 'Advanced (PUID, PGID, Timezone)'}
                {showAdvancedStorage ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>

              {showAdvancedStorage && (
                <div className="mt-3 p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 grid grid-cols-1 sm:grid-cols-3 gap-3 animate-in fade-in duration-200">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                      <JargonHelp term="PUID" label="User ID (PUID)" />
                    </label>
                    <input
                      type="number"
                      value={puid}
                      onChange={(e) => setPuid(Number(e.target.value))}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-mono text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                      <JargonHelp term="PGID" label="Group ID (PGID)" />
                    </label>
                    <input
                      type="number"
                      value={pgid}
                      onChange={(e) => setPgid(Number(e.target.value))}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-mono text-slate-900 dark:text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                      Timezone
                    </label>
                    <input
                      type="text"
                      value={timezone}
                      onChange={(e) => setTimezone(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-mono text-slate-900 dark:text-white"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Folder Check Action */}
            <div className="pt-2">
              <button
                type="button"
                onClick={handlePrepareStorage}
                disabled={loading}
                className="flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold py-2 px-4 text-xs hover:opacity-90 transition disabled:opacity-50"
              >
                {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <FolderCheck className="h-3.5 w-3.5" />}
                Prepare & Verify Folders
              </button>
            </div>

            {/* Folder Report Display */}
            {folderReport && (
              <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/40 dark:bg-emerald-950/20 p-4 space-y-3">
                <div className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  Folders Ready & Verified
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-slate-600 dark:text-slate-300">
                  <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800">
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Writable</span>
                    <span className="font-semibold text-emerald-600">{folderReport.writable ? 'Yes' : 'No'}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800">
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Hardlinks Supported</span>
                    <span className="font-semibold text-emerald-600">{folderReport.same_filesystem ? 'Yes (Instant Import)' : 'Different Filesystems'}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800">
                    <span className="block text-[10px] text-slate-400 uppercase font-semibold">Free Storage</span>
                    <span className="font-semibold">{formatBytes(folderReport.free_bytes)} / {formatBytes(folderReport.total_bytes)}</span>
                  </div>
                </div>

                {folderReport.problems && folderReport.problems.length > 0 && (
                  <div className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
                    {folderReport.problems.map((p, i) => (
                      <div key={i} className="flex items-center gap-1.5">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        <span>{p.message}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(0)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentStep(2);
                loadDetection();
              }}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition"
            >
              Continue to Apps
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 2: Find & Select Apps */}
      {currentStep === 2 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Layers className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Choose Your Apps
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                We scanned your system for existing services. Adopt what you already have, or let Unifierr install and configure missing apps for you.
              </p>
            </div>
          </div>

          {/* Media Server Choice */}
          <div className="rounded-xl border border-brand-200/60 bg-brand-50/40 dark:border-brand-900/40 dark:bg-brand-950/20 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-brand-900 dark:text-brand-300">
                Which media streaming server do you prefer?
              </span>
              <Tooltip content="Jellyfin is 100% free and open-source. Plex is popular with wide smart TV app support." />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition ${
                  mediaServerChoice === 'jellyfin'
                    ? 'border-brand-500 bg-white dark:bg-slate-900 shadow-sm ring-1 ring-brand-500'
                    : 'border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50'
                }`}
              >
                <input
                  type="radio"
                  name="mediaServer"
                  value="jellyfin"
                  checked={mediaServerChoice === 'jellyfin'}
                  onChange={() => {
                    setMediaServerChoice('jellyfin');
                    setSelectedToInstall((prev) => {
                      const next = new Set(prev);
                      next.add('jellyfin');
                      next.delete('plex');
                      return next;
                    });
                  }}
                  className="text-brand-600 focus:ring-brand-500"
                />
                <div>
                  <div className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                    Jellyfin <span className="text-[10px] bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-1.5 py-0.5 rounded font-semibold">Recommended</span>
                  </div>
                  <div className="text-xs text-slate-500">100% free & open-source, no account required.</div>
                </div>
              </label>

              <label
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition ${
                  mediaServerChoice === 'plex'
                    ? 'border-brand-500 bg-white dark:bg-slate-900 shadow-sm ring-1 ring-brand-500'
                    : 'border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50'
                }`}
              >
                <input
                  type="radio"
                  name="mediaServer"
                  value="plex"
                  checked={mediaServerChoice === 'plex'}
                  onChange={() => {
                    setMediaServerChoice('plex');
                    setSelectedToInstall((prev) => {
                      const next = new Set(prev);
                      next.add('plex');
                      next.delete('jellyfin');
                      return next;
                    });
                  }}
                  className="text-brand-600 focus:ring-brand-500"
                />
                <div>
                  <div className="text-sm font-bold text-slate-900 dark:text-white">Plex Media Server</div>
                  <div className="text-xs text-slate-500">Popular commercial media streamer.</div>
                </div>
              </label>
            </div>
          </div>

          {/* App Cards List */}
          <div className="space-y-3">
            {ALL_APPS.filter((app) => {
              if (app.kind === 'plex' && mediaServerChoice !== 'plex') return false;
              if (app.kind === 'jellyfin' && mediaServerChoice !== 'jellyfin') return false;
              return true;
            }).map((app) => {
              const detected = detectedApps.find((d) => d.kind === app.kind);
              const isAdopted = adoptedKinds.has(app.kind);
              const isToInstall = selectedToInstall.has(app.kind);
              const showAdv = openAdoptAdvanced[app.kind] || false;

              return (
                <div
                  key={app.kind}
                  className={`rounded-xl border p-4 transition ${
                    isAdopted
                      ? 'border-emerald-300 bg-emerald-50/30 dark:border-emerald-900/50 dark:bg-emerald-950/20'
                      : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900'
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-slate-900 dark:text-white">{app.name}</span>
                        {detected?.reachable_url && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 px-2 py-0.5 text-[10px] font-semibold">
                            <Radio className="h-3 w-3 animate-pulse" /> Found at {detected.reachable_url}
                          </span>
                        )}
                        {isAdopted && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-semibold">
                            <CheckCircle2 className="h-3 w-3" /> Adopted
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{app.desc}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {detected && !isAdopted && (
                        <button
                          type="button"
                          onClick={() => handleAdopt(app.kind)}
                          disabled={loading}
                          className="rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold py-1.5 px-3 transition shadow-xs"
                        >
                          Use this
                        </button>
                      )}

                      {!isAdopted && (
                        <label className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={isToInstall}
                            onChange={(e) => {
                              setSelectedToInstall((prev) => {
                                const next = new Set(prev);
                                if (e.target.checked) next.add(app.kind);
                                else next.delete(app.kind);
                                return next;
                              });
                            }}
                            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500 dark:border-slate-700 dark:bg-slate-800"
                          />
                          <span>Install for me</span>
                        </label>
                      )}

                      <button
                        type="button"
                        onClick={() =>
                          setOpenAdoptAdvanced((prev) => ({
                            ...prev,
                            [app.kind]: !prev[app.kind],
                          }))
                        }
                        className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 px-1.5 py-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                        aria-expanded={showAdv}
                        title="Type the address and key yourself"
                      >
                        <Sliders className="h-3.5 w-3.5" aria-hidden="true" />
                        Advanced
                      </button>
                    </div>
                  </div>

                  {/* Manual Connection Expander */}
                  {showAdv && (
                    <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                      <p className="sm:col-span-2 text-[11px] text-slate-500">
                        Only needed if Unifierr could not connect by itself. The API key is in the app under
                        Settings → General → Security → API Key.
                      </p>
                      <label className="block">
                        <span className="text-[10px] font-medium text-slate-500 block mb-0.5">Address (e.g. http://192.168.1.10:7878)</span>
                        <input
                          type="url"
                          autoComplete="off"
                          value={customAdoptForm[app.kind]?.base_url || ''}
                          onChange={(e) => {
                            const val = e.target.value;
                            setCustomAdoptForm((prev) => {
                              const existing = prev[app.kind] || { base_url: '', api_key: '', username: '', password: '' };
                              return { ...prev, [app.kind]: { ...existing, base_url: val } };
                            });
                          }}
                          placeholder={detected?.reachable_url || 'http://...'}
                          className="w-full rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2 py-1 text-xs"
                        />
                      </label>
                      {app.kind !== 'qbittorrent' && (
                      <label className="block">
                          <span className="text-[10px] font-medium text-slate-500 block mb-0.5">API key or token</span>
                          <input
                            type="password"
                            autoComplete="off"
                            value={customAdoptForm[app.kind]?.api_key || ''}
                            onChange={(e) => {
                              const val = e.target.value;
                              setCustomAdoptForm((prev) => {
                                const existing = prev[app.kind] || { base_url: '', api_key: '', username: '', password: '' };
                                return { ...prev, [app.kind]: { ...existing, api_key: val } };
                              });
                            }}
                            placeholder="Leave empty if found automatically"
                            className="w-full rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2 py-1 text-xs"
                          />
                        </label>
                      )}
                      {(app.kind === 'qbittorrent' || app.kind === 'jellyfin') && (
                        <>
                      <label className="block">
                            <span className="text-[10px] font-medium text-slate-500 block mb-0.5">Username</span>
                            <input
                              type="text"
                              autoComplete="off"
                              value={customAdoptForm[app.kind]?.username || ''}
                              onChange={(e) => {
                                const val = e.target.value;
                                setCustomAdoptForm((prev) => {
                                  const existing = prev[app.kind] || { base_url: '', api_key: '', username: '', password: '' };
                                  return { ...prev, [app.kind]: { ...existing, username: val } };
                                });
                              }}
                              placeholder="admin"
                              className="w-full rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2 py-1 text-xs"
                            />
                          </label>
                      <label className="block">
                            <span className="text-[10px] font-medium text-slate-500 block mb-0.5">Password</span>
                            <input
                              type="password"
                              autoComplete="off"
                              value={customAdoptForm[app.kind]?.password || ''}
                              onChange={(e) => {
                                const val = e.target.value;
                                setCustomAdoptForm((prev) => {
                                  const existing = prev[app.kind] || { base_url: '', api_key: '', username: '', password: '' };
                                  return { ...prev, [app.kind]: { ...existing, password: val } };
                                });
                              }}
                              placeholder=""
                              className="w-full rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2 py-1 text-xs"
                            />
                          </label>
                        </>
                      )}
                      <div className="sm:col-span-2 flex justify-end">
                        <button
                          type="button"
                          onClick={() => handleAdopt(app.kind)}
                          disabled={loading}
                          className="rounded bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 text-xs px-2.5 py-1 font-semibold"
                        >
                          Connect
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(1)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
            <button
              type="button"
              onClick={() => {
                setCurrentStep(3);
                startInstall();
              }}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition"
            >
              Install & Setup Apps
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: Installing Apps */}
      {currentStep === 3 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Server className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Installing Apps in Docker
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Pulling verified LinuxServer container images and configuring shared TRaSH storage paths.
              </p>
            </div>
          </div>

          {installJob && installJob.steps.length > 0 && (
            <ProgressBar
              value={
                (installJob.steps.filter((s) => s.status === 'ok' || s.status === 'skipped').length /
                  installJob.steps.length) *
                100
              }
              label="Overall Installation Progress"
              size="sm"
            />
          )}

          {/* Job Progress Steps */}
          <div className="space-y-3">
            {installJob ? (
              installJob.steps.map((step, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between gap-3 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50"
                >
                  <div className="flex items-start gap-3">
                    {step.status === 'ok' && <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />}
                    {step.status === 'running' && <RefreshCw className="h-5 w-5 text-brand-500 animate-spin shrink-0 mt-0.5" />}
                    {step.status === 'pending' && <div className="h-5 w-5 rounded-full border-2 border-slate-300 dark:border-slate-700 shrink-0 mt-0.5" />}
                    {step.status === 'skipped' && <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />}
                    {step.status === 'failed' && <XCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />}

                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-white">{step.name}</div>
                      {step.message && <div className="text-xs text-slate-500 mt-0.5">{step.message}</div>}
                      {step.explanation && (
                        <div className="mt-1 text-xs text-red-600 dark:text-red-400 font-medium">
                          {step.explanation}
                        </div>
                      )}
                      {step.fix && (
                        <div className="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400">
                          Fix: {step.fix}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className="text-xs font-semibold capitalize text-slate-400">{step.status}</span>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-sm text-slate-500">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-500" />
                Preparing install job...
              </div>
            )}
          </div>

          {/* Collapsible raw logs */}
          {installJob && installJob.log && installJob.log.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
              <button
                type="button"
                onClick={() => setShowInstallLogs(!showInstallLogs)}
                className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              >
                <FileCode className="h-3.5 w-3.5" />
                {showInstallLogs ? 'Hide detailed log' : 'Show detailed log'}
                {showInstallLogs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>

              {showInstallLogs && (
                <pre className="mt-2 p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] max-h-48 overflow-y-auto leading-relaxed">
                  {installJob.log.join('\n')}
                </pre>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(2)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
            <button
              type="button"
              disabled={installJob?.status === 'running'}
              onClick={() => {
                setCurrentStep(4);
                startWire();
              }}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition disabled:opacity-50"
            >
              {installJob?.status === 'done' ? 'Continue to Connecting' : 'Next Step'}
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 4: Connect Everything (Auto-wiring) */}
      {currentStep === 4 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Sparkles className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Connecting Everything Together
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Unifierr connects download clients, indexers, subtitles, and media libraries automatically in the background.
              </p>
            </div>
          </div>

          {wireJob && wireJob.steps.length > 0 && (
            <ProgressBar
              value={
                (wireJob.steps.filter((s) => s.status === 'ok' || s.status === 'skipped').length /
                  wireJob.steps.length) *
                100
              }
              label="Overall Connection Progress"
              size="sm"
            />
          )}

          {/* Wiring Steps */}
          <div className="space-y-3">
            {wireJob ? (
              wireJob.steps.map((step, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between gap-3 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50"
                >
                  <div className="flex items-start gap-3">
                    {step.status === 'ok' && <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />}
                    {step.status === 'running' && <RefreshCw className="h-5 w-5 text-brand-500 animate-spin shrink-0 mt-0.5" />}
                    {step.status === 'pending' && <div className="h-5 w-5 rounded-full border-2 border-slate-300 dark:border-slate-700 shrink-0 mt-0.5" />}
                    {step.status === 'skipped' && <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />}
                    {step.status === 'failed' && <XCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />}

                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-white">{step.name}</div>
                      {step.message && <div className="text-xs text-slate-500 mt-0.5">{step.message}</div>}
                      {step.explanation && (
                        <div className="mt-1 text-xs text-red-600 dark:text-red-400 font-medium">
                          {step.explanation}
                        </div>
                      )}
                      {step.fix && (
                        <div className="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                          Suggested Fix: {step.fix}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className="text-xs font-semibold capitalize text-slate-400">{step.status}</span>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-sm text-slate-500">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-500" />
                Connecting external services...
              </div>
            )}
          </div>

          {/* Retry Button if any step failed */}
          {wireJob && wireJob.status === 'failed' && (
            <div className="p-4 rounded-xl border border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/30 flex items-center justify-between">
              <span className="text-xs text-red-800 dark:text-red-300">
                Some connections could not be established. Make sure external services have finished booting up.
              </span>
              <button
                type="button"
                onClick={startWire}
                className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-semibold py-1.5 px-3 shadow-xs"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Retry Wiring
              </button>
            </div>
          )}

          {/* Logs */}
          {wireJob && wireJob.log && wireJob.log.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
              <button
                type="button"
                onClick={() => setShowWireLogs(!showWireLogs)}
                className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
              >
                <FileCode className="h-3.5 w-3.5" />
                {showWireLogs ? 'Hide detailed log' : 'Show detailed log'}
                {showWireLogs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>

              {showWireLogs && (
                <pre className="mt-2 p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] max-h-48 overflow-y-auto leading-relaxed">
                  {wireJob.log.join('\n')}
                </pre>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(3)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
            <button
              type="button"
              disabled={wireJob?.status === 'running'}
              onClick={() => {
                setCurrentStep(5);
                loadTrashStatus();
              }}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition disabled:opacity-50"
            >
              Continue to Quality Profiles
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 5: Apply TRaSH Quality Profiles */}
      {currentStep === 5 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 sm:p-8 space-y-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-400">
              <Sliders className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                Apply TRaSH Quality Profiles
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Sync community-curated TRaSH-Guides quality profiles, custom formats, and release size limits into Radarr and Sonarr. Existing user profiles are never deleted.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {trashPresets.map((preset) => {
              const selected = selectedTrashProfile === preset.id;
              return (
                <label
                  key={preset.id}
                  className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition ${
                    selected
                      ? 'border-brand-500 bg-brand-50/40 dark:bg-brand-950/20 ring-1 ring-brand-500'
                      : 'border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-950/40 hover:border-slate-300'
                  }`}
                >
                  <input
                    type="radio"
                    name="trashProfile"
                    value={preset.id}
                    checked={selected}
                    onChange={() => setSelectedTrashProfile(preset.id)}
                    className="mt-1 text-brand-600 focus:ring-brand-500"
                  />
                  <div className="space-y-1">
                    <div className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      {preset.name}
                      {preset.id === 'hd-1080p' && (
                        <span className="text-[10px] bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-1.5 py-0.5 rounded font-semibold">
                          Recommended
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                      {preset.description}
                    </p>
                    <div className="text-[11px] font-mono text-slate-400 pt-0.5">
                      Radarr: {preset.radarr_profile} • Sonarr: {preset.sonarr_profile}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={startTrashSync}
              disabled={loading || trashJob?.status === 'running'}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-semibold py-2.5 px-5 text-xs hover:opacity-90 transition disabled:opacity-50"
            >
              {trashJob?.status === 'running' ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {trashJob ? 'Re-apply TRaSH Quality Profiles' : 'Apply TRaSH Quality Profiles'}
            </button>
          </div>

          {trashJob && (
            <div className="space-y-3">
              {trashJob.steps.map((step, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between gap-3 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50"
                >
                  <div className="flex items-start gap-3">
                    {step.status === 'ok' && <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />}
                    {step.status === 'running' && <RefreshCw className="h-5 w-5 text-brand-500 animate-spin shrink-0 mt-0.5" />}
                    {step.status === 'pending' && <div className="h-5 w-5 rounded-full border-2 border-slate-300 dark:border-slate-700 shrink-0 mt-0.5" />}
                    {step.status === 'skipped' && <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />}
                    {step.status === 'failed' && <XCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />}

                    <div>
                      <div className="text-sm font-semibold text-slate-900 dark:text-white">{step.name}</div>
                      {step.message && <div className="text-xs text-slate-500 mt-0.5">{step.message}</div>}
                      {step.explanation && (
                        <div className="mt-1 text-xs text-red-600 dark:text-red-400 font-medium">
                          {step.explanation}
                        </div>
                      )}
                      {step.fix && (
                        <div className="mt-0.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                          Suggested Fix: {step.fix}
                        </div>
                      )}
                    </div>
                  </div>
                  <span className="text-xs font-semibold capitalize text-slate-400">{step.status}</span>
                </div>
              ))}

              {trashJob.log && trashJob.log.length > 0 && (
                <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                  <button
                    type="button"
                    onClick={() => setShowTrashLogs(!showTrashLogs)}
                    className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                  >
                    <FileCode className="h-3.5 w-3.5" />
                    {showTrashLogs ? 'Hide detailed log' : 'Show detailed log'}
                    {showTrashLogs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </button>

                  {showTrashLogs && (
                    <pre className="mt-2 p-3 rounded-xl bg-slate-950 text-slate-300 font-mono text-[11px] max-h-48 overflow-y-auto leading-relaxed">
                      {trashJob.log.join('\n')}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setCurrentStep(4)}
              className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" /> Back
            </button>
            <button
              type="button"
              disabled={trashJob?.status === 'running'}
              onClick={() => setCurrentStep(6)}
              className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold py-2.5 px-6 text-sm shadow-md shadow-brand-500/20 transition disabled:opacity-50"
            >
              Finish Setup
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* STEP 6: All Done Celebration */}
      {currentStep === 6 && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center space-y-6 shadow-sm">
          <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto shadow-inner">
            <CheckCircle2 className="w-10 h-10" />
          </div>

          <div className="max-w-md mx-auto space-y-2">
            <h2 className="text-2xl font-extrabold text-slate-900 dark:text-white">
              You're all set!
            </h2>
            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
              Your entire media stack is configured, wired, and ready to go. You can now discover movies and series, request downloads, and watch your media from one simple place.
            </p>
          </div>

          <div className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 max-w-sm mx-auto text-left text-xs space-y-2 text-slate-600 dark:text-slate-300">
            <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" /> Single-folder TRaSH storage
            </div>
            <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" /> TRaSH quality profiles & custom formats
            </div>
            <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" /> Automated movie & series requests
            </div>
            <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-200">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" /> Automatic subtitle retrieval
            </div>
          </div>

          <div className="pt-4">
            <button
              type="button"
              onClick={handleComplete}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-bold py-3 px-8 text-base shadow-lg shadow-brand-500/25 transition focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
            >
              {loading ? 'Finalizing...' : 'Explore Discover'}
              <ArrowRight className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
