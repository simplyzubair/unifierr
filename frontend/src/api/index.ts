import { apiClient } from './client';
import type {
  User,
  SetupStatus,
  EnvironmentReport,
  DetectedApp,
  FolderReport,
  ServiceKind,
  ServiceOut,
  Job,
  MediaResult,
  MediaItem,
  RequestOut,
  RequestPreflight,
  DownloadsResponse,
  Indexer,
  IndexerSchema,
  SubtitleWanted,
  StorageResponse,
  HealthOverview,
  EventItem,
  SystemSettings,
  UpdateInfo,
  SystemSettingsUpdate,
  MediaType,
  CleanupMovie,
} from '@/types/api';

export * from './client';

// ---------------- AUTH & USERS ----------------

export const authApi = {
  bootstrap: (data: { username: string; password: string }) =>
    apiClient<User>('/api/auth/bootstrap', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuthRedirect: true,
    }),

  login: (data: { username: string; password: string }) =>
    apiClient<User>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuthRedirect: true,
    }),

  logout: () =>
    apiClient<void>('/api/auth/logout', {
      method: 'POST',
    }),

  me: () =>
    apiClient<User>('/api/auth/me', {
      method: 'GET',
      skipAuthRedirect: true,
    }),

  changePassword: (data: { current_password: string; new_password: string }) =>
    apiClient<void>('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getUsers: () =>
    apiClient<User[]>('/api/users', {
      method: 'GET',
    }),

  createUser: (data: { username: string; password: string; role: 'admin' | 'user' }) =>
    apiClient<User>('/api/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteUser: (id: number) =>
    apiClient<void>(`/api/users/${id}`, {
      method: 'DELETE',
    }),
};

// ---------------- SETUP WIZARD ----------------

export const setupApi = {
  getStatus: () =>
    apiClient<SetupStatus>('/api/setup/status', {
      method: 'GET',
      skipAuthRedirect: true,
    }),

  getEnvironment: () =>
    apiClient<EnvironmentReport>('/api/setup/environment', {
      method: 'GET',
    }),

  detectApps: () =>
    apiClient<DetectedApp[]>('/api/setup/detect', {
      method: 'GET',
    }),

  prepareFolders: (data: { root: string; puid: number; pgid: number; timezone: string }) =>
    apiClient<FolderReport>('/api/setup/folders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  install: (kinds: ServiceKind[]) =>
    apiClient<{ job_id: string }>('/api/setup/install', {
      method: 'POST',
      body: JSON.stringify({ kinds }),
    }),

  adopt: (data: {
    kind: ServiceKind;
    name?: string;
    base_url?: string;
    api_key?: string;
    username?: string;
    password?: string;
  }) =>
    apiClient<ServiceOut>('/api/setup/adopt', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  wire: () =>
    apiClient<{ job_id: string }>('/api/setup/wire', {
      method: 'POST',
    }),

  complete: () =>
    apiClient<{ status: string }>('/api/setup/complete', {
      method: 'POST',
    }),
};

// ---------------- JOBS ----------------

export const jobsApi = {
  getJob: (id: string) =>
    apiClient<Job>(`/api/jobs/${id}`, {
      method: 'GET',
    }),
};

// ---------------- SERVICES ----------------

export const servicesApi = {
  getServices: () =>
    apiClient<ServiceOut[]>('/api/services', {
      method: 'GET',
    }),

  testService: (id: number) =>
    apiClient<ServiceOut>(`/api/services/${id}/test`, {
      method: 'POST',
    }),

  getCredentials: (id: number) =>
    apiClient<{ username: string | null; password: string | null }>(`/api/services/${id}/credentials`, {
      method: 'GET',
    }),

  updateService: (
    id: number,
    data: {
      base_url?: string;
      api_key?: string;
      username?: string;
      password?: string;
      enabled?: boolean;
    }
  ) =>
    apiClient<ServiceOut>(`/api/services/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteService: (id: number) =>
    apiClient<void>(`/api/services/${id}`, {
      method: 'DELETE',
    }),

  restartService: (id: number) =>
    apiClient<void>(`/api/services/${id}/restart`, {
      method: 'POST',
    }),

  updateImage: (id: number) =>
    apiClient<{ job_id: string }>(`/api/services/${id}/update`, {
      method: 'POST',
    }),

  getLogs: (id: number, tail: number = 200) =>
    apiClient<{ logs: string }>(`/api/services/${id}/logs`, {
      method: 'GET',
      params: { tail },
    }),
};

// ---------------- MEDIA & REQUESTS ----------------

export const mediaApi = {
  getWatchLinks: () =>
    apiClient<{ server_id?: string; items?: Record<string, string> }>('/api/media/watch-links', { method: 'GET' }),
  getCleanupDue: () => apiClient<CleanupMovie[]>('/api/media/cleanup', { method: 'GET' }),
  answerCleanup: (id: number, del: boolean) => apiClient<{ ok: boolean }>(`/api/media/cleanup/${id}`, {
    method: 'POST', body: JSON.stringify({ delete: del }),
  }),
  search: (q: string, type: 'movie' | 'series' | 'all' = 'all') =>
    apiClient<MediaResult[]>('/api/media/search', {
      method: 'GET',
      params: { q, type },
    }),

  getLibrary: (type: 'movie' | 'series' = 'movie') =>
    apiClient<MediaResult[]>('/api/media/library', {
      method: 'GET',
      params: { type },
    }),

  deleteLibraryItem: (type: 'movie' | 'series', externalId: number, deleteFiles: boolean) =>
    apiClient<{ removed: boolean; library_refresh_requested: boolean }>(
      `/api/media/library/${type}/${externalId}`,
      {
        method: 'DELETE',
        body: JSON.stringify({ confirm: true, delete_files: deleteFiles }),
      },
    ),

  getRecent: () =>
    apiClient<MediaItem[]>('/api/media/recent', {
      method: 'GET',
    }),
};

export const requestsApi = {
  getRequests: (status?: string) =>
    apiClient<RequestOut[]>('/api/requests', {
      method: 'GET',
      params: { status },
    }),

  preflight: (data: {
    media_type: MediaType;
    tmdb_id?: number | null;
    tvdb_id?: number | null;
    title: string;
    year?: number | null;
    poster_url?: string | null;
  }) =>
    apiClient<RequestPreflight>('/api/requests/preflight', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  createRequest: (data: {
    media_type: MediaType;
    tmdb_id?: number | null;
    tvdb_id?: number | null;
    title: string;
    year?: number | null;
    poster_url?: string | null;
  }) =>
    apiClient<RequestOut>('/api/requests', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  approve: (id: number, note?: string) =>
    apiClient<RequestOut>(`/api/requests/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  deny: (id: number, note?: string) =>
    apiClient<RequestOut>(`/api/requests/${id}/deny`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  deleteRequest: (id: number) =>
    apiClient<void>(`/api/requests/${id}`, {
      method: 'DELETE',
    }),
};

// ---------------- DOWNLOADS ----------------

export const downloadsApi = {
  getDownloads: () =>
    apiClient<DownloadsResponse>('/api/downloads', {
      method: 'GET',
    }),

  pause: (id: string) =>
    apiClient<void>(`/api/downloads/${id}/pause`, {
      method: 'POST',
    }),

  resume: (id: string) =>
    apiClient<void>(`/api/downloads/${id}/resume`, {
      method: 'POST',
    }),

  deleteDownload: (id: string, deleteFiles: boolean = false) =>
    apiClient<void>(`/api/downloads/${id}`, {
      method: 'DELETE',
      params: { delete_files: deleteFiles },
    }),
};

// ---------------- INDEXERS ----------------

export const indexersApi = {
  getIndexers: () =>
    apiClient<Indexer[]>('/api/indexers', {
      method: 'GET',
    }),

  getSchemas: () =>
    apiClient<IndexerSchema[]>('/api/indexers/schemas', {
      method: 'GET',
    }),

  createIndexer: (data: { definition_name: string; fields?: Record<string, unknown> }) =>
    apiClient<Indexer>('/api/indexers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteIndexer: (id: number) =>
    apiClient<void>(`/api/indexers/${id}`, {
      method: 'DELETE',
    }),

  setEnabled: (id: number, enabled: boolean) =>
    apiClient<Indexer>(`/api/indexers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),

  testAll: () =>
    apiClient<Array<{ id: number; isValid: boolean; errors?: string[] }>>('/api/indexers/test', {
      method: 'POST',
    }),
};

// ---------------- SUBTITLES ----------------

export const subtitlesApi = {
  getWanted: () =>
    apiClient<SubtitleWanted[]>('/api/subtitles/wanted', {
      method: 'GET',
    }),

  searchMissing: () =>
    apiClient<void>('/api/subtitles/search', {
      method: 'POST',
    }),
};

// ---------------- STORAGE & HEALTH & EVENTS ----------------

export const storageApi = {
  getStorage: () =>
    apiClient<StorageResponse>('/api/storage', {
      method: 'GET',
    }),
};

export const healthApi = {
  getOverview: () =>
    apiClient<HealthOverview>('/api/health/overview', {
      method: 'GET',
    }),
};

export const eventsApi = {
  getEvents: (limit: number = 100) =>
    apiClient<EventItem[]>('/api/events', {
      method: 'GET',
      params: { limit },
    }),
};

// ---------------- SYSTEM SETTINGS & BACKUP ----------------

export const systemApi = {
  getSettings: () =>
    apiClient<SystemSettings>('/api/settings', {
      method: 'GET',
    }),

  updateSettings: (data: SystemSettingsUpdate) =>
    apiClient<SystemSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getUpdate: () => apiClient<UpdateInfo>('/api/system/update', { method: 'GET' }),

  getVersion: () => apiClient<{ version: string; build?: string }>('/api/health', { method: 'GET' }),

  getClientLatest: () =>
    apiClient<{ version?: string; android_url?: string }>('/api/client/latest', { method: 'GET' }),

  checkUpdate: () => apiClient<UpdateInfo>('/api/system/update/check', { method: 'POST' }),

  applyUpdate: () =>
    apiClient<{ started: boolean; message: string }>('/api/system/update/apply', { method: 'POST' }),

  setAutoUpdate: (auto_update: boolean) =>
    apiClient<UpdateInfo>('/api/system/update/settings', {
      method: 'PUT',
      body: JSON.stringify({ auto_update }),
    }),

  getBackup: () =>
    apiClient<Blob>('/api/system/backup', {
      method: 'GET',
    }),

  restoreBackup: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient<void>('/api/system/restore', {
      method: 'POST',
      body: formData,
    });
  },
};
