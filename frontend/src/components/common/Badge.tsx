import React from 'react';
import type { MediaAvailability, QueueState } from '@/types/api';
import { CheckCircle2, Clock, DownloadCloud, AlertTriangle, XCircle, Play, Pause, AlertCircle } from 'lucide-react';

interface AvailabilityBadgeProps {
  status: MediaAvailability | string;
  className?: string;
  size?: 'sm' | 'md';
}

export const AvailabilityBadge: React.FC<AvailabilityBadgeProps> = ({
  status,
  className = '',
  size = 'md',
}) => {
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs font-medium';

  switch (status) {
    case 'available':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-emerald-100 font-semibold text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 ${sizeClasses} ${className}`}
        >
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
          Available
        </span>
      );

    case 'downloading':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-sky-100 font-semibold text-sky-800 dark:bg-sky-950/60 dark:text-sky-300 ${sizeClasses} ${className}`}
        >
          <DownloadCloud className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400 animate-pulse" />
          Downloading
        </span>
      );

    case 'requested':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-indigo-100 font-semibold text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 ${sizeClasses} ${className}`}
        >
          <Clock className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
          Requested
        </span>
      );

    case 'missing':
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-amber-100 font-semibold text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 ${sizeClasses} ${className}`}
        >
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          Missing
        </span>
      );

    case 'not_added':
    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-slate-100 font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300 ${sizeClasses} ${className}`}
        >
          Not in Library
        </span>
      );
  }
};

interface QueueStateBadgeProps {
  state: QueueState;
  className?: string;
}

export const QueueStateBadge: React.FC<QueueStateBadgeProps> = ({ state, className = '' }) => {
  const base = 'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold';

  switch (state) {
    case 'downloading':
      return (
        <span className={`${base} bg-sky-100 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300 ${className}`}>
          <DownloadCloud className="h-3 w-3 animate-pulse text-sky-500" />
          Downloading
        </span>
      );
    case 'seeding':
    case 'completed':
      return (
        <span className={`${base} bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 ${className}`}>
          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
          {state === 'seeding' ? 'Seeding' : 'Completed'}
        </span>
      );
    case 'paused':
      return (
        <span className={`${base} bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-300 ${className}`}>
          <Pause className="h-3 w-3 text-slate-500" />
          Paused
        </span>
      );
    case 'queued':
      return (
        <span className={`${base} bg-indigo-100 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 ${className}`}>
          <Clock className="h-3 w-3 text-indigo-500" />
          Queued
        </span>
      );
    case 'stalled':
      return (
        <span className={`${base} bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 ${className}`}>
          <AlertCircle className="h-3 w-3 text-amber-500" />
          Stalled
        </span>
      );
    case 'importing':
      return (
        <span className={`${base} bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300 ${className}`}>
          <Play className="h-3 w-3 text-purple-500" />
          Importing
        </span>
      );
    case 'error':
      return (
        <span className={`${base} bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300 ${className}`}>
          <XCircle className="h-3 w-3 text-red-500" />
          Error
        </span>
      );
    case 'checking':
    case 'unknown':
    default:
      return (
        <span className={`${base} bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 ${className}`}>
          {state}
        </span>
      );
  }
};
