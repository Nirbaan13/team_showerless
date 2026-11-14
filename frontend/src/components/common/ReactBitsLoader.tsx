import React from 'react';

interface ReactBitsLoaderProps {
  label?: string;
  sublabel?: string;
}

export const ReactBitsLoader: React.FC<ReactBitsLoaderProps> = ({
  label = 'Querying SPHEREx IRSA Cutout Service...',
  sublabel = 'Synthesizing multi-epoch FITS cube (Level-3 calibrated)',
}) => {
  return (
    <div className="absolute inset-0 bg-space-950/85 backdrop-blur-md flex flex-col items-center justify-center z-50 p-6">
      <div className="relative w-28 h-28 flex items-center justify-center">
        {/* Outer orbital radar ring */}
        <div className="absolute inset-0 rounded-full border border-cyan-500/20 border-dashed animate-spin" style={{ animationDuration: '14s' }} />
        
        {/* Mid pulsing scanner ring */}
        <div className="absolute inset-2 rounded-full border-2 border-t-cyan-400 border-r-transparent border-b-cyan-500/30 border-l-transparent animate-spin" style={{ animationDuration: '2.5s' }} />

        {/* Inner reverse counter ring */}
        <div className="absolute inset-6 rounded-full border border-b-cyan-300 border-t-transparent border-l-transparent border-r-transparent animate-spin" style={{ animationDuration: '1.2s', animationDirection: 'reverse' }} />

        {/* Center reticle core */}
        <div className="relative flex items-center justify-center w-8 h-8 rounded-full bg-cyan-950/60 border border-cyan-400/80 shadow-[0_0_15px_rgba(0,242,254,0.4)]">
          <div className="w-2 h-2 rounded-full bg-cyan-300 animate-ping" />
        </div>

        {/* Crosshair ticks */}
        <div className="absolute -top-1 w-0.5 h-2 bg-cyan-400/80" />
        <div className="absolute -bottom-1 w-0.5 h-2 bg-cyan-400/80" />
        <div className="absolute -left-1 h-0.5 w-2 bg-cyan-400/80" />
        <div className="absolute -right-1 h-0.5 w-2 bg-cyan-400/80" />
      </div>

      {/* Shimmer text micro-interaction */}
      <div className="mt-6 flex flex-col items-center text-center space-y-1.5">
        <div className="font-telemetry text-xs tracking-widest uppercase font-semibold text-cyan-300">
          {label}
        </div>
        <div className="text-[11px] text-space-400 font-mono flex items-center gap-1.5">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          {sublabel}
        </div>
      </div>

      {/* Animated Wave shimmer bar */}
      <div className="w-56 h-1 mt-5 bg-space-800 rounded-full overflow-hidden border border-space-700/60 relative">
        <div className="absolute top-0 bottom-0 left-0 bg-gradient-to-r from-transparent via-cyan-400 to-transparent w-full animate-shimmer" 
             style={{ 
               backgroundImage: 'linear-gradient(90deg, transparent 0%, rgba(0, 242, 254, 0.8) 50%, transparent 100%)',
               backgroundSize: '200% 100%'
             }} />
      </div>
    </div>
  );
};
