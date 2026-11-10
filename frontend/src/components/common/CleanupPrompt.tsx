import React, { useCallback, useEffect, useState } from 'react';
import { mediaApi } from '@/api';
import type { CleanupMovie } from '@/types/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import { Modal } from '@/components/common/Modal';

const SESSION_KEY = 'cleanup-prompt-dismissed';

export const CleanupPrompt: React.FC = () => {
  const [movies, setMovies] = useState<CleanupMovie[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem(SESSION_KEY) === '1'; } catch { return false; }
  });
  const load = useCallback(() => {
    void mediaApi.getCleanupDue().then((items) => { setMovies(items); setError(null); }).catch((err: Error) => setError(err));
  }, []);
  useEffect(load, [load]);
  const close = () => {
    try { sessionStorage.setItem(SESSION_KEY, '1'); } catch { /* Storage may be unavailable. */ }
    setDismissed(true);
  };
  const movie = movies[0];
  const respond = async (del: boolean) => {
    if (!movie) return;
    setBusy(true);
    setError(null);
    try {
      await mediaApi.answerCleanup(movie.external_id, del);
      setMovies((items) => items.slice(1));
    } catch (err) {
      setError(err as Error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal isOpen={!dismissed && (!!movie || !!error)} onClose={close} title="Delete this movie?" maxWidth="md">
      {error && <ErrorCard error={error} onRetry={load} />}
      {movie && (
        <div className="space-y-4">
          {movie.poster_url && <img src={movie.poster_url} alt={`${movie.title} poster`} className="mx-auto max-h-56 rounded-lg object-contain" />}
          <p className="text-sm text-slate-700 dark:text-slate-300">
            You watched “{movie.title}{movie.year ? ` (${movie.year})` : ''}”. It finished downloading {movie.days_since_download} days ago. Delete it to free up space?
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button type="button" disabled={busy} onClick={() => void respond(false)} className="rounded-lg px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800">No, keep it</button>
            <button type="button" disabled={busy} onClick={() => void respond(true)} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">Yes, delete it</button>
          </div>
          <p className="text-center text-xs text-slate-500">We’ll ask again in 90 days.</p>
        </div>
      )}
    </Modal>
  );
};
