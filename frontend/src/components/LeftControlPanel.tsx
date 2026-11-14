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
  const [viewMode, setViewMode] = useState<'explorer' | 'scientist'>('explorer');
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
      {/* 0. Audience Level Toggle: Explorer vs Scientist */}
      <div className="p-2.5 border-b border-paper-800 bg-paper-950">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-paper-400 uppercase tracking-wider font-semibold">
            Telemetry Mode
          </span>
          <div className="flex rounded-lg border-2 border-black bg-paper-900 p-0.5 btn-tactile-sm">
            <button
              onClick={() => setViewMode('explorer')}
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'explorer'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
              title="Clean, intuitive labels for public & citizen science volunteers"
            >
              Explorer
            </button>
            <button
              onClick={() => setViewMode('scientist')}
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all cursor-pointer ${
                viewMode === 'scientist'
                  ? 'bg-emerald-400 text-gray-950'
                  : 'text-paper-400 hover:text-paper-200'
              }`}
              title="Full astrophysics metadata: wavelengths, resolving power, and FITS levels"
            >
              Scientist
            </button>
          </div>
        </div>
      </div>

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
            className="btn-tactile w-full py-2 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-lg font-mono text-[11px] font-bold border-2 border-black cursor-pointer mt-1"
          >
            Update Field
          </button>
        </form>

        {/* FOV Area Size */}
        <div className="mt-2.5 pt-2 border-t border-paper-800">
          <span className="text-[10px] font-mono text-paper-400 block mb-1">Field of View (FOV)</span>
          <div className="grid grid-cols-4 gap-1.5">
            {(["1'", "3'", "5'", "10'"] as FOVOption[]).map((f) => (
              <button
                key={f}
                onClick={() => onUpdateFov(f)}
                className={`btn-tactile-sm py-1 rounded-lg font-mono text-[11px] border-2 border-black transition-all cursor-pointer ${
                  fov === f
                    ? 'bg-emerald-400 text-gray-950 font-bold'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-100'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 2. SPHEREx Infrared Filter Bands */}
      <div className="p-3 border-b border-paper-800">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-emerald-400" />
            Infrared Filter
          </span>
          <button
            onClick={() => {
              onSelectArray('all');
              onSelectChannel(null);
            }}
            title="Combine all 6 infrared bands into a stacked composite image"
            className={`btn-tactile-sm text-[10px] font-mono px-2 py-0.5 rounded-lg border-2 border-black transition-all cursor-pointer ${
              selectedArray === 'all'
                ? 'bg-emerald-400 text-gray-950 font-bold'
                : 'bg-paper-950 border-black text-paper-400 hover:text-paper-100'
            }`}
          >
            All Bands
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
                className={`btn-tactile-sm w-full px-2.5 py-1.5 rounded-lg border-2 border-black text-left flex items-center justify-between transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-paper-800 text-paper-100 font-medium'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-200'
                }`}
                title={`Wavelength: ${spec.range} | ${spec.res}\n${spec.desc}`}
              >
                <div>
                  <div className="font-mono text-[11px] font-semibold text-paper-200 flex items-center gap-1.5">
                    <span>{spec.name}</span>
                    {viewMode === 'scientist' ? (
                      <span className="text-[10px] font-mono text-emerald-400 font-normal">
                        ({spec.range})
                      </span>
                    ) : (
                      <span className="text-[10px] font-sans font-normal text-paper-400">
                        ({spec.label})
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] font-mono text-paper-500">
                    {viewMode === 'scientist' ? (
                      <span className="text-paper-400">Resolving Power: {spec.res}</span>
                    ) : (
                      spec.desc
                    )}
                  </div>
                </div>
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Image Filtering & Movement Isolation */}
      <div className="p-3 border-b border-paper-800">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-2">
          <Filter className="w-3.5 h-3.5 text-emerald-400" />
          {viewMode === 'scientist' ? 'Background Subtraction Algorithm' : 'Image Filter'}
        </span>

        <div className="space-y-1.5">
          {[
            {
              id: 'raw_calibrated',
              label: viewMode === 'scientist' ? 'Level 2/3 Calibrated FITS' : 'Natural Sky (Raw)',
              desc: viewMode === 'scientist' ? 'Native flux in MJy/sr' : 'Standard telescope image',
            },
            {
              id: 'zodi_reference_subtracted',
              label: viewMode === 'scientist' ? 'Zodi Reference Subtracted' : 'Remove Dust Glare (Clean)',
              desc: viewMode === 'scientist' ? 'Diffuse interplanetary dust model removed' : 'Cuts out solar system dust haze',
            },
            {
              id: 'epoch_difference',
              label: viewMode === 'scientist' ? 'Epoch Difference (Δt Residual)' : 'Highlight Motion (Diff)',
              desc: viewMode === 'scientist' ? 'Temporal frame differencing' : 'Subtracts dates to spot moving dots',
            },
          ].map((mode) => {
            const isSelected = subtractionMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`btn-tactile-sm w-full px-2.5 py-1.5 rounded-lg border-2 border-black text-left transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-paper-800 text-emerald-300 font-semibold'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-100'
                }`}
                title={mode.desc}
              >
                <div className="font-mono text-[11px]">{mode.label}</div>
                <div className="text-[10px] text-paper-500 font-sans">{mode.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Known Astronomical Catalogs */}
      <div className="p-3">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-1.5">
          <Database className="w-3.5 h-3.5 text-emerald-400" />
          Known Catalog Overlays
        </span>

        <div className="space-y-1.5">
          <label className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-paper-950 border-2 border-black cursor-pointer hover:border-paper-700 btn-tactile-sm">
            <div>
              <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                Gaia DR3
              </span>
              <span className="text-[10px] text-paper-500 font-sans block">Known stars & coordinates</span>
            </div>
            <input
              type="checkbox"
              checked={overlays.gaiaDr3}
              onChange={() => onToggleOverlay('gaiaDr3')}
              className="accent-emerald-400 rounded cursor-pointer"
            />
          </label>

          <label className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-paper-950 border-2 border-black cursor-pointer hover:border-paper-700 btn-tactile-sm">
            <div>
              <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                AllWISE
              </span>
              <span className="text-[10px] text-paper-500 font-sans block">Known infrared sources</span>
            </div>
            <input
              type="checkbox"
              checked={overlays.wise}
              onChange={() => onToggleOverlay('wise')}
              className="accent-emerald-400 rounded cursor-pointer"
            />
          </label>
        </div>
      </div>
    </aside>
  );
};
