import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CleanupPrompt } from '@/components/common/CleanupPrompt';
import { mediaApi } from '@/api';

vi.mock('@/api', () => ({ mediaApi: { getCleanupDue: vi.fn(), answerCleanup: vi.fn() } }));

describe('CleanupPrompt', () => {
  it('shows a due movie and records a delete answer', async () => {
    vi.mocked(mediaApi.getCleanupDue).mockResolvedValue([{
      external_id: 17, tmdb_id: 55, title: 'The Example', year: 2021,
      downloaded_at: new Date().toISOString(), days_since_download: 91,
    }]);
    vi.mocked(mediaApi.answerCleanup).mockResolvedValue({ ok: true });
    render(<CleanupPrompt />);
    expect(await screen.findByText(/The Example \(2021\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Yes, delete it' }));
    expect(mediaApi.answerCleanup).toHaveBeenCalledWith(17, true);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });
});
