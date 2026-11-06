import React, { useState } from 'react';
import { HelpCircle } from 'lucide-react';

interface TooltipProps {
  content: string;
  children?: React.ReactNode;
  className?: string;
}

export const Tooltip: React.FC<TooltipProps> = ({ content, children, className = '' }) => {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <span
      className={`relative inline-flex items-center group cursor-help ${className}`}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
      tabIndex={0}
      role="tooltip"
      aria-label={content}
    >
      {children || <HelpCircle className="h-4 w-4 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 transition-colors" />}

      {isVisible && (
        <span
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 p-2.5 bg-slate-900 text-slate-100 text-xs rounded-lg shadow-xl border border-slate-800 z-50 pointer-events-none transition-all leading-relaxed text-center animate-in fade-in zoom-in-95 duration-150"
        >
          {content}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900" />
        </span>
      )}
    </span>
  );
};

export const JARGON_EXPLANATIONS: Record<string, string> = {
  PUID: 'User ID in Linux that controls which account owns files created by Docker.',
  PGID: 'Group ID in Linux that controls which group owns files created by Docker.',
  Hardlinks: 'Allows files to exist in both your downloads and media folders without taking up extra disk space.',
  Indexer: 'A search provider (torrent tracker) that finds download sources for movies and TV shows.',
  Prowlarr: 'Central indexer manager that connects search providers to Radarr and Sonarr automatically.',
  Radarr: 'Movie management tool that automatically searches, downloads, and organizes films.',
  Sonarr: 'TV show management tool that automatically tracks episodes and handles downloads.',
  Bazarr: 'Subtitle manager that automatically finds subtitles in your preferred languages.',
  qBittorrent: 'Fast, lightweight download engine that retrieves torrent files.',
  Jellyfin: 'Free, open-source media streaming server for your personal movies and TV shows.',
  Plex: 'Popular media streaming server for your personal movies and TV shows.',
  CSRF: 'Cross-Site Request Forgery security token protecting actions from malicious websites.',
  'Atomic Move': 'Moving files instantly on the same filesystem without slow re-copying.',
};

export const JargonHelp: React.FC<{ term: keyof typeof JARGON_EXPLANATIONS; label?: string }> = ({
  term,
  label,
}) => {
  const explanation = JARGON_EXPLANATIONS[term] || 'Technical term explained in plain English.';
  return (
    <span className="inline-flex items-center gap-1">
      <span>{label || term}</span>
      <Tooltip content={explanation} />
    </span>
  );
};
