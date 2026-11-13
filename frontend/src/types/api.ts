// Normalized models matching backend/app/adapters/base.py and docs/CONTRACTS.md

export type ServiceKind =
  | 'radarr'
  | 'sonarr'
  | 'prowlarr'
  | 'qbittorrent'
  | 'sabnzbd'
  | 'nzbget'
  | 'bazarr'
  | 'jellyfin'
  | 'plex'
  | 'gluetun'
  | 'unmanic';

export type Severity = 'info' | 'warning' | 'error';

export interface HealthIssue {
  severity: Severity;
  message: string;
  explanation?: string | null;
  fix?: string | null;
  source?: string | null;
}

export interface HealthStatus {
  ok: boolean;
  version?: string | null;
  message: string;
  issues?: HealthIssue[];
}

export type MediaType = 'movie' | 'series';

export interface MediaItem {
  media_type: MediaType;
  title: string;
  year?: number | null;
  overview?: string | null;
  poster_url?: string | null;
  tmdb_id?: number | null;
  tvdb_id?: number | null;
  imdb_id?: string | null;
  external_id?: number | null;
  in_library?: boolean;
  monitored?: boolean;
  has_file?: boolean;
  percent_complete?: number | null;
  size_on_disk?: number | null;
  status?: string | null;
}
export interface CleanupMovie {
  external_id: number;
  tmdb_id: number;
  title: string;
  year?: number | null;
  poster_url?: string | null;
  downloaded_at: string;
  days_since_download: number;
}

export type QueueState =
  | 'downloading'
  | 'seeding'
  | 'paused'
  | 'queued'
  | 'stalled'
  | 'checking'
  | 'completed'
  | 'importing'
  | 'error'
  | 'unknown';

export interface QueueItem {
  id: string; // torrent hash or <source>:<queue id>
  name: string;
  source: 'qbittorrent' | 'sabnzbd' | 'nzbget' | 'radarr' | 'sonarr';
  state: QueueState;
  progress: number; // 0..100
  size?: number | null; // bytes
  downloaded?: number | null;
  download_speed?: number | null; // bytes/s
  upload_speed?: number | null;
  eta_seconds?: number | null;
  category?: string | null;
  save_path?: string | null;
  media_title?: string | null;
  media_type?: MediaType | null;
  error?: string | null;
}

export interface Indexer {
  id: number;
  name: string;
  protocol: string; // torrent | usenet
  enabled: boolean;
  privacy?: string | null; // public | private | semiPrivate
  implementation?: string | null;
  status?: string | null;
}

export interface IndexerSchemaField {
  name: string;
  label: string;
  type: string;
  value?: unknown;
  advanced?: boolean;
  helpText?: string;
  selectOptions?: { value: string | number; name: string }[];
}

export interface IndexerSchema {
  name: string; // definition name e.g. "1337x"
  implementation: string;
  protocol: string;
  privacy?: string | null;
  description?: string | null;
  language?: string | null;
  required_fields?: IndexerSchemaField[];
}

export interface LibraryInfo {
  id: string;
  name: string;
  type: string; // movies | tvshows
  paths?: string[];
}

export interface DiskSpace {
  path: string;
  label?: string | null;
  free_bytes: number;
  total_bytes: number;
}

export interface SubtitleWanted {
  media_type: MediaType;
  title: string;
  episode?: string | null;
  missing_languages: string[];
  external_id: number;
}

// Setup & Deployment Models
export type PlatformType =
  | 'synology'
  | 'unraid'
  | 'truenas'
  | 'linux'
  | 'windows'
  | 'macos'
  | 'unknown';

export interface EnvironmentReport {
  platform: PlatformType;
  in_container: boolean;
  docker_available: boolean;
  docker_version?: string | null;
  docker_error?: string | null;
  suggested_root: string;
  puid: number;
  pgid: number;
  timezone: string;
  notes: string[];
}

export interface DetectedApp {
  kind: ServiceKind;
  source: 'docker' | 'network';
  container_name?: string | null;
  image?: string | null;
  url_candidates: string[];
  reachable_url?: string | null;
  config_path?: string | null;
  api_key_found: boolean;
  managed: boolean;
}

export interface FolderReport {
  root: string;
  created: string[];
  existing: string[];
  writable: boolean;
  same_filesystem: boolean;
  free_bytes: number;
  total_bytes: number;
  problems: HealthIssue[];
}

export type StepStatus = 'pending' | 'running' | 'ok' | 'skipped' | 'failed';

export interface JobStep {
  name: string;
  status: StepStatus;
  message?: string | null;
  explanation?: string | null;
  fix?: string | null;
}

export interface Job {
  id: string;
  kind: string;
  status: 'running' | 'done' | 'failed';
  steps: JobStep[];
  log: string[];
  result?: unknown;
  started_at?: string;
  finished_at?: string | null;
}

