import React, { useState, useEffect, useTransition } from 'react';
import { mediaApi, requestsApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { AvailabilityBadge } from '@/components/common/Badge';
import { PosterSkeleton } from '@/components/common/Skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import { Modal } from '@/components/common/Modal';
import type { MediaResult, MediaItem } from '@/types/api';
import {
  Search,
  Film,
  Tv,
  Sparkles,
  Check,
  Plus,
  Compass,
  Image as ImageIcon,
} from 'lucide-react';

export const Discover: React.FC = () => {
  const [query, setQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'movie' | 'series'>('all');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [isPending, startTransition] = useTransition();

  const [results, setResults] = useState<MediaResult[]>([]);
  const [recentMedia, setRecentMedia] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Request modal
  const [selectedItem, setSelectedItem] = useState<MediaResult | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState(false);

  // Debounce query
  useEffect(() => {
    const handler = setTimeout(() => {
      startTransition(() => {
        setDebouncedQuery(query.trim());
      });
    }, 400);
    return () => clearTimeout(handler);
  }, [query]);

  // Load recently added on initial mount
  useEffect(() => {
    const loadRecent = async () => {
      try {
        const recent = await mediaApi.getRecent();
        setRecentMedia(recent);
      } catch {
        // Best effort
      }
    };
    loadRecent();
  }, []);

  // Search when debounced query or filter changes
  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      return;
    }

    const performSearch = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await mediaApi.search(debouncedQuery, filterType);
        setResults(data);
      } catch (err: unknown) {
        setError(err as Error);
      } finally {
        setLoading(false);
      }
    };

    performSearch();
  }, [debouncedQuery, filterType]);

  const handleRequest = async (item: MediaResult) => {
    setRequesting(true);
    setError(null);
    try {
      await requestsApi.createRequest({
        media_type: item.media_type,
        tmdb_id: item.tmdb_id,
        tvdb_id: item.tvdb_id,
        title: item.title,
        year: item.year,
        poster_url: item.poster_url,
      });

      setRequestSuccess(true);
      // Update item in results
      setResults((prev) =>
        prev.map((r) =>
          r.title === item.title && r.year === item.year
            ? { ...r, availability: 'requested' }
            : r
        )
      );

      setTimeout(() => {
        setSelectedItem(null);
        setRequestSuccess(false);
      }, 1200);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setRequesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Compass className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Discover Media
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Find movies and TV shows, check their library status, or request downloads with one click.
          </p>
        </div>

        {/* Filter Type Tabs */}
        <div className="inline-flex rounded-xl bg-slate-200/70 p-1 dark:bg-slate-800/80 self-start sm:self-auto">
          {(['all', 'movie', 'series'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFilterType(t)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition ${
                filterType === t
                  ? 'bg-white text-brand-700 shadow-xs dark:bg-slate-900 dark:text-brand-300'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
              }`}
            >
              {t === 'series' ? 'TV Shows' : t === 'movie' ? 'Movies' : 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Search Input Box */}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400">
          <Search className="h-5 w-5" />
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search for movies or TV shows by title..."
          className="w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 pl-11 pr-4 py-3 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition"
        />
        {isPending && (
          <div className="absolute inset-y-0 right-0 pr-4 flex items-center text-xs text-slate-400 font-medium">
            Searching...
          </div>
        )}
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* Search Results Grid */}
      {loading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <PosterSkeleton key={i} />
          ))}
        </div>
      ) : debouncedQuery ? (
        results.length > 0 ? (
          <div className="space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Found {results.length} results
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {results.map((item, idx) => (
                <MediaCard
                  key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || idx}`}
                  item={item}
                  onRequestClick={() => setSelectedItem(item)}
                />
              ))}
            </div>
          </div>
        ) : (
          <EmptyState
            icon={Search}
            title={`No results found for "${debouncedQuery}"`}
            description="Check the spelling or try searching for another movie or TV show title."
          />
        )
      ) : (
        /* Empty State: Recently Added Media from Server */
        <div className="space-y-4 pt-2">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-white">
            <Sparkles className="h-4 w-4 text-amber-500" />
            Recently Added to Your Media Server
          </div>

          {recentMedia.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {recentMedia.map((item, idx) => (
                <MediaCard
                  key={`${item.media_type}-${item.tmdb_id || item.tvdb_id || idx}`}
                  item={{ ...item, availability: 'available' }}
                  onRequestClick={() => {}}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Sparkles}
              title="Start discovering media"
              description="Type a movie or TV show title in the search box above to request new content."
            />
          )}
        </div>
      )}

      {/* Request Confirmation Modal */}
      <Modal
        isOpen={!!selectedItem}
        onClose={() => {
          if (!requesting) setSelectedItem(null);
        }}
        title={`Request "${selectedItem?.title}"`}
        description={`Add this ${selectedItem?.media_type === 'series' ? 'TV show' : 'movie'} to your collection.`}
      >
        {selectedItem && (
          <div className="space-y-4">
            <div className="flex gap-4">
              <div className="w-24 shrink-0 rounded-lg overflow-hidden bg-slate-100 dark:bg-slate-800 aspect-[2/3]">
                {selectedItem.poster_url ? (
                  <img
                    src={selectedItem.poster_url}
                    alt={selectedItem.title}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-400">
                    <ImageIcon className="h-6 w-6" />
                  </div>
                )}
              </div>
              <div className="space-y-1.5 flex-1 text-xs">
                <div className="text-sm font-bold text-slate-900 dark:text-white">
                  {selectedItem.title} {selectedItem.year && `(${selectedItem.year})`}
                </div>
                <div className="capitalize font-semibold text-brand-600 dark:text-brand-400">
                  {selectedItem.media_type === 'series' ? 'TV Series' : 'Movie'}
                </div>
                <p className="text-slate-500 line-clamp-4 leading-relaxed">
                  {selectedItem.overview || 'No overview provided.'}
                </p>
              </div>
            </div>

            <div className="rounded-xl bg-slate-50 dark:bg-slate-950 p-3 text-xs text-slate-600 dark:text-slate-400">
              Your request will be processed immediately. Once an indexer finds a suitable release, download will begin automatically.
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setSelectedItem(null)}
                disabled={requesting}
                className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleRequest(selectedItem)}
                disabled={requesting}
                className="flex items-center gap-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold py-2 px-5 shadow-sm transition disabled:opacity-50"
              >
                {requestSuccess ? (
                  <>
                    <Check className="h-4 w-4 text-white" /> Requested!
                  </>
                ) : requesting ? (
                  'Requesting...'
                ) : (
                  <>
                    <Plus className="h-4 w-4" /> Confirm Request
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};

// Reusable Media Card
const MediaCard: React.FC<{
  item: MediaResult;
  onRequestClick: () => void;
}> = ({ item, onRequestClick }) => {
  const [imageError, setImageError] = useState(false);

  return (
    <div className="group flex flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2.5 shadow-xs hover:shadow-md transition-all duration-200">
      {/* Poster Image */}
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800">
        {item.poster_url && !imageError ? (
          <img
            src={item.poster_url}
            alt={item.title}
            loading="lazy"
            onError={() => setImageError(true)}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center p-3 text-center text-slate-400">
            {item.media_type === 'series' ? <Tv className="h-8 w-8 mb-1" /> : <Film className="h-8 w-8 mb-1" />}
            <span className="text-[10px] font-medium leading-tight line-clamp-2">{item.title}</span>
          </div>
        )}

        {/* Media type tag top-left */}
        <div className="absolute top-2 left-2 rounded-md bg-slate-900/80 backdrop-blur-xs px-1.5 py-0.5 text-[9px] font-bold text-white uppercase tracking-wider">
          {item.media_type === 'series' ? 'TV' : 'Movie'}
        </div>
      </div>

      {/* Info & Action */}
      <div className="mt-2.5 flex flex-1 flex-col justify-between space-y-2">
        <div>
          <h3 className="text-xs font-bold text-slate-900 dark:text-white line-clamp-1 leading-tight" title={item.title}>
            {item.title}
          </h3>
          <span className="text-[11px] text-slate-500 font-medium">
            {item.year || 'Unknown year'}
          </span>
        </div>

        <div className="pt-1">
          {item.availability === 'not_added' || item.availability === 'missing' ? (
            <button
              type="button"
              onClick={onRequestClick}
              className="w-full flex items-center justify-center gap-1.5 rounded-lg bg-brand-50 hover:bg-brand-100 dark:bg-brand-950/60 dark:hover:bg-brand-900/60 text-brand-700 dark:text-brand-300 py-1.5 text-xs font-semibold transition"
            >
              <Plus className="h-3.5 w-3.5" /> Request
            </button>
          ) : (
            <div className="flex justify-start">
              <AvailabilityBadge status={item.availability} size="sm" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
