import React from 'react';
import { Loader2 } from 'lucide-react';

interface ReactBitsLoaderProps {
  label?: string;
  sublabel?: string;
}

export const ReactBitsLoader: React.FC<ReactBitsLoaderProps> = ({
  label = 'Querying SPHEREx Cutout Service...',
  sublabel = 'Retrieving calibrated spectral images (Level-3)',
}) => {
  return (
    <div className="absolute inset-0 bg-nasa-dark/80 backdrop-blur-sm flex flex-col items-center justify-center z-50 p-6">
      <div className="bg-nasa-surface border border-nasa-border rounded-lg p-5 flex flex-col items-center space-y-3 shadow-xl max-w-sm text-center">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        <div>
          <div className="font-mono text-xs font-semibold text-nasa-textMain uppercase tracking-wide">
            {label}
          </div>
          <div className="text-[11px] text-nasa-textMuted font-mono mt-1">
            {sublabel}
          </div>
        </div>
      </div>
    </div>
  );
};
