import React, { useState, useEffect } from 'react';
import { healthApi, storageApi, eventsApi, setupApi, jobsApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { ProgressBar } from '@/components/common/ProgressBar';
import { CardSkeleton } from '@/components/common/Skeleton';
import type { HealthOverview, StorageResponse, EventItem, HealthIssue, Job } from '@/types/api';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HardDrive,
  Clock,
  RefreshCw,
  FolderCheck,
  ShieldAlert,
  Wrench,
} from 'lucide-react';

export const Health: React.FC = () => {
  const [overview, setOverview] = useState<HealthOverview | null>(null);
  const [storage, setStorage] = useState<StorageResponse | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const loadData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [h, s, e] = await Promise.all([
        healthApi.getOverview(),
        storageApi.getStorage(),
        eventsApi.getEvents(30),
      ]);
      setOverview(h);
      setStorage(s);
      setEvents(e);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // "Try to fix automatically": re-run the setup's "Connect everything" job. It is safe to repeat: it only adds
  // missing connections and folders, never removes anything.
  const [fixJob, setFixJob] = useState<Job | null>(null);
  const [fixing, setFixing] = useState(false);
  const runFix = async () => {
    setFixing(true);
    setFixJob(null);
    try {
      const { job_id } = await setupApi.wire();
      for (let i = 0; i < 200; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const job = await jobsApi.getJob(job_id);
        setFixJob(job);
        if (job.status !== 'running') break;
      }
      await loadData(true);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setFixing(false);
    }
  };
  const fixFailed = fixJob?.steps.filter((step) => step.status === 'failed') ?? [];

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Activity className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            System Health & Diagnostics
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Real-time status of external apps, storage availability, and system activity.
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadData(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh Status'}
        </button>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {overview && overview.overall !== 'ok' && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Unifierr can reconnect your apps and recreate missing folders and settings for you. It never deletes anything.
            </p>
            <button
              type="button"
              onClick={() => void runFix()}
              disabled={fixing}
              className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white px-3.5 py-2 text-xs font-semibold disabled:opacity-50 shrink-0"
            >
              <Wrench className={`h-3.5 w-3.5 ${fixing ? 'animate-spin' : ''}`} />
              {fixing ? 'Fixing…' : 'Try to fix automatically'}
            </button>
          </div>
          {fixJob && fixJob.status !== 'running' && (
            <div role="status" className="text-sm">
              {fixFailed.length === 0 ? (
                <p className="text-emerald-700 dark:text-emerald-300">
                  Done. Everything Unifierr can set up is connected. Anything still listed below needs a manual step.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {fixFailed.map((step) => (
                    <li key={step.name} className="text-amber-800 dark:text-amber-300">
                      <span className="font-semibold">{step.name}:</span> {step.message}
                      {step.fix && <span className="block text-xs opacity-90">How to fix: {step.fix}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : overview ? (
        <>
          {/* Overall Health Banner */}
          <div
            className={`rounded-2xl p-5 border flex items-start gap-4 transition shadow-xs ${
              overview.overall === 'ok'
                ? 'bg-emerald-50/80 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-900/50 text-emerald-900 dark:text-emerald-200'
                : overview.overall === 'warning'
                ? 'bg-amber-50/80 border-amber-200 dark:bg-amber-950/30 dark:border-amber-900/50 text-amber-900 dark:text-amber-200'
                : 'bg-red-50/80 border-red-200 dark:bg-red-950/30 dark:border-red-900/50 text-red-900 dark:text-red-200'
            }`}
          >
            {overview.overall === 'ok' ? (
              <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            ) : overview.overall === 'warning' ? (
              <AlertTriangle className="h-6 w-6 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-6 w-6 text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
            )}
            <div>
              <h2 className="text-base font-bold">
                {overview.overall === 'ok'
                  ? 'All services operational'
                  : overview.overall === 'warning'
                  ? 'Some services require attention'
                  : 'Critical issues detected'}
              </h2>
              <p className="text-xs mt-0.5 opacity-90 leading-relaxed">
                {overview.overall === 'ok'
                  ? 'Everything is running smoothly. Radarr, Sonarr, qBittorrent, and your media server are communicating without issues.'
                  : `${overview.issues?.length || 1} problem(s) detected with your stack. Check the resolutions below.`}
              </p>
            </div>
          </div>

          {/* Actionable Issues List */}
          {overview.issues && overview.issues.length > 0 && (
            <div className="space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <ShieldAlert className="h-4 w-4 text-amber-500" />
                Actionable Issues ({overview.issues.length})
              </h3>
              <div className="space-y-3">
                {overview.issues.map((issue: HealthIssue, idx: number) => (
                  <div
                    key={idx}
                    className="rounded-2xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/50 dark:bg-amber-950/20 p-4 space-y-2 text-xs"
                  >
                    <div className="flex items-center gap-2 font-bold text-amber-950 dark:text-amber-200 text-sm">
                      <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                      <span>{issue.message}</span>
                      {issue.source && (
                        <span className="rounded bg-amber-200/60 dark:bg-amber-900/60 px-1.5 py-0.5 text-[10px] font-mono uppercase">
                          {issue.source}
                        </span>
                      )}
                    </div>

                    {issue.explanation && (
                      <div className="text-slate-600 dark:text-slate-300 leading-relaxed">
                        <span className="font-semibold text-slate-700 dark:text-slate-200">What this means: </span>
                        {issue.explanation}
                      </div>
                    )}

                    {issue.fix && (
                      <div className="rounded-xl bg-white dark:bg-slate-900 border border-emerald-200 dark:border-emerald-900/60 p-2.5 text-emerald-800 dark:text-emerald-300">
                        <span className="font-semibold">How to fix: </span>
                        {issue.fix}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Per-Service Cards */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Connected Apps ({overview.services?.length || 0})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {overview.services?.map((svc) => (
                <div
                  key={svc.kind}
                  className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-3 shadow-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-slate-900 dark:text-white capitalize">
                      {svc.name}
                    </span>
                    {svc.status.ok ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-semibold">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" /> Operational
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300 px-2 py-0.5 text-[10px] font-semibold">
                        <XCircle className="h-3 w-3 text-red-500" /> Offline
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-slate-500 space-y-1">
                    <div>Status: <span className="text-slate-700 dark:text-slate-300 font-medium">{svc.status.message}</span></div>
                    {svc.status.version && (
                      <div>Version: <span className="font-mono text-[11px]">{svc.status.version}</span></div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Storage & Disks Section */}
          {storage && (
            <div className="space-y-4 pt-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <HardDrive className="h-4 w-4 text-brand-500" />
                Storage & Hardlinks
              </h3>

              {storage.disks && storage.disks.length > 0 && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {storage.disks.map((d, i) => {
                    const used = d.total_bytes - d.free_bytes;
                    const pct = d.total_bytes > 0 ? (used / d.total_bytes) * 100 : 0;
                    return (
                      <div
                        key={i}
                        className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2 shadow-xs"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-mono font-semibold text-slate-900 dark:text-white truncate">
                            {d.label || d.path}
                          </span>
                          <span className="text-slate-500 text-[11px]">
                            {formatBytes(d.free_bytes)} free of {formatBytes(d.total_bytes)}
                          </span>
                        </div>
                        <ProgressBar
                          value={pct}
                          showPercentage={false}
                          color={pct > 90 ? 'amber' : 'brand'}
                          size="sm"
                        />
                      </div>
                    );
                  })}
                </div>
              )}

              {storage.folders && (
                <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-4 text-xs space-y-2">
                  <div className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-200">
                    <FolderCheck className="h-4 w-4 text-emerald-500" />
                    Storage Root: <span className="font-mono">{storage.folders.root}</span>
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">
                    Hardlinks: {storage.folders.same_filesystem ? (
                      <span className="text-emerald-600 font-semibold">Enabled (Torrents and media on same filesystem)</span>
                    ) : (
                      <span className="text-amber-600 font-semibold">Disabled (Cross-device copies will duplicate space)</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recent Events Log */}
          <div className="space-y-3 pt-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              <Clock className="h-4 w-4 text-slate-400" />
              Recent Troubleshooting Events
            </h3>

            {events.length > 0 ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden divide-y divide-slate-100 dark:divide-slate-800/80 text-xs shadow-xs">
                {events.map((ev) => (
                  <div key={ev.id} className="p-3.5 flex items-start gap-3">
                    {ev.level === 'error' ? (
                      <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                    ) : ev.level === 'warning' ? (
                      <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold uppercase text-[10px] text-slate-500 rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2">
                          {ev.source}
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          {new Date(ev.ts).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-slate-800 dark:text-slate-200 mt-0.5 leading-relaxed">
                        {ev.message}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center text-xs text-slate-500 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                No recent diagnostic events logged.
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
};
