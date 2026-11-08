import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { SetupWizard } from '@/pages/setup/SetupWizard';
import { jobsApi, setupApi, systemApi } from '@/api';

vi.mock('@/context/AuthContext', () => ({
  useAuth: () => ({
    refreshStatus: vi.fn(),
  }),
}));

vi.mock('@/api', () => ({
  setupApi: {
    getEnvironment: vi.fn(),
    prepareFolders: vi.fn(),
    detectApps: vi.fn(),
    install: vi.fn(),
    adopt: vi.fn(),
    wire: vi.fn(),
    complete: vi.fn(),
  },
  jobsApi: {
    getJob: vi.fn(),
  },
  systemApi: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
  },
}));

describe('SetupWizard navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(setupApi.getEnvironment).mockResolvedValue({
      platform: 'linux',
      in_container: true,
      docker_available: true,
      docker_version: '24.0.5',
      suggested_root: '/srv/unifierr',
      puid: 1000,
      pgid: 1000,
      timezone: 'UTC',
      notes: ['Recommended setup verified.'],
    });
    vi.mocked(setupApi.detectApps).mockResolvedValue([]);
    vi.mocked(setupApi.prepareFolders).mockResolvedValue({
      root: '/srv/unifierr',
      created: [],
      existing: [],
      writable: true,
      same_filesystem: true,
      free_bytes: 10_000,
      total_bytes: 20_000,
      problems: [],
    });
    vi.mocked(systemApi.getSettings).mockResolvedValue({
      root: '/srv/unifierr',
      puid: 1000,
      pgid: 1000,
      timezone: 'UTC',
      vpn_enabled: false,
      vpn_provider: '',
      vpn_type: 'openvpn',
      vpn_server_countries: '',
      vpn_has_openvpn_credentials: false,
      vpn_has_wireguard_key: false,
      plex_claim_saved: false,
    });
    vi.mocked(systemApi.updateSettings).mockResolvedValue({
      root: '/srv/unifierr',
      puid: 1000,
      pgid: 1000,
      timezone: 'UTC',
    });
  });

  it('renders step 1 and navigates to step 2 on button click', async () => {
    render(
      <BrowserRouter>
        <SetupWizard />
      </BrowserRouter>
    );

    // Initial step 1 should show Welcome heading
    expect(await screen.findByText('Welcome to Unifierr')).toBeInTheDocument();
    expect(screen.getByText('Operating System / Platform')).toBeInTheDocument();

    const continueBtn = screen.getByRole('button', { name: /continue to storage/i });
    await userEvent.click(continueBtn);

    // Should now be on step 2: Storage
    await waitFor(() => {
      expect(screen.getByText('Confirm Your Media Storage')).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('/srv/unifierr')).toBeInTheDocument();

    // Clicking Back should return to step 1
    const backBtn = screen.getByRole('button', { name: /back/i });
    await userEvent.click(backBtn);

    await waitFor(() => {
      expect(screen.getByText('Welcome to Unifierr')).toBeInTheDocument();
    });
  });

  it('asks for a short-lived claim token when installing a new Plex server', async () => {
    render(
      <BrowserRouter>
        <SetupWizard />
      </BrowserRouter>
    );

    await screen.findByText('Welcome to Unifierr');
    await userEvent.click(screen.getByRole('button', { name: /continue to storage/i }));
    await userEvent.click(screen.getByRole('button', { name: /check storage & find apps/i }));
    await screen.findByText('Review Your Apps');
    await userEvent.click(screen.getByRole('radio', { name: /plex media server/i }));
    await userEvent.click(screen.getByRole('button', { name: /more options: vpn and plex setup/i }));

    expect(await screen.findByLabelText('Plex claim token')).toBeInTheDocument();
    expect(screen.getByText(/expire after about 4 minutes/i)).toBeInTheDocument();
  });

  it('checks storage before recommending apps', async () => {
    vi.mocked(setupApi.prepareFolders).mockResolvedValue({
      root: '/srv/unifierr',
      created: [],
      existing: [],
      writable: false,
      same_filesystem: true,
      free_bytes: 0,
      total_bytes: 20_000,
      problems: [],
    });
    render(<BrowserRouter><SetupWizard /></BrowserRouter>);

    await screen.findByText('Welcome to Unifierr');
    await userEvent.click(screen.getByRole('button', { name: /continue to storage/i }));
    await userEvent.click(screen.getByRole('button', { name: /check storage & find apps/i }));

    expect(await screen.findByText('Storage needs attention')).toBeInTheDocument();
    expect(setupApi.detectApps).not.toHaveBeenCalled();
  });

  it('connects detected apps and installs only missing recommended apps', async () => {
    vi.mocked(setupApi.detectApps).mockResolvedValue([{
      kind: 'radarr',
      source: 'docker',
      container_name: 'radarr',
      url_candidates: ['http://radarr:7878'],
      reachable_url: 'http://radarr:7878',
      api_key_found: true,
      managed: false,
    }]);
    vi.mocked(setupApi.adopt).mockResolvedValue({} as never);
    vi.mocked(setupApi.install).mockResolvedValue({ job_id: 'install-job' });
    vi.mocked(setupApi.wire).mockResolvedValue({ job_id: 'wire-job' });
    vi.mocked(jobsApi.getJob).mockResolvedValue({
      id: 'install-job',
      kind: 'install',
      status: 'done',
      steps: [],
      log: [],
      result: {},
      started_at: new Date().toISOString(),
    });

    render(<BrowserRouter><SetupWizard /></BrowserRouter>);
    await screen.findByText('Welcome to Unifierr');
    await userEvent.click(screen.getByRole('button', { name: /continue to storage/i }));
    await userEvent.click(screen.getByRole('button', { name: /check storage & find apps/i }));
    await screen.findByText('Review Your Apps');
    await userEvent.click(screen.getByRole('button', { name: /set up recommended apps/i }));

    await waitFor(() => expect(setupApi.adopt).toHaveBeenCalledWith({
      kind: 'radarr',
      base_url: 'http://radarr:7878',
    }));
    await waitFor(() => expect(setupApi.install).toHaveBeenCalledWith([
      'sonarr', 'prowlarr', 'qbittorrent', 'bazarr', 'jellyfin',
    ]));
    await waitFor(() => expect(setupApi.wire).toHaveBeenCalledOnce());
  });
});
