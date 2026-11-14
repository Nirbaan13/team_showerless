import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState, CandidateObject } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS, resolveCoordinateCatalogContext } from '../services/mockSpherexApi';
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
  viewMode?: 'volunteer' | 'scientist';
  searchStatus?: {
    source: 'live' | 'fallback' | 'preset';
    message: string;
  };
  activeCandidate?: CandidateObject | null;
  className?: string;
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
  viewMode = 'volunteer',
  searchStatus,
  activeCandidate,
  className = '',
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
    <aside className={`w-full md:w-64 bg-paper-900 border-r border-paper-800 flex flex-col h-full md:h-[calc(100vh-3rem)] text-xs overflow-y-auto select-none z-20 ${className}`}>
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

        {searchStatus && (
          <div className="mt-2 p-1.5 rounded-lg bg-paper-950 border border-paper-800 flex items-center gap-1.5 text-[10px] font-mono">
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                searchStatus.source === 'live'
                  ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]'
                  : searchStatus.source === 'preset'
                  ? 'bg-sky-400'
                  : 'bg-amber-400'
              }`}
            />
            <span className="truncate text-paper-300" title={searchStatus.message}>
              {searchStatus.source === 'live'
                ? 'NASA IRSA Live Stream'
                : searchStatus.source === 'preset'
                ? 'Benchmark Preset'
                : 'Offline Mock Fallback'}
            </span>
          </div>
        )}

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
              label: viewMode === 'scientist' ? 'Level 2/3 Aligned FITS' : 'Aligned Sky (Raw)',
              desc: viewMode === 'scientist' ? 'Gnomonic WCS aligned flux (MJy/sr)' : 'Standard telescope exposure',
            },
            {
              id: 'epoch_difference',
              label: viewMode === 'scientist' ? 'Per-Frame Difference (LOO Δt)' : 'Difference Image (Motion)',
              desc: viewMode === 'scientist' ? 'Leave-one-out median reference subtracted' : 'Subtracts static stars to reveal motion',
            },
            {
              id: 'bloom_mask',
              label: viewMode === 'scientist' ? 'BLOOM Bitmask Core Overlay' : 'BLOOM Mask (Bright Cores)',
              desc: viewMode === 'scientist' ? 'Detector saturation core flags (e.g. Vesta)' : 'Links bright saturated asteroid cores',
            },
            {
              id: 'zodi_reference_subtracted',
              label: viewMode === 'scientist' ? 'Zodi Reference Subtracted' : 'Remove Dust Glare (Clean)',
              desc: viewMode === 'scientist' ? 'Diffuse interplanetary dust model removed' : 'Cuts out solar system dust haze',
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

      {/* 4. Known Astronomical Catalogs (Dynamic per Target & Selected Object) */}
      {(() => {
        const coordCat = resolveCoordinateCatalogContext(ra, dec);
        const selCat = activeCandidate?.matchedCatalog || null;
        const selId =
          activeCandidate?.catalogId ||
          activeCandidate?.validationData?.objectName ||
          null;
        return (
          <div className="p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-emerald-400" />
                Known Catalog Overlays
              </span>
              <span className="text-[9px] font-mono text-emerald-400">
                {coordCat.constellation}
              </span>
            </div>

            {activeCandidate && (
              <div className="mb-2 px-2 py-1 rounded bg-paper-950 border border-paper-800 text-[9px] font-mono flex items-center justify-between gap-1">
                <span className="text-paper-400 truncate">
                  ★ Selected:{' '}
                  <strong className="text-white">
                    {activeCandidate.validationData?.objectName ||
                      activeCandidate.catalogId ||
                      activeCandidate.id}
                  </strong>
                </span>
                <span
                  className={`px-1.5 py-0.5 rounded shrink-0 font-bold ${
                    selCat
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                  }`}
                >
                  {selCat || 'Uncatalogued'}
                </span>
              </div>
            )}

            <div className="space-y-1.5">
              <label
                className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-paper-950 border-2 cursor-pointer transition-all btn-tactile-sm ${
                  selCat === 'Gaia DR3'
                    ? 'border-emerald-400/80 ring-1 ring-emerald-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <div className="min-w-0 pr-2">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                    <span>Gaia DR3 ({coordCat.gaiaSources.length})</span>
                    {selCat === 'Gaia DR3' && (
                      <span className="text-[8px] bg-emerald-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <span
                    className="text-[9px] text-emerald-300/90 font-mono block truncate"
                    title={selCat === 'Gaia DR3' && selId ? selId : coordCat.gaiaId}
                  >
                    {selCat === 'Gaia DR3' && selId ? `★ ${selId}` : coordCat.gaiaId}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={overlays.gaiaDr3}
                  onChange={() => onToggleOverlay('gaiaDr3')}
                  className="accent-emerald-400 rounded cursor-pointer shrink-0"
                />
              </label>

              <label
                className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-paper-950 border-2 cursor-pointer transition-all btn-tactile-sm ${
                  selCat === 'WISE'
                    ? 'border-amber-400/80 ring-1 ring-amber-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <div className="min-w-0 pr-2">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                    <span>AllWISE ({coordCat.wiseSources.length})</span>
                    {selCat === 'WISE' && (
                      <span className="text-[8px] bg-amber-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <span
                    className="text-[9px] text-amber-300/90 font-mono block truncate"
                    title={selCat === 'WISE' && selId ? selId : coordCat.wiseId}
                  >
                    {selCat === 'WISE' && selId ? `★ ${selId}` : coordCat.wiseId}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={overlays.wise}
                  onChange={() => onToggleOverlay('wise')}
                  className="accent-emerald-400 rounded cursor-pointer shrink-0"
                />
              </label>

              <label
                className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-paper-950 border-2 cursor-pointer transition-all btn-tactile-sm ${
                  selCat === 'NEO Ephemeris'
                    ? 'border-sky-400/80 ring-1 ring-sky-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <div className="min-w-0 pr-2">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-sky-400 shrink-0" />
                    <span>
                      JPL Ephemeris ({coordCat.ephemerisLabel || selCat === 'NEO Ephemeris' ? '1' : '0'})
                    </span>
                    {selCat === 'NEO Ephemeris' && (
                      <span className="text-[8px] bg-sky-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <span className="text-[9px] text-sky-300/90 font-mono block truncate">
                    {selCat === 'NEO Ephemeris' && selId
                      ? `★ ${selId}`
                      : coordCat.ephemerisLabel || 'No Solar System body in field'}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={overlays.solarSystemEphemeris}
                  onChange={() => onToggleOverlay('solarSystemEphemeris')}
                  className="accent-emerald-400 rounded cursor-pointer shrink-0"
                />
              </label>
            </div>
          </div>
        );
      })()}
    </aside>
  );
};