// Auth & Users
export type UserRole = 'admin' | 'user';

export interface User {
  id: number;
  username: string;
  role: UserRole;
  created_at?: string;
}

export interface SetupStatus {
  has_admin: boolean;
  setup_complete: boolean;
  docker_available: boolean;
  version: string;
}

// Services
export interface ServiceOut {
  id: number;
  kind: ServiceKind;
  name: string;
  base_url: string;
  managed: boolean;
  container_name?: string | null;
  enabled: boolean;
  has_api_key: boolean;
  has_login: boolean;
  status: HealthStatus | null;
}

// Requests & Media
export type MediaAvailability =
  | 'available'
  | 'downloading'
  | 'requested'
  | 'missing'
  | 'not_added';

export interface RequestOut {
  id: number;
  media_type: MediaType;
  tmdb_id?: number | null;
  tvdb_id?: number | null;
  title: string;
  year?: number | null;
  poster_url?: string | null;
  status: 'pending' | 'approved' | 'denied' | 'failed';
  stage: 'pending_review' | 'denied' | 'needs_attention' | 'unknown' | 'searching' | 'downloading' | 'importing' | 'waiting_for_library' | 'available';
  stage_message: string;
  availability?: MediaAvailability;
  requested_by?: string | null;
  created_at?: string;
  note?: string | null;
}

export type PreflightVerdict = 'ready' | 'warning' | 'blocked';
export interface RequestPreflight {
  verdict: PreflightVerdict;
  checks: Array<{
    name: string;
    status: PreflightVerdict;
    message: string;
    fix: string;
  }>;
}

export interface MediaResult extends MediaItem {
  request?: RequestOut | null;
  availability: MediaAvailability;
}

// Downloads response
export interface DownloadsResponse {
  items: QueueItem[];
  dl_speed?: number | null; // bytes/s
  up_speed?: number | null; // bytes/s
  updated_at?: string;
}

// Health overview response
export interface HealthOverview {
  overall: 'ok' | 'warning' | 'error';
  services: Array<{
    kind: ServiceKind;
    name: string;
    status: HealthStatus;
  }>;
  issues: HealthIssue[];
}

// Storage response
export interface StorageResponse {
  folders: FolderReport | null;
  disks: DiskSpace[];
}

// System events
export interface EventItem {
  id: number;
  ts: string;
  level: 'info' | 'warning' | 'error';
  source: string;
  message: string;
  details?: unknown;
}

// Settings
export interface SystemSettings {
  root: string;
  puid: number;
  pgid: number;
  timezone: string;
  movies_path?: string;
  tv_path?: string;
  downloads_path?: string;
  language?: string;
  vpn_enabled?: boolean;
  vpn_provider?: string;
  vpn_type?: 'openvpn' | 'wireguard';
  vpn_server_countries?: string;
  vpn_has_openvpn_credentials?: boolean;
  vpn_has_wireguard_key?: boolean;
  plex_claim_saved?: boolean;
  download_client?: 'qbittorrent' | 'sabnzbd' | 'nzbget' | null;
  trash_profiles?: boolean;
  trash_profile?: string | null;
  cleanup_review_days?: 0 | 30 | 90 | 180;
  download_start_hour?: number;
  download_end_hour?: number;
  ntfy_url?: string;
}

export interface SystemSettingsUpdate {
  timezone?: string;
  language?: string;
  puid?: number;
  pgid?: number;
  vpn_enabled?: boolean;
  vpn_provider?: string;
  vpn_type?: 'openvpn' | 'wireguard';
  vpn_server_countries?: string;
  vpn_username?: string;
  vpn_password?: string;
  wireguard_private_key?: string;
  plex_claim?: string;
  download_client?: 'qbittorrent' | 'sabnzbd' | 'nzbget';
  trash_profiles?: boolean;
  trash_profile?: string;
  cleanup_review_days?: 0 | 30 | 90 | 180;
  download_start_hour?: number;
  download_end_hour?: number;
  ntfy_url?: string;
}

// API Error Shape
export interface UnifierrApiError {
  error?: string;
  message?: string;
  detail?: string | Array<{ msg: string; loc?: (string | number)[] }>;
  explanation?: string | null;
  fix?: string | null;
}

export interface UpdateImageInfo {
  id: string;
  revision?: string | null;
  created?: string | null;
}

export interface UpdateResult {
  ok: boolean;
  message: string;
  at: string;
}

export interface UpdateInfo {
  supported: boolean;
  reason?: string;
  image?: string;
  version: string;
  revision?: string | null;
  current?: UpdateImageInfo;
  latest?: UpdateImageInfo | null;
  available?: boolean;
  checked_at?: string | null;
  error?: string | null;
  auto_update: boolean;
  check_every_seconds: number;
  last_result?: UpdateResult | null;
  download_url: string;
}
