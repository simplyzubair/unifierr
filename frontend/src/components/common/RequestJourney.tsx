import React from 'react';
import type { RequestOut } from '@/types/api';

// The path every request takes, in plain words. Each backend stage lights up the steps up to and including it.
const STEPS = ['Requested', 'Searching', 'Downloading', 'Organizing', 'Ready to watch'] as const;
const STEP_OF: Partial<Record<RequestOut['stage'], number>> = {
  pending_review: 0,
  searching: 1,
  downloading: 2,
  importing: 3,
  waiting_for_library: 3,
  available: 4,
};

export const RequestJourney: React.FC<{ stage: RequestOut['stage']; message: string }> = ({ stage, message }) => {
  const step = STEP_OF[stage];
  // denied / needs_attention / unknown: no step to light up, just say what is going on.
  const stuck = step === undefined;
  return (
    <div className="space-y-1.5">
      {!stuck && (
        <ol className="flex items-center gap-1" aria-label={`Progress: ${STEPS[step]}`}>
          {STEPS.map((label, i) => (
            <li key={label} className="flex-1" aria-current={i === step ? 'step' : undefined}>
              <div
                className={`h-1.5 rounded-full ${
                  i < step || (i === step && stage === 'available')
                    ? 'bg-emerald-500'
                    : i === step
                      ? 'bg-brand-500 animate-pulse'
                      : 'bg-slate-200 dark:bg-slate-800'
                }`}
              />
              <span
                className={`mt-1 hidden sm:block text-[10px] ${
                  i === step ? 'font-semibold text-slate-800 dark:text-slate-200' : 'text-slate-400'
                }`}
              >
                {label}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className={`text-xs ${stuck ? 'text-amber-700 dark:text-amber-300' : 'text-slate-600 dark:text-slate-400'}`}>
        {!stuck && <span className="font-semibold sm:hidden">{STEPS[step]}: </span>}
        {message}
      </p>
    </div>
  );
};
