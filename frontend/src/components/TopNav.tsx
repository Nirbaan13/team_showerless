import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { Share2, Code, Check, Database, UserCheck } from 'lucide-react';

interface TopNavProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  candidateId?: string | null;
  presetId?: string | null;
  onOpenEmbedModal: () => void;
  onOpenFeed?: () => void;
  onOpenCatalogue?: () => void;
  isViewerActive: boolean;
  isScientistMode?: boolean;
}

export const TopNav: React.FC<TopNavProps> = ({
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  activeFrameIndex,
  candidateId,
  presetId,
  onOpenEmbedModal,
  onOpenFeed,
  onOpenCatalogue,
  isViewerActive,
  isScientistMode: _isScientistMode = false,
}) => {
  const [copiedLink, setCopiedLink] = useState(false);
  const getShareUrl = () => {
    const params = new URLSearchParams({
      ra: ra.toFixed(6),
      dec: dec.toFixed(6),
      fov,
      detector: String(selectedArray),
      subtraction: subtractionMode,
      frame: String(activeFrameIndex),
      tab: 'viewer',
    });
    if (candidateId) params.set('candidate', candidateId);
    if (presetId) params.set('preset', presetId);
    return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
  };

  const handleCopyShareLink = () => {
    const url = getShareUrl();
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  };

  if (!isViewerActive) {
    return null;
  }

  return (
    <div className="flex items-center space-x-2 relative">
      {/* Current Coordinates Indicator */}
      <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded bg-paper-950 border border-paper-800 text-[11px] font-mono text-paper-300">
        <span className="text-paper-500">RA:</span>
        <span className="text-ochre-300 font-medium">{ra.toFixed(4)}°</span>
        <span className="text-paper-700">•</span>
        <span className="text-paper-500">Dec:</span>
        <span className="text-ochre-300 font-medium">{dec.toFixed(4)}°</span>
      </div>


      {/* Share View: single clean button that copies the link */}
      <button
        onClick={handleCopyShareLink}
        className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer"
        title="Copy direct shareable coordinate URL to clipboard"
      >
        {copiedLink ? <Check className="w-3.5 h-3.5 text-emerald-400 stroke-[2.5]" /> : <Share2 className="w-3.5 h-3.5 text-emerald-400" />}
        <span>{copiedLink ? 'Link Copied!' : 'Share View'}</span>
      </button>

      {/* Embed Iframe Snippet */}
      <button
        onClick={onOpenEmbedModal}
        className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-paper-900 border-2 border-black text-paper-200 hover:text-emerald-300 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer"
        title="Generate responsive <iframe> embed snippet for blogs or research writeups"
      >
        <Code className="w-3.5 h-3.5 text-ochre-400" />
        <span>Embed</span>
      </button>

      {/* Verification Feed Button */}
      {onOpenFeed && (
        <button
          onClick={onOpenFeed}
          className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-sky-950/80 border-2 border-sky-500/60 text-sky-300 hover:text-white hover:bg-sky-900 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer shadow-[0_0_10px_rgba(56,189,248,0.2)]"
          title="Open Community Verification Feed & Peer-Review Discussions"
        >
          <UserCheck className="w-3.5 h-3.5 text-sky-400" />
          <span className="font-semibold">Verification Feed</span>
        </button>
      )}

      {/* Candidate Catalog Button - directly beside Verification Feed */}
      {onOpenCatalogue && (
        <button
          onClick={onOpenCatalogue}
          className="btn-tactile-sm px-2.5 py-1 rounded-lg bg-emerald-950/80 border-2 border-emerald-500/60 text-emerald-300 hover:text-white hover:bg-emerald-900 text-[11px] font-mono flex items-center gap-1.5 cursor-pointer shadow-[0_0_10px_rgba(16,185,129,0.25)]"
          title="Open PlanetX Persistent Candidate Catalog & Scientific Submissions"
        >
          <Database className="w-3.5 h-3.5 text-emerald-400" />
          <span className="font-semibold">Candidate Catalog</span>
        </button>
      )}
    </div>
  );
};
