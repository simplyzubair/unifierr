import React from 'react';
import { AlertCircle, RefreshCw, X } from 'lucide-react';
import { ApiError } from '@/api/client';

interface ErrorCardProps {
  error: Error | ApiError | string | null | undefined;
  title?: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  className?: string;
}

export const ErrorCard: React.FC<ErrorCardProps> = ({
  error,
  title,
  onRetry,
  onDismiss,
  className = '',
}) => {
  if (!error) return null;

  let message = 'An unexpected error occurred.';
  let explanation: string | null = null;
  let fix: string | null = null;

  if (typeof error === 'string') {
    message = error;
  } else if (error instanceof ApiError) {
    message = error.message;
    explanation = error.explanation || null;
    fix = error.fix || null;
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div
      role="alert"
      className={`rounded-xl border border-red-200 bg-red-50/90 p-4 text-red-900 shadow-sm dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600 dark:text-red-400" />
          <div className="space-y-2">
            <div>
              {title && <h4 className="font-semibold text-red-950 dark:text-red-100">{title}</h4>}
              <p className="text-sm font-medium leading-relaxed">{message}</p>
            </div>

            {explanation && (
              <div className="rounded-lg bg-red-100/70 p-2.5 text-xs text-red-900 dark:bg-red-900/30 dark:text-red-300">
                <span className="font-semibold block mb-0.5">What this means:</span>
                <p className="leading-relaxed">{explanation}</p>
              </div>
            )}

            {fix && (
              <div className="rounded-lg bg-emerald-100/70 p-2.5 text-xs text-emerald-950 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-300/40 dark:border-emerald-800/40">
                <span className="font-semibold block mb-0.5">How to fix:</span>
                <p className="leading-relaxed">{fix}</p>
              </div>
            )}

            {onRetry && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={onRetry}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-red-700 transition focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  Try Again
                </button>
              </div>
            )}
          </div>
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss error"
            className="rounded-lg p-1 text-red-600 hover:bg-red-100 hover:text-red-900 dark:text-red-400 dark:hover:bg-red-900/50 dark:hover:text-red-100 transition"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};
