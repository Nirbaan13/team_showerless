import React, { useState } from 'react';
import type { TargetPreset, FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { Share2, Code, Check, RefreshCw } from 'lucide-react';

interface TopNavProps {
  currentPresetId: string | null;
  onSelectPreset: (preset: TargetPreset) => void;
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  onOpenEmbedModal: () => void;
  simulateLatency: boolean;
  onToggleSimulateLatency: () => void;
}

export const TopNav: React.FC<TopNavProps> = ({
  currentPresetId,
  onSelectPreset,
  ra,
  dec,
  fov,
  selectedArray,
  subtractionMode,
  activeFrameIndex,
  onOpenEmbedModal,
  simulateLatency,
  onToggleSimulateLatency,
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
    <header className="h-12 bg-nasa-surface border-b border-nasa-border px-4 flex items-center justify-between text-xs select-none z-30">
      {/* Brand & Mission Identifier */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 rounded bg-nasa-blue flex items-center justify-center font-bold text-white text-[11px]">
            NASA
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-semibold text-nasa-textMain tracking-wide text-xs">
              SPHEREx Sky-Viewer
            </span>
            <span className="text-[10px] text-nasa-textMuted font-mono">
              IPAC / IRSA Quick Release Tool
            </span>
          </div>
        </div>

        <div className="h-4 w-[1px] bg-nasa-border mx-2 hidden md:block" />

        {/* Standard Preset Targets Selector */}
        <div className="hidden lg:flex items-center space-x-1">
          <span className="text-[11px] font-mono text-nasa-textMuted mr-1">
            Presets:
          </span>
          {NASA_TEST_PRESETS.map((preset) => {
            const isSelected = currentPresetId === preset.id;
            return (
              <button
                key={preset.id}
                onClick={() => onSelectPreset(preset)}
                className={`px-2 py-1 rounded text-[11px] font-mono transition-colors border ${
                  isSelected
                    ? 'bg-blue-900/40 border-blue-600 text-blue-200 font-medium'
                    : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:border-nasa-subtle hover:text-nasa-textMain'
                }`}
                title={`${preset.name} (${preset.subtitle})\nRA: ${preset.raHms} | Dec: ${preset.decDms}`}
              >
                {preset.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Right Controls: Query indicator, Share, Embed */}
      <div className="flex items-center space-x-2">
        <button
          onClick={onToggleSimulateLatency}
          className={`px-2 py-1 rounded text-[11px] font-mono flex items-center gap-1.5 border transition-colors ${
            simulateLatency
              ? 'bg-amber-950/40 border-amber-600/70 text-amber-200'
              : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:text-nasa-textMain'
          }`}
          title="Simulate remote IRSA cutout network query"
        >
          <RefreshCw className={`w-3 h-3 ${simulateLatency ? 'animate-spin' : ''}`} />
          <span>Cutout Latency Sim</span>
        </button>

        <button
          onClick={handleCopyShareLink}
          className="px-2.5 py-1 rounded bg-nasa-dark border border-nasa-border text-nasa-textMain hover:border-blue-500 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
          title="Copy direct URL link with current coordinate state"
        >
          {copiedLink ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Share2 className="w-3.5 h-3.5" />}
          <span>{copiedLink ? 'Copied' : 'Share URL'}</span>
        </button>

        <button
          onClick={onOpenEmbedModal}
          className="px-2.5 py-1 rounded bg-nasa-dark border border-nasa-border text-nasa-textMain hover:border-blue-500 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
          title="Generate clean <iframe> embed snippet"
        >
          <Code className="w-3.5 h-3.5 text-blue-400" />
          <span>Embed</span>
        </button>
      </div>
    </header>
  );
};
