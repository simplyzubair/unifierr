import React, { useState, useEffect, useRef } from 'react';
import { downloadsApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { QueueStateBadge } from '@/components/common/Badge';
import { ProgressBar } from '@/components/common/ProgressBar';
import { EmptyState } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TableSkeleton } from '@/components/common/Skeleton';
import type { QueueItem } from '@/types/api';
import {
  Download,
  ArrowDown,
  ArrowUp,
  Pause,
  Play,
  Trash2,
  Clock,
  Film,
  Tv,
} from 'lucide-react';

export const Downloads: React.FC = () => {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [dlSpeed, setDlSpeed] = useState<number | null>(null);
  const [upSpeed, setUpSpeed] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Delete dialog state
  const [deleteTarget, setDeleteTarget] = useState<QueueItem | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const fetchDownloads = async (isFirst = false) => {
    try {
      const data = await downloadsApi.getDownloads();
      setItems(data.items || []);
      setDlSpeed(data.dl_speed ?? null);
      setUpSpeed(data.up_speed ?? null);
      if (isFirst) setLoading(false);
    } catch (err: unknown) {
      if (isFirst) {
        setError(err as Error);
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchDownloads(true);
    pollTimerRef.current = setInterval(() => {
      fetchDownloads(false);
    }, 3000); // 3s interval per spec

    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, []);

  const handlePause = async (id: string) => {
    try {
      await downloadsApi.pause(id);
      await fetchDownloads();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleResume = async (id: string) => {
    try {
      await downloadsApi.resume(id);
      await fetchDownloads();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const handleDeleteConfirm = async (deleteFiles?: boolean) => {
    if (!deleteTarget) return;
    try {
      await downloadsApi.deleteDownload(deleteTarget.id, !!deleteFiles);
      setDeleteTarget(null);
      await fetchDownloads();
    } catch (err: unknown) {
      setError(err as Error);
    }
  };

  const formatSpeed = (bytesPerSec?: number | null) => {
    if (!bytesPerSec || bytesPerSec === 0) return '0 KB/s';
    const mb = bytesPerSec / (1024 * 1024);
    if (mb >= 1) return `${mb.toFixed(1)} MB/s`;
    const kb = bytesPerSec / 1024;
    return `${kb.toFixed(0)} KB/s`;
  };

  const formatBytes = (bytes?: number | null) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const formatEta = (seconds?: number | null) => {
    if (!seconds || seconds <= 0) return '—';
    if (seconds > 86400 * 7) return '> 1 week';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  };

  return (
    <div className="space-y-6">
      {/* Header & Speed Totals */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Download className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Active Downloads
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Real-time download activity across qBittorrent, Radarr, and Sonarr.
          </p>
        </div>

        {/* Speed Stats Pill */}
        <div className="flex items-center gap-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-2.5 px-4 shadow-xs self-start sm:self-auto">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <ArrowDown className="h-4 w-4" />
            <span>{formatSpeed(dlSpeed)}</span>
          </div>
          <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
          <div className="flex items-center gap-1.5 text-xs font-semibold text-sky-600 dark:text-sky-400">
            <ArrowUp className="h-4 w-4" />
            <span>{formatSpeed(upSpeed)}</span>
          </div>
          <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
          <div className="text-xs font-medium text-slate-500">
            {items.length} {items.length === 1 ? 'task' : 'tasks'}
          </div>
        </div>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* Downloads List */}
      {loading ? (
        <TableSkeleton rows={4} />
      ) : items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-xs hover:border-slate-300 dark:hover:border-slate-700 transition space-y-3"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 shrink-0 mt-0.5">
                    {item.media_type === 'series' ? <Tv className="h-4 w-4" /> : <Film className="h-4 w-4" />}
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate" title={item.name}>
                      {item.media_title || item.name}
                    </h3>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mt-0.5">
                      <span className="font-mono text-[11px] truncate max-w-xs">{item.name}</span>
                      {item.category && (
                        <span className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.2 text-[10px] font-semibold text-slate-600 dark:text-slate-300 uppercase">
                          {item.category}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                  <QueueStateBadge state={item.state} />

                  {item.state === 'paused' ? (
                    <button
                      type="button"
                      onClick={() => handleResume(item.id)}
                      className="p-1.5 rounded-lg text-slate-600 hover:text-emerald-600 hover:bg-emerald-50 dark:text-slate-400 dark:hover:bg-emerald-950/40 transition"
                      title="Resume Download"
                    >
                      <Play className="h-4 w-4" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handlePause(item.id)}
                      className="p-1.5 rounded-lg text-slate-600 hover:text-amber-600 hover:bg-amber-50 dark:text-slate-400 dark:hover:bg-amber-950/40 transition"
                      title="Pause Download"
                    >
                      <Pause className="h-4 w-4" />
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => setDeleteTarget(item)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition"
                    title="Remove Download"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Progress Bar & Details */}
              <div className="space-y-1.5">
                <ProgressBar
                  value={item.progress}
                  showPercentage={false}
                  size="sm"
                  color={item.state === 'paused' ? 'amber' : item.state === 'error' ? 'amber' : 'brand'}
                />

                <div className="flex flex-wrap items-center justify-between text-xs text-slate-500 font-medium">
                  <div className="flex items-center gap-3">
                    <span>{Math.round(item.progress)}%</span>
                    <span>
                      {formatBytes(item.downloaded)} of {formatBytes(item.size)}
                    </span>
                    {item.download_speed && item.download_speed > 0 ? (
                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                        ↓ {formatSpeed(item.download_speed)}
                      </span>
                    ) : null}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-slate-400" />
                    <span>ETA: {formatEta(item.eta_seconds)}</span>
                  </div>
                </div>
              </div>

              {item.error && (
                <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/40 p-2 rounded-lg">
                  {item.error}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : error ? null : (
        <EmptyState
          icon={Download}
          title="No downloads right now"
          description="Everything is quiet. Request something to watch from the Discover page!"
        />
      )}

      {/* Remove Confirmation Dialog with 'delete files' checkbox */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        title="Remove Download"
        description={`Are you sure you want to remove "${deleteTarget?.media_title || deleteTarget?.name}" from the queue?`}
        confirmLabel="Remove"
        isDestructive
        checkboxLabel="Also delete downloaded files from disk"
        defaultCheckboxState={false}
      />
    </div>
  );
};
