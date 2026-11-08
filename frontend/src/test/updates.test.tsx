import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Updates } from '@/pages/updates/Updates';
import { systemApi } from '@/api';

vi.mock('@/api', () => ({
  systemApi: { getUpdate: vi.fn(), checkUpdate: vi.fn(), applyUpdate: vi.fn(), setAutoUpdate: vi.fn() },
}));

const base = {
  supported: true, version: '0.1.0', auto_update: false, check_every_seconds: 900,
  download_url: 'https://example.test', current: { id: 'aaa111', revision: 'abcdef123456' },
};

beforeEach(() => vi.resetAllMocks());

describe('Updates page', () => {
  it('explains why updates are unavailable instead of showing buttons', async () => {
    vi.mocked(systemApi.getUpdate).mockResolvedValue({ ...base, supported: false, reason: 'Built on this computer.' } as never);
    render(<Updates />);
    expect(await screen.findByText('Built on this computer.')).toBeTruthy();
    expect(screen.queryByText('Update now')).toBeNull();
  });

  it('offers Update now only when a newer version is ready, and asks the server to apply it', async () => {
    vi.mocked(systemApi.getUpdate).mockResolvedValue({
      ...base, available: true, latest: { id: 'bbb222', revision: '999999aaaaaa' },
    } as never);
    vi.mocked(systemApi.applyUpdate).mockResolvedValue({ started: true, message: 'Updating.' });
    render(<Updates />);

    await userEvent.click(await screen.findByText('Update now'));

    await waitFor(() => expect(systemApi.applyUpdate).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('status')).toBeTruthy(); // "Updating. Unifierr restarts..."
  });

  it('saves the automatic-update switch', async () => {
    vi.mocked(systemApi.getUpdate).mockResolvedValue({ ...base, available: false } as never);
    vi.mocked(systemApi.setAutoUpdate).mockResolvedValue({ ...base, auto_update: true } as never);
    render(<Updates />);

    await userEvent.click(await screen.findByLabelText(/Update automatically/));

    await waitFor(() => expect(systemApi.setAutoUpdate).toHaveBeenCalledWith(true));
  });
});
