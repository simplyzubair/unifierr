import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, Download, Loader2, RefreshCw, Smartphone } from 'lucide-react';
import { systemApi } from '@/api';
import { ErrorCard } from '@/components/common/ErrorCard';
import type { UpdateInfo } from '@/types/api';

const short = (revision?: string | null, id?: string) => (revision ? revision.slice(0, 7) : (id ?? '?'));
const POLL_MS = 3000;
const GIVE_UP_MS = 4 * 60 * 1000;

export const Updates: React.FC = () => {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState<'check' | 'apply' | null>(null);
  const [restarting, setRestarting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const startRef = useRef<{ id?: string; at: number } | null>(null);

  const load = useCallback(async () => {
    try {
      setInfo(await systemApi.getUpdate());
      setError(null);
    } catch (err) {
      if (!startRef.current) setError(err instanceof Error ? err : new Error('Could not load update status.'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // After "Update now" the server goes away for a moment. Keep asking until a different version answers.
  useEffect(() => {
    if (!restarting) return;
    const timer = setInterval(async () => {
      const start = startRef.current;
      if (!start) return;
      try {
        const next = await systemApi.getUpdate();
        const changed = next.current?.id !== start.id;
        const failed = !!next.last_result && !next.last_result.ok && Date.parse(next.last_result.at) > start.at;
        if (changed || failed || Date.now() - start.at > GIVE_UP_MS) {
          setInfo(next);
          setRestarting(false);
          startRef.current = null;
          setNotice(
            changed
              ? 'Updated. You are on the newest version.'
              : failed
                ? null
                : 'The update is taking longer than usual. Check again in a minute.',
          );
        }
      } catch {
        // expected while Unifierr restarts
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [restarting]);

  const check = async () => {
    setBusy('check');
    setNotice(null);
    try {
      const next = await systemApi.checkUpdate();
      setInfo(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not check for updates.'));
    } finally {
      setBusy(null);
    }
  };

  const apply = async () => {
    setBusy('apply');
    setNotice(null);
    try {
      const res = await systemApi.applyUpdate();
      if (res.started) {
        startRef.current = { id: info?.current?.id, at: Date.now() };
        setRestarting(true);
      } else {
        setNotice(res.message);
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not start the update.'));
    } finally {
      setBusy(null);
    }
  };

  const toggleAuto = async (on: boolean) => {
    try {
      setInfo(await systemApi.setAutoUpdate(on));
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Could not save this setting.'));
    }
  };

  const minutes = info ? Math.round(info.check_every_seconds / 60) : 15;
  const card = 'rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5';

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Updates</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Keep Unifierr up to date without downloading anything by hand.
        </p>
      </div>

      <ErrorCard error={error} onDismiss={() => setError(null)} />

      <section className={`${card} space-y-4`}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold text-slate-900 dark:text-white">Unifierr server</h2>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Version {info?.version ?? '…'}
              {info?.current && <> · build {short(info.current.revision, info.current.id)}</>}
            </p>
          </div>
          {info?.available && !restarting && (
            <span className="rounded-full bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300 px-2.5 py-1 text-xs font-semibold">
              New version
            </span>
          )}
        </div>

        {info && !info.supported && (
          <p
            role="note"
            className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900/60 dark:bg-sky-950/30 dark:text-sky-300"
          >
            {info.reason}
          </p>
        )}

        {info?.supported && (
          <>
            {restarting ? (
              <p role="status" className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <Loader2 className="h-4 w-4 animate-spin" /> Updating. Unifierr restarts in about a minute and this
                page reconnects by itself.
              </p>
            ) : info.available && info.latest ? (
              <p className="text-sm text-slate-700 dark:text-slate-300">
                Version <strong>{short(info.latest.revision, info.latest.id)}</strong> is ready (you have{' '}
                {short(info.current?.revision, info.current?.id)}). Downloads keep running; Unifierr itself is
                unavailable for a minute.
              </p>
            ) : (
              <p className="flex flex-wrap items-center gap-x-2 text-sm text-slate-700 dark:text-slate-300">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                {notice ?? (info.checked_at ? "You're up to date." : 'Not checked yet.')}
                {info.checked_at && (
                  <span className="text-slate-400">Checked {new Date(info.checked_at).toLocaleTimeString()}.</span>
                )}
              </p>
            )}

            {info.error && <p className="text-sm text-amber-700 dark:text-amber-300">{info.error}</p>}

            {info.last_result && !info.last_result.ok && !restarting && (
              <p
                role="note"
                className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
              >
                The last update did not work, so Unifierr went back to the version it had before. Nothing was lost.{' '}
                <span className="opacity-80">{info.last_result.message}</span>
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={check}
                disabled={busy !== null || restarting}
                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
              >
                <RefreshCw className={`h-4 w-4 ${busy === 'check' ? 'animate-spin' : ''}`} /> Check for updates
              </button>
              {info.available && (
                <button
                  type="button"
                  onClick={apply}
                  disabled={busy !== null || restarting}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white px-3 py-2 text-sm font-semibold disabled:opacity-50"
                >
                  <Download className="h-4 w-4" /> Update now
                </button>
              )}
            </div>

            <label className="flex items-start gap-3 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                checked={info.auto_update}
                onChange={(e) => void toggleAuto(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              <span>
                <span className="font-medium text-slate-900 dark:text-white">Update automatically</span>
                <span className="block text-slate-500 dark:text-slate-400">
                  Every {minutes} minutes Unifierr looks for a new version, installs it and restarts. If the new
                  version does not start properly, it goes back to the old one.
                </span>
              </span>
            </label>
          </>
        )}
      </section>

      <section className={`${card} space-y-2`}>
        <h2 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white">
          <Smartphone className="h-4 w-4" /> Phone, tablet and computer apps
        </h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          The apps show this same website. When the server updates, the apps get the new screens and fixes right away,
          with nothing to install. You only need a new app file for rare changes to the app itself.
        </p>
        {info?.download_url && (
          <a
            href={info.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline"
          >
            Open the app download page
          </a>
        )}
      </section>
    </div>
  );
};
