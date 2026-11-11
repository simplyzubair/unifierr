import React, { useEffect, useState } from 'react';
import { ArrowUpCircle } from 'lucide-react';
import { systemApi } from '@/api';

// The Android app adds "UnifierrApp/<version>" to its browser name (client/android/MainActivity.kt).
export const appVersion = (userAgent: string) => userAgent.match(/UnifierrApp\/(\d+\.\d+\.\d+)/)?.[1] ?? null;

export const isNewer = (latest: string, current: string) => {
  const a = latest.split('.').map(Number);
  const b = current.split('.').map(Number);
  for (let i = 0; i < 3; i += 1) if (a[i] !== b[i]) return a[i] > b[i];
  return false;
};

/** Small "Update" button, bottom left, shown only inside the phone app when a newer app is out. */
export const AppUpdateButton: React.FC = () => {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const current = appVersion(navigator.userAgent);
    if (!current) return;
    systemApi.getClientLatest().then(
      (latest) => {
        if (latest.version && latest.android_url && isNewer(latest.version, current)) setUrl(latest.android_url);
      },
      () => undefined,
    );
  }, []);

  if (!url) return null;
  return (
    <a
      href={url}
      className="fixed left-3 bottom-20 md:bottom-4 z-30 flex items-center gap-1.5 rounded-full bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white shadow-lg"
    >
      <ArrowUpCircle className="h-4 w-4" aria-hidden="true" />
      Update app
    </a>
  );
};
