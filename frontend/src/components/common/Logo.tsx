import React from 'react';

interface LogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showText?: boolean;
}

export const Logo: React.FC<LogoProps> = ({ className = '', size = 'md', showText = true }) => {
  const iconSizes = {
    sm: 'w-6 h-6',
    md: 'w-8 h-8',
    lg: 'w-10 h-10',
  };

  const textSizes = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-2xl',
  };

  return (
    <div className={`flex items-center gap-2.5 font-bold tracking-tight select-none ${className}`}>
      <div className={`relative flex items-center justify-center shrink-0 ${iconSizes[size]}`}>
        <svg
          viewBox="0 0 40 40"
          className="w-full h-full drop-shadow-sm transition-transform duration-300 hover:scale-105"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="unifierrGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#818cf8" />
              <stop offset="50%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#4338ca" />
            </linearGradient>
            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#6366f1" floodOpacity="0.3" />
            </filter>
          </defs>
          <rect width="40" height="40" rx="10" fill="url(#unifierrGrad)" />
          {/* Unifierr interconnected nodes & media pulse */}
          <path
            d="M13 14a3 3 0 1 0 0 .01M27 14a3 3 0 1 0 0 .01M20 26a3 3 0 1 0 0 .01"
            stroke="#ffffff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M15 15.5l4 8.5M25 15.5l-4 8.5M15.5 14h9"
            stroke="#ffffff"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="20" cy="18" r="2.2" fill="#ffffff" />
        </svg>
      </div>
      {showText && (
        <span className={`${textSizes[size]} font-extrabold text-slate-900 dark:text-white flex items-center`}>
          <span>Uni</span>
          <span className="text-brand-600 dark:text-brand-400">fierr</span>
        </span>
      )}
    </div>
  );
};
