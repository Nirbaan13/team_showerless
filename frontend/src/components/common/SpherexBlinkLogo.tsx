import React from 'react';

interface SpherexBlinkLogoProps {
  className?: string;
  size?: number;
}

export const SpherexBlinkLogo: React.FC<SpherexBlinkLogoProps> = ({
  className = '',
  size = 28,
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
    >
      {/* Outer tactile rounded badge with 2px black border effect */}
      <rect x="2" y="2" width="44" height="44" rx="10" fill="#09090d" stroke="#10b981" strokeWidth="2.5" />
      <rect x="3.5" y="3.5" width="41" height="41" rx="8.5" stroke="#000000" strokeWidth="1" fill="none" opacity="0.6" />

      {/* Optical telescope crosshairs */}
      <line x1="24" y1="6" x2="24" y2="12" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="24" y1="36" x2="24" y2="42" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="6" y1="24" x2="12" y2="24" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="36" y1="24" x2="42" y2="24" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />

      {/* Multi-epoch orbital trail arc */}
      <path d="M 12 34 C 15 20, 24 14, 35 13" stroke="#34d399" strokeWidth="2" strokeDasharray="2 3" strokeLinecap="round" />

      {/* Blink motion epoch dots */}
      <circle cx="14" cy="31" r="2" fill="#059669" opacity="0.6" />
      <circle cx="21" cy="22" r="2.5" fill="#10b981" opacity="0.85" />
      <circle cx="29" cy="16" r="3" fill="#34d399" />

      {/* Current active moving object with infrared glow */}
      <circle cx="36" cy="13" r="5" fill="#fbbf24" fillOpacity="0.3" />
      <circle cx="36" cy="13" r="3.2" fill="#f59e0b" />
      <circle cx="36" cy="13" r="1.3" fill="#ffffff" />
    </svg>
  );
};
