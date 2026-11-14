import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS } from '../services/mockSpherexApi';
import { Layers, Search, Filter, Database, Info, RefreshCw } from 'lucide-react';

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

  const fovTransferEstimates: Record<FOVOption, { size: string; latency: string }> = {
    "1'": { size: '120 KB', latency: '0.2s' },
    "3'": { size: '980 KB', latency: '0.5s' },
    "5'": { size: '2.8 MB', latency: '1.1s' },
    "10'": { size: '11.2 MB', latency: '3.4s' },
  };

  return (
    <aside className="w-72 bg-nasa-surface border-r border-nasa-border flex flex-col h-[calc(100vh-3rem)] text-xs overflow-y-auto select-none z-20">
      {/* 1. Target Query Section */}
      <div className="p-3 border-b border-nasa-border">
        <div className="flex items-center justify-between mb-2">
          <span className="font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5 text-blue-400" />
            Target Coordinates (J2000)
          </span>
          <button
            onClick={onRefreshCutout}
            className="p-1 rounded hover:bg-nasa-dark text-nasa-textMuted hover:text-blue-400 transition-colors"
            title="Reload IRSA cutout"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        <form onSubmit={handleApplyCoords} className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] font-mono text-nasa-textMuted block mb-0.5">RA (deg)</label>
              <input
                type="text"
                value={raInput}
                onChange={(e) => setRaInput(e.target.value)}
                className="w-full bg-nasa-dark border border-nasa-border rounded px-2 py-1 font-mono text-[11px] text-nasa-textMain focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono text-nasa-textMuted block mb-0.5">Dec (deg)</label>
              <input
                type="text"
                value={decInput}
                onChange={(e) => setDecInput(e.target.value)}
                className="w-full bg-nasa-dark border border-nasa-border rounded px-2 py-1 font-mono text-[11px] text-nasa-textMain focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="flex justify-between items-center pt-1">
            <button
              type="submit"
              className="w-full py-1 bg-nasa-blue text-white rounded font-mono text-[11px] font-medium hover:bg-blue-600 transition-colors"
            >
              Update Viewport
            </button>
          </div>
        </form>

        {/* FOV Area Size */}
        <div className="mt-3 pt-2 border-t border-nasa-border">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-nasa-textMuted">Cutout Size (FOV)</span>
            <span className="text-[10px] font-mono text-nasa-textMuted">
              {fovTransferEstimates[fov].size} • {fovTransferEstimates[fov].latency}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1">
            {(["1'", "3'", "5'", "10'"] as FOVOption[]).map((f) => (
              <button
                key={f}
                onClick={() => onUpdateFov(f)}
                className={`py-1 rounded font-mono text-[11px] border text-center transition-colors ${
                  fov === f
                    ? 'bg-blue-900/50 border-blue-500 text-blue-200 font-semibold'
                    : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:border-nasa-subtle hover:text-nasa-textMain'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. SPHEREx Detector Arrays & Spectral Bands */}
      <div className="p-3 border-b border-nasa-border">
        <div className="flex items-center justify-between mb-2">
          <span className="font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-blue-400" />
            Detector Array
          </span>
          <button
            onClick={() => {
              onSelectArray('all');
              onSelectChannel(null);
            }}
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
              selectedArray === 'all'
                ? 'bg-blue-900/50 border-blue-500 text-blue-200'
                : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:text-nasa-textMain'
            }`}
          >
            Stacked SNR
          </button>
        </div>

        <div className="space-y-1">
          {DETECTOR_ARRAY_SPECS.map((spec) => {
            const isSelected = selectedArray === spec.id;
            return (
              <button
                key={spec.id}
                onClick={() => {
                  onSelectArray(spec.id as DetectorArrayId);
                  onSelectChannel(null);
                }}
                className={`w-full p-1.5 rounded border text-left flex items-center justify-between transition-colors ${
                  isSelected
                    ? 'bg-blue-950/40 border-blue-500 text-blue-100'
                    : 'bg-nasa-dark/60 border-nasa-border text-nasa-textMuted hover:border-nasa-subtle hover:text-nasa-textMain'
                }`}
              >
                <div>
                  <div className="font-mono text-[11px] font-medium text-nasa-textMain">
                    {spec.name} <span className="text-[10px] text-nasa-textMuted font-normal">({spec.type})</span>
                  </div>
                  <div className="text-[10px] font-mono text-nasa-textMuted">
                    {spec.range}
                  </div>
                </div>
                {isSelected && (
                  <span className="text-[9px] font-mono uppercase bg-blue-900/60 text-blue-200 px-1 py-0.5 rounded">
                    Selected
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* 102 Band Scrubber */}
        <div className="mt-2.5 pt-2 border-t border-nasa-border">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-nasa-textMuted">Band Channel</span>
            <span className="text-[10px] font-mono text-blue-300">
              {selectedChannel ? `CH #${selectedChannel} (${(0.75 + (selectedChannel / 102) * 4.25).toFixed(2)} µm)` : 'All Array Bands'}
            </span>
          </div>
          <input
            type="range"
            min="1"
            max="102"
            value={selectedChannel || 51}
            onChange={(e) => onSelectChannel(parseInt(e.target.value, 10))}
            className="w-full accent-blue-500 h-1 bg-nasa-border rounded cursor-pointer"
          />
        </div>
      </div>

      {/* 3. Subtraction Mode */}
      <div className="p-3 border-b border-nasa-border">
        <div className="flex items-center gap-1.5 font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] mb-2">
          <Filter className="w-3.5 h-3.5 text-blue-400" />
          <span>Background Processing</span>
        </div>

        <div className="space-y-1">
          {[
            {
              id: 'raw_calibrated',
              label: 'Raw Calibrated FITS',
              desc: 'Calibrated spectral image cutout without spatial background removal',
            },
            {
              id: 'zodi_reference_subtracted',
              label: 'Zodiacal Light Subtracted',
              desc: 'Median background & zodiacal emission model removed',
            },
            {
              id: 'epoch_difference',
              label: 'Epoch Difference Residual',
              desc: 'Subtracted against baseline epoch to highlight moving bodies',
            },
          ].map((mode) => {
            const isSelected = subtractionMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`w-full p-2 rounded border text-left transition-colors ${
                  isSelected
                    ? 'bg-blue-950/40 border-blue-500 text-nasa-textMain'
                    : 'bg-nasa-dark/60 border-nasa-border text-nasa-textMuted hover:border-nasa-subtle'
                }`}
              >
                <div className="font-mono text-[11px] font-medium text-blue-300">
                  {mode.label}
                </div>
                <div className="text-[10px] text-nasa-textMuted mt-0.5 leading-tight">
                  {mode.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Known Astronomical Catalogs */}
      <div className="p-3">
        <div className="flex items-center gap-1.5 font-semibold text-nasa-textMain uppercase tracking-wider text-[11px] mb-2">
          <Database className="w-3.5 h-3.5 text-blue-400" />
          <span>Catalog Overlays</span>
        </div>

        <div className="space-y-1.5">
          <label className="flex items-center justify-between p-1.5 rounded bg-nasa-dark/60 border border-nasa-border cursor-pointer hover:border-nasa-subtle">
            <span className="font-mono text-[11px] text-nasa-textMain flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Gaia DR3 Astrometry
            </span>
            <input
              type="checkbox"
              checked={overlays.gaiaDr3}
              onChange={() => onToggleOverlay('gaiaDr3')}
              className="accent-blue-500 rounded"
            />
          </label>

          <label className="flex items-center justify-between p-1.5 rounded bg-nasa-dark/60 border border-nasa-border cursor-pointer hover:border-nasa-subtle">
            <span className="font-mono text-[11px] text-nasa-textMain flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              AllWISE Infrared Sources
            </span>
            <input
              type="checkbox"
              checked={overlays.wise}
              onChange={() => onToggleOverlay('wise')}
              className="accent-blue-500 rounded"
            />
          </label>

          <label className="flex items-center justify-between p-1.5 rounded bg-nasa-dark/60 border border-nasa-border cursor-pointer hover:border-nasa-subtle">
            <span className="font-mono text-[11px] text-nasa-textMain flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-400" />
              Solar System Ephemeris
            </span>
            <input
              type="checkbox"
              checked={overlays.solarSystemEphemeris}
              onChange={() => onToggleOverlay('solarSystemEphemeris')}
              className="accent-blue-500 rounded"
            />
          </label>
        </div>

        <div className="mt-3 p-2 rounded bg-nasa-dark border border-nasa-border text-[10px] text-nasa-textMuted flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 text-nasa-textMuted shrink-0 mt-0.5" />
          <span>Cross-references positions with standard catalogs to prevent duplicate discovery flags.</span>
        </div>
      </div>
    </aside>
  );
};
