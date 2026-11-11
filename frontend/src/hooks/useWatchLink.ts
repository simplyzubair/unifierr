import { useEffect, useState } from 'react';
import { mediaApi } from '@/api';

interface WatchIds {
  server_id?: string;
  items?: Record<string, string>;
}

interface Titled {
  media_type: 'movie' | 'series';
  tmdb_id?: number | null;
  tvdb_id?: number | null;
}

// Jellyfin answers on the same NAS name you open Unifierr with (Tailscale or home network), on its own port.
// shortcut: assumes Jellyfin's default port 8096 on the same host; add a "Jellyfin address" setting if that ever differs.
export const jellyfinBase = (hostname: string) => `http://${hostname}:8096`;

export const watchUrl = (ids: WatchIds, item: Titled, base: string): string | null => {
  const map = ids.items ?? {};
  const id =
    item.media_type === 'movie'
      ? item.tmdb_id && map[`movie:${item.tmdb_id}`]
      : (item.tvdb_id && map[`series:${item.tvdb_id}`]) || (item.tmdb_id && map[`series:tmdb:${item.tmdb_id}`]);
  if (!id || !ids.server_id) return null;
  return `${base}/web/#/details?id=${encodeURIComponent(id)}&serverId=${encodeURIComponent(ids.server_id)}`;
};

/** Returns a function that gives the "open in Jellyfin" address for a title, or null when it is not in Jellyfin. */
export const useWatchLink = () => {
  const [ids, setIds] = useState<WatchIds>({});
  useEffect(() => {
    mediaApi.getWatchLinks().then(setIds, () => undefined);
  }, []);
  const base = jellyfinBase(window.location.hostname);
  return (item: Titled) => watchUrl(ids, item, base);
};
