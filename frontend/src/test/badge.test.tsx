import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AvailabilityBadge } from '@/components/common/Badge';

describe('AvailabilityBadge', () => {
  it('renders "Available" badge for available status', () => {
    render(<AvailabilityBadge status="available" />);
    expect(screen.getByText('Available')).toBeInTheDocument();
  });

  it('renders "Downloading" badge for downloading status', () => {
    render(<AvailabilityBadge status="downloading" />);
    expect(screen.getByText('Downloading')).toBeInTheDocument();
  });

  it('renders "Requested" badge for requested status', () => {
    render(<AvailabilityBadge status="requested" />);
    expect(screen.getByText('Requested')).toBeInTheDocument();
  });

  it('renders "Missing" badge for missing status', () => {
    render(<AvailabilityBadge status="missing" />);
    expect(screen.getByText('Not downloaded yet')).toBeInTheDocument();
  });

  it('renders "Not in Library" badge for not_added status', () => {
    render(<AvailabilityBadge status="not_added" />);
    expect(screen.getByText('Not in Library')).toBeInTheDocument();
  });
});
