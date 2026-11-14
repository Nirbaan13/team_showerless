import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS } from '../services/mockSpherexApi';
import { Search, Layers, Filter, Database } from 'lucide-react';

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
  selectedChannel: _selectedChannel,
  onSelectChannel,
  subtractionMode,
  onChangeSubtractionMode,
  overlays,
  onToggleOverlay,
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

  return (
    <aside className="w-64 bg-paper-900 border-r border-paper-800 flex flex-col h-[calc(100vh-3rem)] text-xs overflow-y-auto select-none z-20">
      {/* 1. Target Query */}
      <div className="p-3 border-b border-paper-800">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-2">
          <Search className="w-3.5 h-3.5 text-ochre-400" />
          Coordinates (J2000)
        </span>

        <form onSubmit={handleApplyCoords} className="space-y-2">
          <div className="grid grid-cols-2 gap-1.5">
            <div>
              <label className="text-[10px] font-mono text-paper-400 block mb-0.5">RA (deg)</label>
              <input
                type="text"
                value={raInput}
                onChange={(e) => setRaInput(e.target.value)}
                className="w-full bg-paper-950 border border-paper-800 rounded px-2 py-1 font-mono text-[11px] text-paper-100 focus:outline-none focus:border-ochre-400"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono text-paper-400 block mb-0.5">Dec (deg)</label>
              <input
                type="text"
                value={decInput}
                onChange={(e) => setDecInput(e.target.value)}
                className="w-full bg-paper-950 border border-paper-800 rounded px-2 py-1 font-mono text-[11px] text-paper-100 focus:outline-none focus:border-ochre-400"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full py-1.5 bg-ochre-400 hover:bg-ochre-300 text-paper-950 rounded font-mono text-[11px] font-semibold transition-colors"
          >
            Update Field
          </button>
        </form>

        {/* FOV Area Size */}
        <div className="mt-2.5 pt-2 border-t border-paper-800">
          <span className="text-[10px] font-mono text-paper-400 block mb-1">Field of View (FOV)</span>
          <div className="grid grid-cols-4 gap-1">
            {(["1'", "3'", "5'", "10'"] as FOVOption[]).map((f) => (
              <button
                key={f}
                onClick={() => onUpdateFov(f)}
                className={`py-1 rounded font-mono text-[11px] border transition-colors ${
                  fov === f
                    ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-semibold'
                    : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-100'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. SPHEREx Detector Arrays */}
      <div className="p-3 border-b border-paper-800">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-ochre-400" />
            Detector Band
          </span>
          <button
            onClick={() => {
              onSelectArray('all');
              onSelectChannel(null);
            }}
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded border transition-colors ${
              selectedArray === 'all'
                ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-semibold'
                : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-100'
            }`}
          >
            Stacked
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
                className={`w-full px-2 py-1.5 rounded border text-left flex items-center justify-between transition-colors ${
                  isSelected
                    ? 'bg-paper-800 border-ochre-400 text-paper-100'
                    : 'bg-paper-950 border-paper-800 text-paper-400 hover:border-paper-700 hover:text-paper-200'
                }`}
              >
                <div>
                  <div className="font-mono text-[11px] font-medium text-paper-200">
                    {spec.name}
                  </div>
                  <div className="text-[10px] font-mono text-paper-500">
                    {spec.range}
                  </div>
                </div>
                {isSelected && (
                  <span className="w-1.5 h-1.5 rounded-full bg-ochre-400" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Subtraction Mode */}
      <div className="p-3 border-b border-paper-800">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-1.5">
          <Filter className="w-3.5 h-3.5 text-ochre-400" />
          Background Subtraction
        </span>

        <div className="space-y-1">
          {[
            { id: 'raw_calibrated', label: 'Raw Calibrated FITS' },
            { id: 'zodi_reference_subtracted', label: 'Zodiacal Light Subtracted' },
            { id: 'epoch_difference', label: 'Epoch Difference Residual' },
          ].map((mode) => {
            const isSelected = subtractionMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`w-full px-2 py-1.5 rounded border text-left font-mono text-[11px] transition-colors ${
                  isSelected
                    ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-medium'
                    : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-100'
                }`}
              >
                {mode.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Known Astronomical Catalogs */}
      <div className="p-3">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-1.5">
          <Database className="w-3.5 h-3.5 text-ochre-400" />
          Catalog Overlays
        </span>

        <div className="space-y-1">
          <label className="flex items-center justify-between px-2 py-1.5 rounded bg-paper-950 border border-paper-800 cursor-pointer hover:border-paper-700">
            <span className="font-mono text-[11px] text-paper-300 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Gaia DR3
            </span>
            <input
              type="checkbox"
              checked={overlays.gaiaDr3}
              onChange={() => onToggleOverlay('gaiaDr3')}
              className="accent-amber-500 rounded"
            />
          </label>

          <label className="flex items-center justify-between px-2 py-1.5 rounded bg-paper-950 border border-paper-800 cursor-pointer hover:border-paper-700">
            <span className="font-mono text-[11px] text-paper-300 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              AllWISE
            </span>
            <input
              type="checkbox"
              checked={overlays.wise}
              onChange={() => onToggleOverlay('wise')}
              className="accent-amber-500 rounded"
            />
          </label>
        </div>
      </div>
    </aside>
  );
};
