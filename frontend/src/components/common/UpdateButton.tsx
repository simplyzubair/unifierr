import React, { useEffect, useState } from 'react';
import { Download, Loader2, RefreshCw } from 'lucide-react';
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
 * Small icon next to the theme button. Admins: refresh icon checks for updates; it turns into a download icon
 * when a new server version is ready (one tap installs it and reloads). Inside the phone app it also turns into a
 * download icon when a newer app is out.
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

  const [checking, setChecking] = useState(false);
  const check = async () => {
    setChecking(true);
    setNote(null);
    try {
      const u = await systemApi.checkUpdate();
      setServerReady(!!u.available);
      setNote(u.available ? null : "You're up to date");
    } catch {
      setNote('Could not check right now');
    } finally {
      setChecking(false);
    }
  };

  const btn = 'relative p-1.5 rounded-lg transition disabled:opacity-70';
  const quiet = 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800';
  const ready = 'text-brand-600 bg-brand-50 hover:bg-brand-100 dark:text-brand-300 dark:bg-brand-950/60';
  const dot = <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-sky-500" aria-hidden="true" />;

  // Phone app has a newer version: a download icon that fetches it.
  if (appUrl && !(isAdmin && (serverReady || updating))) {
    return (
      <a href={appUrl} className={`${btn} ${ready}`} title="New app version: tap to download" aria-label="Download the new app version">
        <Download className="h-4 w-4" />
        {dot}
      </a>
    );
  }
  if (!isAdmin) return null;
  if (updating) {
    return (
      <span className={`${btn} ${ready}`} title="Updating… back in a minute" role="status" aria-label="Updating, back in a minute">
        <Loader2 className="h-4 w-4 animate-spin" />
      </span>
    );
  }
  if (serverReady) {
    return (
      <button type="button" onClick={updateServer} className={`${btn} ${ready}`} title="Update ready: tap to install" aria-label="Install the update">
        <Download className="h-4 w-4" />
        {dot}
      </button>
    );
  }
  return (
    <button type="button" onClick={check} disabled={checking} className={`${btn} ${quiet}`}
      title={note ?? 'Check for updates'} aria-label={note ?? 'Check for updates'}>
      <RefreshCw className={`h-4 w-4 ${checking ? 'animate-spin' : ''}`} />
    </button>
  );
};
