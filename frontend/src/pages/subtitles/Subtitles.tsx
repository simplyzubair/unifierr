import React, { useState, useEffect } from 'react';
import { subtitlesApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { TableSkeleton } from '@/components/common/Skeleton';
import { EmptyState } from '@/components/common/EmptyState';
import type { SubtitleWanted } from '@/types/api';
import { Subtitles as SubtitlesIcon, Search, Film, Tv, CheckCircle2, Globe } from 'lucide-react';

export const Subtitles: React.FC = () => {
  const [wantedList, setWantedList] = useState<SubtitleWanted[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchSuccess, setSearchSuccess] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    loadWanted();
  }, []);

  const loadWanted = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await subtitlesApi.getWanted();
      setWantedList(data);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchAllMissing = async () => {
    setSearching(true);
    setError(null);
    try {
      await subtitlesApi.searchMissing();
      setSearchSuccess(true);
      setTimeout(() => {
        setSearchSuccess(false);
        loadWanted();
      }, 3000);
    } catch (err: unknown) {
      setError(err as Error);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <SubtitlesIcon className="h-6 w-6 text-brand-600 dark:text-brand-400" />
            Subtitles & Bazarr
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Automatically finds missing subtitles for movies and episodes in your selected languages.
          </p>
        </div>

        <button
          type="button"
          onClick={handleSearchAllMissing}
          disabled={searching}
          className="flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white px-4 py-2.5 text-xs font-semibold shadow-xs transition self-start sm:self-auto disabled:opacity-50"
        >
          <Search className={`h-4 w-4 ${searching ? 'animate-spin' : ''}`} />
          {searching
            ? 'Searching Subtitles...'
            : searchSuccess
            ? 'Search Task Triggered!'
            : 'Search All Missing'}
        </button>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      {/* Wanted Subtitles List */}
      {loading ? (
        <TableSkeleton rows={4} />
      ) : wantedList.length > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold uppercase text-slate-500">
            <span>Missing Subtitles ({wantedList.length})</span>
          </div>

          {wantedList.map((item, idx) => (
            <div
              key={`${item.media_type}-${item.external_id}-${idx}`}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-xs"
            >
              <div className="flex items-start gap-3 min-w-0">
                <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 shrink-0 mt-0.5">
                  {item.media_type === 'series' ? <Tv className="h-4 w-4" /> : <Film className="h-4 w-4" />}
                </div>
                <div className="min-w-0">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">
                    {item.title}
                  </h3>
                  {item.episode && (
                    <div className="text-xs font-medium text-slate-500 mt-0.5">
                      {item.episode}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-auto">
                <span className="text-[11px] text-slate-400 font-medium mr-1 flex items-center gap-1">
                  <Globe className="h-3 w-3" /> Missing:
                </span>
                {item.missing_languages.map((lang) => (
                  <span
                    key={lang}
                    className="rounded-md bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 px-2 py-0.5 text-xs font-semibold uppercase"
                  >
                    {lang}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : error ? null : (
        <EmptyState
          icon={CheckCircle2}
          title="All subtitles found!"
          description="None of your movies or series are currently missing subtitles. Bazarr will keep checking automatically when new media arrives."
        />
      )}
    </div>
  );
};
