import React from 'react';

interface SpherexBlinkLogoProps {
  className?: string;
  size?: number;
}

export const SpherexBlinkLogo: React.FC<SpherexBlinkLogoProps> = ({
  className = '',
  size = 24,
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
      {/* Outer tactile rounded badge */}
      <rect x="2" y="2" width="44" height="44" rx="10" fill="#09090d" stroke="#10b981" strokeWidth="2.5" />
      <rect x="3.5" y="3.5" width="41" height="41" rx="8.5" stroke="#000000" strokeWidth="1" fill="none" opacity="0.6" />

      {/* Optical telescope crosshairs */}
      <line x1="24" y1="5" x2="24" y2="13" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="24" y1="35" x2="24" y2="43" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="5" y1="24" x2="13" y2="24" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />
      <line x1="35" y1="24" x2="43" y2="24" stroke="#10b981" strokeWidth="2" strokeLinecap="round" />

      {/* Clean circular aperture reticle */}
      <circle cx="24" cy="24" r="11" stroke="#34d399" strokeWidth="1.8" strokeDasharray="3 3" />

      {/* Clean glowing core */}
      <circle cx="24" cy="24" r="5" fill="#fbbf24" fillOpacity="0.3" />
      <circle cx="24" cy="24" r="3.2" fill="#f59e0b" />
      <circle cx="24" cy="24" r="1.3" fill="#ffffff" />
    </svg>
  );
};
