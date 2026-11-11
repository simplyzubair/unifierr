import React, { useEffect, useState } from 'react';
import { ArrowUpCircle, Loader2 } from 'lucide-react';
import { systemApi } from '@/api';

// The Android app adds "UnifierrApp/<version>" to its browser name (client/android/MainActivity.kt).
export const appVersion = (userAgent: string) => userAgent.match(/UnifierrApp\/(\d+\.\d+\.\d+)/)?.[1] ?? null;

export const isNewer = (latest: string, current: string) => {
  const a = latest.split('.').map(Number);
  const b = current.split('.').map(Number);
  for (let i = 0; i < 3; i += 1) if (a[i] !== b[i]) return a[i] > b[i];
  return false;
};

const CHECK_MS = 10 * 60 * 1000;
const POLL_MS = 4000;
const GIVE_UP_MS = 5 * 60 * 1000;

/**
 * One small button, bottom left, only when something new is ready:
 * - admins: a newer Unifierr server -> one tap installs it and reloads the page;
 * - inside the phone app: a newer app -> one tap downloads it.
 */
export const UpdateButton: React.FC<{ isAdmin: boolean }> = ({ isAdmin }) => {
  const [serverReady, setServerReady] = useState(false);
  const [appUrl, setAppUrl] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    const look = () => systemApi.getUpdate().then((u) => setServerReady(!!u.available), () => undefined);
    void look();
    const timer = setInterval(look, CHECK_MS);
    return () => clearInterval(timer);
  }, [isAdmin]);

  useEffect(() => {
    const current = appVersion(navigator.userAgent);
    if (!current) return;
    systemApi.getClientLatest().then(
      (latest) => {
        if (latest.version && latest.android_url && isNewer(latest.version, current)) setAppUrl(latest.android_url);
      },
      () => undefined,
    );
  }, []);

  const updateServer = async () => {
    setUpdating(true);
    setNote(null);
    try {
      const before = (await systemApi.getUpdate()).current?.id;
      const res = await systemApi.applyUpdate();
      if (!res.started) {
        setUpdating(false);
        setNote(res.message);
        return;
      }
      const startedAt = Date.now();
      // Unifierr restarts for a minute; keep asking until the new version answers, then load its new screens.
      const timer = setInterval(async () => {
        try {
          const now = await systemApi.getUpdate();
          if (now.current?.id !== before) {
            clearInterval(timer);
            window.location.reload();
          }
        } catch {
          // expected while it restarts
        }
        if (Date.now() - startedAt > GIVE_UP_MS) {
          clearInterval(timer);
          setUpdating(false);
          setNote('Taking longer than usual. It will finish on its own.');
        }
      }, POLL_MS);
    } catch {
      setUpdating(false);
      setNote('Could not start the update. Try again in a minute.');
    }
  };

  const place = 'fixed left-3 bottom-20 md:left-[17rem] md:bottom-4 z-30';
  const pill =
    'flex items-center gap-1.5 rounded-full bg-brand-600 hover:bg-brand-500 px-3 py-1.5 text-xs font-semibold text-white shadow-lg disabled:opacity-80';

  if (isAdmin && (serverReady || updating)) {
    return (
      <div className={`${place} flex flex-col items-start gap-1`}>
        {note && <span className="rounded-lg bg-slate-900/90 px-2 py-1 text-[11px] text-slate-200">{note}</span>}
        <button type="button" onClick={updateServer} disabled={updating} className={pill}>
          {updating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ArrowUpCircle className="h-4 w-4" aria-hidden="true" />}
          {updating ? 'Updating… back in a minute' : 'Update'}
        </button>
      </div>
    );
  }
  if (appUrl) {
    return (
      <a href={appUrl} className={`${place} ${pill}`}>
        <ArrowUpCircle className="h-4 w-4" aria-hidden="true" />
        Update app
      </a>
    );
  }
  return null;
};
