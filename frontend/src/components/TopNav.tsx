import React, { useState } from 'react';
import type { TargetPreset, FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';
import { NASA_TEST_PRESETS } from '../services/mockSpherexApi';
import { Share2, Code, Compass, Sparkles, Check } from 'lucide-react';

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
      setTimeout(() => setCopiedLink(false), 2200);
    });
  };

  return (
    <header className="h-14 bg-space-900 border-b border-space-700/80 px-4 flex items-center justify-between text-xs select-none z-30">
      {/* Brand & Mission Identifier */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-2">
          <div className="w-7 h-7 rounded-md bg-gradient-to-tr from-cyan-600 to-cyan-400 p-[1px] flex items-center justify-center shadow-[0_0_12px_rgba(0,242,254,0.3)]">
            <div className="w-full h-full bg-space-950 rounded-md flex items-center justify-center">
              <Compass className="w-4 h-4 text-cyan-400" />
            </div>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-bold tracking-wider text-space-100 font-telemetry">
              <span>SPHEREx</span>
              <span className="text-[10px] font-normal px-1.5 py-0.5 rounded bg-space-800 text-cyan-400 border border-cyan-500/30">
                SKY-VIEWER
              </span>
            </div>
            <span className="text-[10px] text-space-400 font-mono">
              NASA Space Apps • 102 Spectral Bands
            </span>
          </div>
        </div>

        <div className="h-6 w-[1px] bg-space-700/60 mx-1 hidden md:block" />

        {/* NASA 5 Test Presets */}
        <div className="hidden lg:flex items-center space-x-1">
          <span className="text-[11px] font-mono text-space-400 mr-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-amber-400" />
            Targets:
          </span>
          {NASA_TEST_PRESETS.map((preset) => {
            const isSelected = currentPresetId === preset.id;
            return (
              <button
                key={preset.id}
                onClick={() => onSelectPreset(preset)}
                className={`px-2.5 py-1 rounded text-[11px] font-mono transition-all duration-150 border ${
                  isSelected
                    ? 'bg-cyan-950/70 border-cyan-400 text-cyan-300 shadow-[0_0_8px_rgba(0,242,254,0.25)]'
                    : 'bg-space-850 border-space-700 text-space-300 hover:border-space-500 hover:text-space-100'
                }`}
                title={`${preset.name} (${preset.subtitle})\nRA: ${preset.raHms} | Dec: ${preset.decDms}`}
              >
                {preset.name}
              </button>
            );
          })}
        </div>
      </div>

      {/* Preset Mobile Dropdown */}
      <div className="lg:hidden flex items-center">
        <select
          value={currentPresetId || ''}
          onChange={(e) => {
            const found = NASA_TEST_PRESETS.find((p) => p.id === e.target.value);
            if (found) onSelectPreset(found);
          }}
          className="bg-space-850 border border-space-700 rounded px-2 py-1 text-[11px] font-mono text-space-200"
        >
          <option value="" disabled>Select NASA Target...</option>
          {NASA_TEST_PRESETS.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.name}
            </option>
          ))}
        </select>
      </div>

      {/* Right Action Tools: Sim Latency, Share Link, Embed */}
      <div className="flex items-center space-x-2">
        {/* Toggle Simulated Network Loader */}
        <button
          onClick={onToggleSimulateLatency}
          className={`px-2 py-1 rounded text-[11px] font-mono flex items-center gap-1 border transition-all ${
            simulateLatency
              ? 'bg-amber-950/60 border-amber-500/70 text-amber-300 animate-pulse-subtle'
              : 'bg-space-850 border-space-700 text-space-400 hover:text-space-200'
          }`}
          title="Preview the ReactBits-style IRSA cutout loading state micro-interaction"
        >
          <span className={`w-1.5 h-1.5 rounded-full ${simulateLatency ? 'bg-amber-400' : 'bg-space-500'}`} />
          Simulate Cutout Query
        </button>

        {/* Share Link */}
        <button
          onClick={handleCopyShareLink}
          className="px-2.5 py-1 rounded bg-space-850 border border-space-700 text-space-200 hover:border-cyan-500/50 hover:text-cyan-300 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
          title="Syncs current coordinates, FOV, detector, and frame to URL parameters"
        >
          {copiedLink ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Share2 className="w-3.5 h-3.5" />}
          <span>{copiedLink ? 'Copied URL!' : 'Share'}</span>
        </button>

        {/* Embed iframe Generator */}
        <button
          onClick={onOpenEmbedModal}
          className="px-2.5 py-1 rounded bg-space-850 border border-space-700 text-space-200 hover:border-cyan-500/50 hover:text-cyan-300 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
          title="Generate clean <iframe> embed snippet"
        >
          <Code className="w-3.5 h-3.5 text-cyan-400" />
          <span>Embed</span>
        </button>
      </div>
    </header>
  );
};
