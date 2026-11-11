import React from 'react';
import { Play } from 'lucide-react';

/** Poster that opens the title in Jellyfin when it is there; a plain poster otherwise. */
export const PosterLink: React.FC<{ href: string | null; title: string; className?: string; children: React.ReactNode }> = ({
  href,
  title,
  className = 'relative aspect-[2/3] w-full overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800',
  children,
}) =>
  href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={`Watch ${title} in Jellyfin`}
      aria-label={`Watch ${title} in Jellyfin`}
      className={`group block ${className} focus-visible:outline-2 focus-visible:outline-brand-500`}
    >
      {children}
      <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/35">
        <Play className="h-9 w-9 text-white opacity-0 drop-shadow transition group-hover:opacity-100" fill="currentColor" />
      </span>
    </a>
  ) : (
    <div className={className}>{children}</div>
  );
