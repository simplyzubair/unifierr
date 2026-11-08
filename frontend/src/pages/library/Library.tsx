import React, { useState, useEffect } from 'react';
import { mediaApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { AvailabilityBadge } from '@/components/common/Badge';
import { PosterSkeleton } from '@/components/common/Skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useAuth } from '@/context/AuthContext';
import type { MediaResult, MediaType } from '@/types/api';
import { Film, Tv, Search, CheckCircle2, AlertTriangle, Trash2 } from 'lucide-react';

export const Library: React.FC = () => {
  const { isAdmin } = useAuth();
  const [activeTab, setActiveTab] = useState<MediaType>('movie');
  const [statusFilter, setStatusFilter] = useState<'all' | 'available' | 'missing'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<MediaResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MediaResult | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadLibrary();
  }, [activeTab]);

  const loadLibrary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await mediaApi.getLibrary(activeTab);
      setItems(data);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const filteredItems = items.filter((item) => {
    // Status filter
    if (statusFilter === 'available' && !item.has_file && item.availability !== 'available') {
      return false;
    }
    if (statusFilter === 'missing' && (item.has_file || item.availability === 'available')) {
      return false;
    }

    // Text search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        item.title.toLowerCase().includes(q) ||
        (item.year && item.year.toString().includes(q))
      );
    }
    return true;
  });

  const formatSize = (bytes?: number | null) => {
    if (!bytes) return null;
    const gb = bytes / (1024 * 1024 * 1024);
    return `${gb.toFixed(1)} GB`;
  };

  const handleDeleteConfirm = async (deleteFiles?: boolean) => {
    if (!deleteTarget || deleteTarget.external_id == null) return;
    try {
      const result = await mediaApi.deleteLibraryItem(
        deleteTarget.media_type,
        deleteTarget.external_id,
        !!deleteFiles,
      );
      setItems((current) => current.filter((item) => item.external_id !== deleteTarget.external_id));
      const title = deleteTarget.title;
      setSuccessMessage(deleteFiles
        ? result.library_refresh_requested
          ? `${title} and its media files were removed. Your media library is refreshing.`
          : `${title} and its media files were removed. Your media player will update on its next scan.`
        : `${title} was removed from Radarr/Sonarr and Unifierr. Its files were kept, so it may still appear in Jellyfin or Plex.`);
      setDeleteTarget(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err : new Error('Could not remove this title from the library.'));
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Film className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Media Library
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Browse the movies and series indexed in your Radarr and Sonarr libraries.
          </p>
        </div>

        {/* Media Type Tabs */}
        <div className="inline-flex rounded-xl bg-slate-200/70 p-1 dark:bg-slate-800/80 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setActiveTab('movie')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTab === 'movie'
                ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            <Film className="h-3.5 w-3.5" /> Movies
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('series')}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              activeTab === 'series'
                ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
            }`}
          >
            <Tv className="h-3.5 w-3.5" /> TV Series
          </button>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={`Filter ${activeTab === 'movie' ? 'movies' : 'series'} in library...`}
            className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 pl-10 pr-4 py-2 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
          />
        </div>

        {/* Status Pills */}
        <div className="flex items-center gap-1.5 self-start sm:self-auto">
          {(['all', 'available', 'missing'] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold capitalize transition ${
                statusFilter === st
                  ? 'bg-brand-100 text-brand-800 dark:bg-brand-950/60 dark:text-brand-300'
                  : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />
      {successMessage && (
        <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
          {successMessage}
          <button type="button" onClick={() => setSuccessMessage(null)} className="ml-3 font-semibold underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <PosterSkeleton key={i} />
          ))}
        </div>
      ) : filteredItems.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {filteredItems.map((item, idx) => (
            <div
              key={`${item.media_type}-${item.external_id || idx}`}
              className="flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2.5 shadow-xs hover:border-slate-300 dark:hover:border-slate-700 transition"
            >
              <div className="relative aspect-[2/3] w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800">
                {item.poster_url ? (
                  <img
                    src={item.poster_url}
                    alt={item.title}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center p-3 text-center text-slate-400">
                    {activeTab === 'series' ? <Tv className="h-8 w-8 mb-1" /> : <Film className="h-8 w-8 mb-1" />}
                    <span className="text-[10px] font-medium line-clamp-2">{item.title}</span>
                  </div>
                )}

                {item.has_file ? (
                  <div className="absolute top-2 right-2 rounded-md bg-emerald-600/90 text-white p-1 shadow-sm">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  </div>
                ) : (
                  <div className="absolute top-2 right-2 rounded-md bg-amber-600/90 text-white p-1 shadow-sm">
                    <AlertTriangle className="h-3.5 w-3.5" />
                  </div>
                )}
              </div>

              <div className="mt-2.5 flex flex-1 flex-col justify-between space-y-2">
                <div>
                  <h3 className="text-xs font-bold text-slate-900 dark:text-white line-clamp-1 leading-tight" title={item.title}>
                    {item.title}
                  </h3>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 font-medium mt-0.5">
                    <span>{item.year || 'Unknown'}</span>
                    {formatSize(item.size_on_disk) && (
                      <span className="text-[10px]">{formatSize(item.size_on_disk)}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <AvailabilityBadge
                    status={item.has_file ? 'available' : item.availability || 'missing'}
                    size="sm"
                  />
                  {item.percent_complete !== undefined && item.percent_complete !== null && (
                    <span className="text-[10px] font-semibold text-slate-500">
                      {Math.round(item.percent_complete)}%
                    </span>
                  )}
                  {isAdmin && item.external_id != null && (
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(item)}
                      className="rounded-lg p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                      aria-label={`Remove ${item.title} from the library`}
                      title="Remove from library"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Film}
          title="No media in library"
          description={
            searchQuery
              ? `No library items match "${searchQuery}".`
              : `Your ${activeTab === 'movie' ? 'movies' : 'series'} collection is empty. Request items from Discover to build your library!`
          }
        />
      )}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        title={`Remove ${deleteTarget?.media_type === 'series' ? 'series' : 'movie'}?`}
        description={`This removes “${deleteTarget?.title ?? ''}” from ${deleteTarget?.media_type === 'series' ? 'Sonarr' : 'Radarr'} and clears its old Unifierr request record. Leave the box unchecked to keep media files. This does not remove download-client jobs or seeding data.`}
        confirmLabel="Remove from library"
        isDestructive
        checkboxLabel="Also delete media files managed by Radarr/Sonarr"
        defaultCheckboxState={false}
      />
    </div>
  );
};
