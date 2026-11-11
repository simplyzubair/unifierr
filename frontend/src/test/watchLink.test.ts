import { describe, expect, it } from 'vitest';
import { watchUrl } from '@/hooks/useWatchLink';

const ids = { server_id: 'srv', items: { 'movie:348': 'm1', 'series:74852': 's1', 'series:tmdb:99': 's2' } };
const base = 'http://nas:8096';

describe('open in Jellyfin', () => {
  it('links movies by TMDB id and shows by TVDB, then TMDB', () => {
    expect(watchUrl(ids, { media_type: 'movie', tmdb_id: 348 }, base)).toBe('http://nas:8096/web/#/details?id=m1&serverId=srv');
    expect(watchUrl(ids, { media_type: 'series', tvdb_id: 74852 }, base)).toContain('id=s1');
    expect(watchUrl(ids, { media_type: 'series', tmdb_id: 99 }, base)).toContain('id=s2');
  });

  it('gives no link for titles Jellyfin does not have yet', () => {
    expect(watchUrl(ids, { media_type: 'movie', tmdb_id: 1 }, base)).toBeNull();
    expect(watchUrl({}, { media_type: 'movie', tmdb_id: 348 }, base)).toBeNull();
  });
});
