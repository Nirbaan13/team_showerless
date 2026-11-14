import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { Share2, Code, Check, RefreshCw } from 'lucide-react';

interface TopNavProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  onOpenEmbedModal: () => void;
  simulateLatency: boolean;
  onToggleSimulateLatency: () => void;
  isViewerActive: boolean;
}

export const TopNav: React.FC<TopNavProps> = ({
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  activeFrameIndex,
  onOpenEmbedModal,
  simulateLatency,
  onToggleSimulateLatency,
  isViewerActive,
}) => {
  const [copiedLink, setCopiedLink] = useState(false);

  const handleCopyShareLink = () => {
    const params = new URLSearchParams({
      ra: ra.toFixed(6),
      dec: dec.toFixed(6),
      fov,
      detector: String(selectedArray),
      subtraction: subtractionMode,
      frame: String(activeFrameIndex),
    });
    const shareUrl = `${window.location.origin}${window.location.pathname}?${params.toString()}`;
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  };

  return (
    <div className="flex items-center space-x-2">
      {/* Current Coordinates Indicator (Only shown when viewer is active) */}
      {isViewerActive && (
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-[11px] font-mono text-paper-300">
          <span className="text-paper-500">RA:</span>
          <span className="text-paper-100">{ra.toFixed(4)}°</span>
          <span className="text-paper-700">•</span>
          <span className="text-paper-500">Dec:</span>
          <span className="text-paper-100">{dec.toFixed(4)}°</span>
        </div>
      )}

      {/* Latency Simulator Toggle with clear (Test Mode) indicator */}
      <button
        onClick={onToggleSimulateLatency}
        className={`px-2.5 py-1 rounded text-[11px] font-mono flex items-center gap-1.5 border transition-colors ${
          simulateLatency
            ? 'bg-ochre-950/40 border-ochre-500/70 text-ochre-300'
            : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200'
        }`}
        title="Simulate remote IRSA network latency micro-interaction"
      >
        <RefreshCw className={`w-3 h-3 ${simulateLatency ? 'animate-spin text-ochre-400' : ''}`} />
        <span>Latency Sim</span>
        <span className="text-[9px] text-paper-500 font-sans">(Test)</span>
      </button>

      {/* Share Direct URL */}
      <button
        onClick={handleCopyShareLink}
        className="px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-paper-200 hover:border-paper-600 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
        title="Copy deep-link URL containing coordinates and settings"
      >
        {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Share2 className="w-3.5 h-3.5" />}
        <span>{copiedLink ? 'Copied' : 'Share'}</span>
      </button>

      {/* Embed Iframe Snippet */}
      <button
        onClick={onOpenEmbedModal}
        className="px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-paper-200 hover:border-paper-600 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
        title="Generate clean <iframe> embed snippet"
      >
        <Code className="w-3.5 h-3.5 text-ochre-400" />
        <span>Embed</span>
      </button>
    </div>
  );
};
