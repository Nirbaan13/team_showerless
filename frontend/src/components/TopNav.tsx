import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { Share2, Code, Check } from 'lucide-react';

// Toggle to bring the Share View button back
const SHOW_SHARE_VIEW = false;

interface TopNavProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  onOpenEmbedModal: () => void;
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

  // On the Homepage, keep the top right clean and empty (no coordinates or share/embed yet)
  if (!isViewerActive) {
    return null;
  }

  return (
    <div className="flex items-center space-x-2">
      {/* Current Coordinates Indicator */}
      <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-[11px] font-mono text-paper-300">
        <span className="text-paper-500">RA:</span>
        <span className="text-ochre-300 font-medium">{ra.toFixed(4)}°</span>
        <span className="text-paper-700">•</span>
        <span className="text-paper-500">Dec:</span>
        <span className="text-ochre-300 font-medium">{dec.toFixed(4)}°</span>
      </div>

      {/* Share Direct Coordinate URL — hidden for now (we'll work on sharing later); code kept */}
      {SHOW_SHARE_VIEW && (
      <button
        onClick={handleCopyShareLink}
        className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer"
        title="Copy direct shareable link for this coordinate and band"
      >
        {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Share2 className="w-3.5 h-3.5 text-emerald-400" />}
        <span>{copiedLink ? 'Link Copied!' : 'Share View'}</span>
      </button>
      )}

      {/* Embed Iframe Snippet */}
      <button
        onClick={onOpenEmbedModal}
        className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer"
        title="Generate responsive <iframe> embed snippet"
      >
        <Code className="w-3.5 h-3.5 text-ochre-400" />
        <span>Embed</span>
      </button>
    </div>
  );
};
