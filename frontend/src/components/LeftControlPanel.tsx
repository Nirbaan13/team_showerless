import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS } from '../services/mockSpherexApi';
import { Layers, Crosshair, Filter, Database, Info, RefreshCw } from 'lucide-react';

interface LeftControlPanelProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  onUpdateCoords: (ra: number, dec: number) => void;
  onUpdateFov: (fov: FOVOption) => void;
  selectedArray: DetectorArrayId | 'all';
  onSelectArray: (arr: DetectorArrayId | 'all') => void;
  selectedChannel: number | null;
  onSelectChannel: (ch: number | null) => void;
  subtractionMode: SubtractionMode;
  onChangeSubtractionMode: (mode: SubtractionMode) => void;
  overlays: CatalogOverlayState;
  onToggleOverlay: (key: keyof CatalogOverlayState) => void;
  onRefreshCutout: () => void;
}

export const LeftControlPanel: React.FC<LeftControlPanelProps> = ({
  ra,
  dec,
  fov,
  onUpdateCoords,
  onUpdateFov,
  selectedArray,
  onSelectArray,
  selectedChannel,
  onSelectChannel,
  subtractionMode,
  onChangeSubtractionMode,
  overlays,
  onToggleOverlay,
  onRefreshCutout,
}) => {
  const [raInput, setRaInput] = useState(ra.toFixed(6));
  const [decInput, setDecInput] = useState(dec.toFixed(6));

  // Sync inputs when ra/dec props change from presets or URL
  React.useEffect(() => {
    setRaInput(ra.toFixed(6));
    setDecInput(dec.toFixed(6));
  }, [ra, dec]);

  const handleApplyCoords = (e: React.FormEvent) => {
    e.preventDefault();
    const parsedRa = parseFloat(raInput);
    const parsedDec = parseFloat(decInput);
    if (!isNaN(parsedRa) && !isNaN(parsedDec)) {
      onUpdateCoords(parsedRa, parsedDec);
    }
  };

  // Approximate IRSA data transfer size and time per FOV
  const fovTransferEstimates: Record<FOVOption, { size: string; latency: string }> = {
    "1'": { size: '~120 KB', latency: '0.2s' },
    "3'": { size: '~980 KB', latency: '0.5s' },
    "5'": { size: '~2.8 MB', latency: '1.1s' },
    "10'": { size: '~11.2 MB', latency: '3.4s' },
  };

  return (
    <aside className="w-80 bg-space-900/95 border-r border-space-700/80 flex flex-col h-[calc(100vh-3.5rem)] text-xs overflow-y-auto select-none z-20">
      {/* 1. Sky Query / Coordinate Section */}
      <div className="p-3.5 border-b border-space-700/70">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 font-semibold text-space-100 font-telemetry uppercase tracking-wider text-[11px]">
            <Crosshair className="w-3.5 h-3.5 text-cyan-400" />
            <span>Target Coordinates & FOV</span>
          </div>
          <button
            onClick={onRefreshCutout}
            className="p-1 rounded hover:bg-space-800 text-space-400 hover:text-cyan-300 transition-colors"
            title="Re-query IRSA cutouts"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        <form onSubmit={handleApplyCoords} className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] font-mono text-space-400 block mb-0.5">RA (deg)</label>
              <input
                type="text"
                value={raInput}
                onChange={(e) => setRaInput(e.target.value)}
                className="w-full bg-space-950 border border-space-700 rounded px-2 py-1 font-mono text-[11px] text-space-100 focus:outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono text-space-400 block mb-0.5">Dec (deg)</label>
              <input
                type="text"
                value={decInput}
                onChange={(e) => setDecInput(e.target.value)}
                className="w-full bg-space-950 border border-space-700 rounded px-2 py-1 font-mono text-[11px] text-space-100 focus:outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <div className="flex justify-between items-center pt-1">
            <button
              type="submit"
              className="px-3 py-1 bg-cyan-950 border border-cyan-500/50 hover:border-cyan-400 text-cyan-300 rounded font-mono text-[11px] font-medium transition-colors"
            >
              Update Viewport
            </button>
          </div>
        </form>

        {/* FOV Selector & Data Transfer Indicator */}
        <div className="mt-3 pt-2.5 border-t border-space-800">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[10px] font-mono text-space-400">Area Size (FOV)</span>
            <span className="text-[10px] font-mono text-cyan-400/90 flex items-center gap-1">
              <span>{fovTransferEstimates[fov].size}</span>
              <span className="text-space-500">•</span>
              <span>{fovTransferEstimates[fov].latency}</span>
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {(["1'", "3'", "5'", "10'"] as FOVOption[]).map((f) => (
              <button
                key={f}
                onClick={() => onUpdateFov(f)}
                className={`py-1 rounded font-mono text-[11px] border text-center transition-all ${
                  fov === f
                    ? 'bg-cyan-950/80 border-cyan-400 text-cyan-300 font-semibold shadow-[0_0_6px_rgba(0,242,254,0.2)]'
                    : 'bg-space-950 border-space-700 text-space-400 hover:border-space-600 hover:text-space-200'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. SPHEREx Detector Arrays & 102 Band Wavelengths */}
      <div className="p-3.5 border-b border-space-700/70">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 font-semibold text-space-100 font-telemetry uppercase tracking-wider text-[11px]">
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
            <span>Detector Arrays (1–6)</span>
          </div>
          <button
            onClick={() => {
              onSelectArray('all');
              onSelectChannel(null);
            }}
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
              selectedArray === 'all'
                ? 'bg-cyan-950 border-cyan-400 text-cyan-300'
                : 'bg-space-950 border-space-700 text-space-400 hover:text-space-200'
            }`}
          >
            Stacked SNR
          </button>
        </div>

        <div className="space-y-1.5">
          {DETECTOR_ARRAY_SPECS.map((spec) => {
            const isSelected = selectedArray === spec.id;
            return (
              <button
                key={spec.id}
                onClick={() => {
                  onSelectArray(spec.id as DetectorArrayId);
                  onSelectChannel(null);
                }}
                className={`w-full p-2 rounded border text-left flex items-center justify-between transition-all ${
                  isSelected
                    ? 'bg-space-800 border-cyan-400 text-space-100 shadow-[0_0_8px_rgba(0,242,254,0.15)]'
                    : 'bg-space-950/60 border-space-700/80 text-space-300 hover:border-space-600'
                }`}
              >
                <div>
                  <div className="font-mono text-[11px] font-semibold text-space-100 flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-cyan-400' : 'bg-space-600'}`} />
                    {spec.name}
                    <span className="text-[10px] text-space-400 font-normal">({spec.type})</span>
                  </div>
                  <div className="text-[10px] font-mono text-space-400 pl-3">
                    {spec.range} • {spec.res}
                  </div>
                </div>
                {isSelected && (
                  <span className="text-[9px] font-mono uppercase bg-cyan-950 text-cyan-300 px-1.5 py-0.5 rounded border border-cyan-500/40">
                    Active
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* 102 Band Discrete Slider */}
        <div className="mt-3 pt-2.5 border-t border-space-800">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-space-400">102-Band Channel</span>
            <span className="text-[10px] font-mono text-cyan-400">
              {selectedChannel ? `CH #${selectedChannel} (λ ≈ ${(0.75 + (selectedChannel / 102) * 4.25).toFixed(2)} µm)` : 'Broadband Stack'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min="1"
              max="102"
              value={selectedChannel || 51}
              onChange={(e) => onSelectChannel(parseInt(e.target.value, 10))}
              className="w-full accent-cyan-400 h-1.5 bg-space-800 rounded-lg cursor-pointer"
            />
            {selectedChannel && (
              <button
                onClick={() => onSelectChannel(null)}
                className="text-[10px] font-mono text-space-400 hover:text-amber-400 underline"
              >
                Reset
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 3. Subtraction & Background Processing */}
      <div className="p-3.5 border-b border-space-700/70">
        <div className="flex items-center gap-1.5 font-semibold text-space-100 font-telemetry uppercase tracking-wider text-[11px] mb-2">
          <Filter className="w-3.5 h-3.5 text-cyan-400" />
          <span>Background Subtraction</span>
        </div>

        <div className="space-y-1">
          {[
            {
              id: 'raw_calibrated',
              label: 'Raw Calibrated',
              desc: 'Level 2/3 cutout without spatial background model subtraction',
            },
            {
              id: 'zodi_reference_subtracted',
              label: 'ZODI + Median Subtracted',
              desc: 'Diffuse interplanetary dust emission & local median filtered',
            },
            {
              id: 'epoch_difference',
              label: 'Epoch Difference',
              desc: 'Target frame minus baseline epoch to isolate rapid transients',
            },
          ].map((mode) => {
            const isSelected = subtractionMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`w-full p-2 rounded border text-left transition-all ${
                  isSelected
                    ? 'bg-cyan-950/50 border-cyan-400 text-space-100'
                    : 'bg-space-950/40 border-space-700/60 text-space-300 hover:border-space-600'
                }`}
              >
                <div className="font-mono text-[11px] font-medium text-cyan-300 flex items-center justify-between">
                  <span>{mode.label}</span>
                  {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />}
                </div>
                <div className="text-[10px] text-space-400 mt-0.5 leading-tight font-sans">
                  {mode.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Known Object Cross-Check Overlays */}
      <div className="p-3.5">
        <div className="flex items-center gap-1.5 font-semibold text-space-100 font-telemetry uppercase tracking-wider text-[11px] mb-2">
          <Database className="w-3.5 h-3.5 text-cyan-400" />
          <span>Known Catalog Overlays</span>
        </div>

        <div className="space-y-2">
          <label className="flex items-center justify-between p-2 rounded bg-space-950/40 border border-space-700/60 cursor-pointer hover:border-space-600">
            <span className="font-mono text-[11px] text-space-200 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Gaia DR3 Astrometry
            </span>
            <input
              type="checkbox"
              checked={overlays.gaiaDr3}
              onChange={() => onToggleOverlay('gaiaDr3')}
              className="accent-cyan-400 rounded"
            />
          </label>

          <label className="flex items-center justify-between p-2 rounded bg-space-950/40 border border-space-700/60 cursor-pointer hover:border-space-600">
            <span className="font-mono text-[11px] text-space-200 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-orange-400" />
              AllWISE Point Sources
            </span>
            <input
              type="checkbox"
              checked={overlays.wise}
              onChange={() => onToggleOverlay('wise')}
              className="accent-cyan-400 rounded"
            />
          </label>

          <label className="flex items-center justify-between p-2 rounded bg-space-950/40 border border-space-700/60 cursor-pointer hover:border-space-600">
            <span className="font-mono text-[11px] text-space-200 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              Solar System Ephemeris (NEO)
            </span>
            <input
              type="checkbox"
              checked={overlays.solarSystemEphemeris}
              onChange={() => onToggleOverlay('solarSystemEphemeris')}
              className="accent-cyan-400 rounded"
            />
          </label>
        </div>

        <div className="mt-3 p-2 rounded bg-space-950/60 border border-space-800 text-[10px] text-space-400 flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 text-space-500 shrink-0 mt-0.5" />
          <span>Catalog markers prevent citizen volunteers from re-flagging recognized astronomical bodies.</span>
        </div>
      </div>
    </aside>
  );
};
