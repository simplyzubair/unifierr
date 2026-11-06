import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { SetupWizard } from '@/pages/setup/SetupWizard';
import { setupApi } from '@/api';

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

    // Should now be on step 2: Storage Layout
    await waitFor(() => {
      expect(screen.getByText('Storage & Media Folders')).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue('/srv/unifierr')).toBeInTheDocument();

    // Clicking Back should return to step 1
    const backBtn = screen.getByRole('button', { name: /back/i });
    await userEvent.click(backBtn);

    await waitFor(() => {
      expect(screen.getByText('Welcome to Unifierr')).toBeInTheDocument();
    });
  });
});
