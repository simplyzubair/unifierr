import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Downloads } from '@/pages/downloads/Downloads';
import { downloadsApi } from '@/api';

vi.mock('@/api', () => ({
  downloadsApi: { getDownloads: vi.fn(), pause: vi.fn(), resume: vi.fn(), remove: vi.fn() },
}));

const item = (id: string, source: string) => ({
  id, name: `${id}.mkv`, source, state: 'downloading', progress: 40, media_title: id,
});

describe('Downloads controls', () => {
  it('shows pause/remove only for downloads a connected client owns, and explains the rest', async () => {
    vi.mocked(downloadsApi.getDownloads).mockResolvedValue({
      items: [item('owned', 'qbittorrent'), item('radarr-only', 'radarr')],
      dl_speed: 0,
      up_speed: 0,
      updated_at: new Date().toISOString(),
    } as never);

    render(<Downloads />);

    await screen.findByText('owned');
    expect(screen.getAllByTitle('Pause Download')).toHaveLength(1);
    expect(screen.getAllByTitle('Remove Download')).toHaveLength(1);
    expect(screen.getByRole('note').textContent).toMatch(/not connected to yet/);
  });
});
