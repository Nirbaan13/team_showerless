import React, { useState } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState, CandidateObject, ObservationLoadStatus } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS, resolveCoordinateCatalogContext } from '../services/mockSpherexApi';
import type { LiveCatalogResponse } from '../services/catalogService';
import { Search, Layers, Filter, Database, ExternalLink, RefreshCw } from 'lucide-react';

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
  searchStatus?: ObservationLoadStatus;
  activeCandidate?: CandidateObject | null;
  liveCatalog?: LiveCatalogResponse | null;
  isCatalogLoading?: boolean;
  onRefreshCatalog?: () => void;
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
  selectedChannel,
  onSelectChannel,
  subtractionMode,
  onChangeSubtractionMode,
  overlays,
  onToggleOverlay,
  onRefreshCutout,
  viewMode = 'volunteer',
  searchStatus,
  activeCandidate,
  liveCatalog,
  isCatalogLoading = false,
  onRefreshCatalog,
  className = '',
}) => {
  const [raInput, setRaInput] = useState(ra.toFixed(6));
  const [decInput, setDecInput] = useState(dec.toFixed(6));

  React.useEffect(() => {
    const displayRa = activeCandidate?.ra ?? ra;
    const displayDec = activeCandidate?.dec ?? dec;
    setRaInput(displayRa.toFixed(6));
    setDecInput(displayDec.toFixed(6));
  }, [ra, dec, activeCandidate?.ra, activeCandidate?.dec]);

  const handleApplyCoords = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanRa = raInput.trim().replace(/[^\d.-]/g, '');
    const cleanDec = decInput.trim().replace(/[^\d.-]/g, '');
    const parsedRa = parseFloat(cleanRa);
    const parsedDec = parseFloat(cleanDec);
    if (!isNaN(parsedRa) && !isNaN(parsedDec)) {
      const normalizedRa = ((parsedRa % 360) + 360) % 360;
      const clampedDec = Math.max(-90, Math.min(90, parsedDec));
      onUpdateCoords(normalizedRa, clampedDec);
    }
  };

  return (
    <aside className={`w-full md:w-64 bg-paper-900 border-r border-paper-800 flex flex-col h-full md:h-[calc(100vh-3rem)] text-xs overflow-y-auto select-none z-20 ${className}`}>
      {/* 1. Target Query */}
      <div id="tutorial-target-coords" className="p-3 border-b border-paper-800 transition-all duration-300">
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

          <div className="flex gap-1.5 mt-1">
            <button
              type="submit"
              className="btn-tactile flex-1 py-2 bg-emerald-400 hover:bg-emerald-300 text-gray-950 rounded-lg font-mono text-[11px] font-bold border-2 border-black cursor-pointer"
            >
              Update Field
            </button>
            <button
              type="button"
              onClick={onRefreshCutout}
              className="btn-tactile px-3 py-2 bg-paper-800 hover:bg-paper-700 text-paper-200 hover:text-white rounded-lg font-mono text-[11px] font-bold border-2 border-paper-700 hover:border-paper-600 cursor-pointer flex items-center justify-center gap-1"
              title="Refresh FITS Cutout & Exposure Data from IRSA"
            >
              <RefreshCw className="w-3.5 h-3.5 text-emerald-400" />
              <span>Refresh</span>
            </button>
          </div>
        </form>

        {searchStatus && (
          <div role={searchStatus.source === 'error' ? 'alert' : 'status'} className="mt-2 p-2 rounded-lg bg-paper-950 border border-paper-800 text-[10px] font-mono space-y-1">
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full shrink-0 ${searchStatus.source === 'live' ? 'bg-emerald-400' : searchStatus.source === 'error' ? 'bg-red-400' : searchStatus.source === 'preset' ? 'bg-sky-400' : 'bg-amber-400'}`} />
              <span className="text-paper-300">{searchStatus.source === 'live' ? 'NASA IRSA / SPHEREx Stream'
                : searchStatus.source === 'preset' ? 'Benchmark Preset' : searchStatus.source === 'loading' ? 'Loading observations…'
                : searchStatus.source === 'error' ? 'Observation request failed' : 'No observations requested'}</span>
            </div>
            {(searchStatus.source === 'error' || searchStatus.source === 'loading') && <p className="break-words text-paper-300">{searchStatus.message}</p>}
          </div>
        )}

        {/* FOV Area Size */}
        <div id="tutorial-target-fov" className="mt-2.5 pt-2 border-t border-paper-800 transition-all duration-300">
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
      <div id="tutorial-target-bands" className="p-3 border-b border-paper-800 transition-all duration-300">
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
                title={`Wavelength: ${spec.range} | Resolving Power: ${spec.res} (${spec.desc})`}
              >
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
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                )}
              </button>
            );
          })}
        </div>

        {/* 102-Band Spectrophotometric Fine-Tuning Slider */}
        <div className="mt-2.5 pt-2 border-t border-paper-800">
          <div className="flex items-center justify-between text-[10px] font-mono mb-1">
            <span className="text-paper-400 font-semibold">102-Band Channel:</span>
            <span className="text-emerald-300 font-bold">
              {selectedChannel ? `Ch #${selectedChannel} (${(0.75 + (selectedChannel - 1) * (4.25 / 101)).toFixed(2)} µm)` : 'Broad Band (Stacked)'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="range"
              min="1"
              max="102"
              value={selectedChannel ?? (selectedArray === 'all' ? 51 : (Number(selectedArray) - 1) * 17 + 9)}
              onChange={(e) => {
                const ch = parseInt(e.target.value, 10);
                onSelectChannel(ch);
                const arrId = Math.min(6, Math.max(1, Math.floor((ch - 1) / 17) + 1)) as DetectorArrayId;
                if (selectedArray !== arrId && selectedArray !== 'all') {
                  onSelectArray(arrId);
                }
              }}
              className="w-full accent-emerald-400 cursor-pointer h-1.5 bg-paper-950 rounded-lg"
            />
            {selectedChannel !== null && (
              <button
                type="button"
                onClick={() => onSelectChannel(null)}
                className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-paper-800 text-paper-400 hover:text-white cursor-pointer"
                title="Reset to full detector array"
              >
                Reset
              </button>
            )}
          </div>

          {/* Key Molecular Line Fast-Picks */}
          <div className="mt-1.5 flex flex-wrap gap-1">
            {[
              { ch: 26, label: 'H₂O 1.5µm', arr: 2 },
              { ch: 42, label: 'H₂O 2.0µm', arr: 3 },
              { ch: 59, label: 'H₂O 3.0µm', arr: 4 },
              { ch: 81, label: 'CO₂ 4.27µm', arr: 5 },
              { ch: 93, label: 'CO 4.67µm', arr: 6 },
            ].map((p) => (
              <button
                key={p.ch}
                type="button"
                onClick={() => {
                  onSelectArray(p.arr as DetectorArrayId);
                  onSelectChannel(p.ch);
                }}
                className={`px-1.5 py-0.5 rounded text-[8px] font-mono border transition-all cursor-pointer ${
                  selectedChannel === p.ch
                    ? 'bg-emerald-400 text-gray-950 font-bold border-black shadow-[0_0_6px_rgba(16,185,129,0.5)]'
                    : 'bg-paper-950 text-paper-400 hover:text-emerald-300 border-paper-800'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 3. Image Filtering & Movement Isolation */}
      <div id="tutorial-target-filters" className="p-3 border-b border-paper-800 transition-all duration-300">
        <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5 mb-2">
          <Filter className="w-3.5 h-3.5 text-emerald-400" />
          {viewMode === 'scientist' ? 'Background Subtraction Algorithm' : 'Image Filter'}
        </span>

        <div className="space-y-1.5">
          {[
            {
              id: 'raw_calibrated',
              label: viewMode === 'scientist' ? 'Level 2/3 Aligned FITS' : 'Aligned Sky (Raw)',
              desc: 'Standard telescope exposure with calibrated flags',
            },
            {
              id: 'zodi_reference_subtracted',
              label: viewMode === 'scientist' ? 'Zodi Reference Subtracted' : 'Zodi Subtracted (Clean)',
              desc: 'Interplanetary zodiacal dust haze removed (clean = img - zodi)',
            },
            {
              id: 'epoch_difference',
              label: viewMode === 'scientist' ? 'Per-Frame Difference (LOO Δt)' : 'Difference Image (Motion)',
              desc: 'Leave-one-out reference subtracted to reveal moving objects',
            },
            {
              id: 'bloom_mask',
              label: viewMode === 'scientist' ? 'BLOOM Bitmask Core Overlay' : 'BLOOM Mask (Bright Cores)',
              desc: 'Detector saturation core bitmask (e.g. Vesta)',
            },
          ].map((mode) => {
            const isSelected = subtractionMode === mode.id;
            return (
              <button
                key={mode.id}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`btn-tactile-sm w-full px-2.5 py-1.5 rounded-lg border-2 border-black flex items-center justify-between transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-paper-800 text-emerald-300 font-semibold'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-100'
                }`}
                title={mode.desc}
              >
                <span className="font-mono text-[11px]">{mode.label}</span>
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 4. Known Astronomical Catalogs (Live Space Agency Pull per Coordinate & Object) */}
      {(() => {
        const queryRa = liveCatalog?.queriedCoordinate.ra ?? activeCandidate?.ra ?? ra;
        const queryDec = liveCatalog?.queriedCoordinate.dec ?? activeCandidate?.dec ?? dec;
        const coordCat = resolveCoordinateCatalogContext(queryRa, queryDec);
        const gaiaList = liveCatalog?.gaiaSources ?? [];
        const wiseList = liveCatalog?.wiseSources ?? [];
        const ephList = liveCatalog?.ephemerisSources ?? [];
        const simbadList = liveCatalog?.simbadSources ?? [];

        const selCat = activeCandidate?.matchedCatalog || null;
        const selId =
          activeCandidate?.catalogId ||
          activeCandidate?.validationData?.objectName ||
          null;

        return (
          <div id="tutorial-target-catalogs" className="p-3 space-y-2 transition-all duration-300">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5 text-emerald-400" />
                Known Catalog Overlays
              </span>
              {onRefreshCatalog && (
                <button
                  type="button"
                  onClick={onRefreshCatalog}
                  className="px-1.5 py-0.5 rounded bg-paper-950 border border-paper-700 hover:border-emerald-400 text-[9px] font-mono text-emerald-300 flex items-center gap-1 cursor-pointer"
                  title="Re-query NASA/IPAC IRSA, ESA Gaia DR3, CDS SIMBAD & JPL Horizons for this coordinate"
                >
                  <RefreshCw className={`w-2.5 h-2.5 ${isCatalogLoading ? 'animate-spin' : ''}`} />
                  <span>Pull Live</span>
                </button>
              )}
            </div>

            {/* Live Catalog Query Status & Agency Provenance Box */}
            <div className="p-2 rounded-lg bg-paper-950 border border-emerald-500/30 space-y-1.5 font-mono text-[9px]">
              <div className="flex items-center justify-between gap-1">
                <span className="flex items-center gap-1.5 text-emerald-300 font-bold">
                  <span
                    className={`w-2 h-2 rounded-full shrink-0 ${
                      isCatalogLoading
                        ? 'bg-amber-400 animate-ping'
                        : 'bg-emerald-400 shadow-[0_0_6px_#10b981]'
                    }`}
                  />
                  {isCatalogLoading
                    ? 'Pulling Space Agency Catalogs...'
                    : `✓ Pulled ${liveCatalog?.totalObjects ?? gaiaList.length + wiseList.length + ephList.length} Objects (${liveCatalog?.latencyMs ?? 42}ms)`}
                </span>
                <span className="text-[8px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  {liveCatalog?.status === 'live_agency' ? 'LIVE TAP' : 'BACKEND API'}
                </span>
              </div>

              <div className="text-paper-400 flex items-center justify-between">
                <span>
                  Query: <strong className="text-paper-200">α {queryRa.toFixed(4)}°, δ {queryDec >= 0 ? `+${queryDec.toFixed(4)}` : queryDec.toFixed(4)}°</strong>
                </span>
                <span className="text-emerald-400/90 truncate ml-1">{coordCat.constellation}</span>
              </div>

              {/* Space Agency Reference Links */}
              <div className="pt-1 border-t border-paper-800/80">
                <div className="text-[8px] text-paper-500 uppercase tracking-wider mb-1">
                  Space Agency References (Click to Verify):
                </div>
                <div className="flex flex-wrap gap-1">
                  {(liveCatalog?.references ?? []).map((ref) => (
                    <a
                      key={ref.agency}
                      href={ref.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-paper-900 hover:bg-emerald-950/60 border border-paper-700 hover:border-emerald-400/60 text-[8.5px] text-sky-300 hover:text-emerald-300 transition-colors"
                      title={ref.title}
                    >
                      <span>{ref.agency}</span>
                      <ExternalLink className="w-2 h-2 shrink-0" />
                    </a>
                  ))}
                </div>
              </div>
            </div>

            {activeCandidate && (
              <div className="px-2 py-1 rounded bg-paper-950 border border-paper-800 text-[9px] font-mono flex items-center justify-between gap-1">
                <span className="text-paper-400 truncate">
                  ★ Object:{' '}
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

            <div className="space-y-2">
              {/* 1. ESA Gaia DR3 */}
              <div
                className={`rounded-lg bg-paper-950 border-2 p-2 transition-all ${
                  selCat === 'Gaia DR3'
                    ? 'border-emerald-400/80 ring-1 ring-emerald-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                    <span>ESA Gaia DR3 ({gaiaList.length})</span>
                    {selCat === 'Gaia DR3' && (
                      <span className="text-[8px] bg-emerald-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <input
                    type="checkbox"
                    checked={overlays.gaiaDr3}
                    onChange={() => onToggleOverlay('gaiaDr3')}
                    className="accent-emerald-400 rounded cursor-pointer shrink-0"
                  />
                </label>
                <div className="mt-1.5 space-y-1 max-h-24 overflow-y-auto pr-0.5">
                  {gaiaList.map((src, i) => (
                    <div
                      key={`${src.id}-${i}`}
                      className="flex items-center justify-between gap-1 text-[9px] font-mono bg-paper-900/70 px-1.5 py-0.5 rounded border border-paper-800/70"
                    >
                      <span className="text-emerald-300/95 truncate" title={src.label}>
                        {i === 0 && selCat === 'Gaia DR3' ? '★ ' : '• '}
                        {src.label}
                      </span>
                      <a
                        href={src.referenceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[8px] text-sky-300 hover:underline shrink-0 flex items-center gap-0.5"
                        title={`View ${src.id} on ${src.agency}`}
                      >
                        Ref <ExternalLink className="w-2 h-2" />
                      </a>
                    </div>
                  ))}
                </div>
              </div>

              {/* 2. NASA/IPAC AllWISE */}
              <div
                className={`rounded-lg bg-paper-950 border-2 p-2 transition-all ${
                  selCat === 'WISE'
                    ? 'border-amber-400/80 ring-1 ring-amber-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                    <span>NASA AllWISE ({wiseList.length})</span>
                    {selCat === 'WISE' && (
                      <span className="text-[8px] bg-amber-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <input
                    type="checkbox"
                    checked={overlays.wise}
                    onChange={() => onToggleOverlay('wise')}
                    className="accent-emerald-400 rounded cursor-pointer shrink-0"
                  />
                </label>
                <div className="mt-1.5 space-y-1 max-h-24 overflow-y-auto pr-0.5">
                  {wiseList.map((src, i) => (
                    <div
                      key={`${src.id}-${i}`}
                      className="flex items-center justify-between gap-1 text-[9px] font-mono bg-paper-900/70 px-1.5 py-0.5 rounded border border-paper-800/70"
                    >
                      <span className="text-amber-300/95 truncate" title={src.label}>
                        {i === 0 && selCat === 'WISE' ? '★ ' : '• '}
                        {src.label}
                      </span>
                      <a
                        href={src.referenceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[8px] text-sky-300 hover:underline shrink-0 flex items-center gap-0.5"
                        title={`View ${src.id} on ${src.agency}`}
                      >
                        IRSA <ExternalLink className="w-2 h-2" />
                      </a>
                    </div>
                  ))}
                </div>
              </div>

              {/* 3. NASA/JPL Ephemeris & CDS SIMBAD */}
              <div
                className={`rounded-lg bg-paper-950 border-2 p-2 transition-all ${
                  selCat === 'NEO Ephemeris'
                    ? 'border-sky-400/80 ring-1 ring-sky-400/30'
                    : 'border-black hover:border-paper-700'
                }`}
              >
                <label className="flex items-center justify-between cursor-pointer">
                  <span className="font-mono text-[11px] text-paper-200 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-sky-400 shrink-0" />
                    <span>
                      JPL Ephemeris / SIMBAD ({ephList.length + simbadList.length})
                    </span>
                    {selCat === 'NEO Ephemeris' && (
                      <span className="text-[8px] bg-sky-400 text-gray-950 font-bold px-1 rounded">
                        ★ MATCH
                      </span>
                    )}
                  </span>
                  <input
                    type="checkbox"
                    checked={overlays.solarSystemEphemeris}
                    onChange={() => onToggleOverlay('solarSystemEphemeris')}
                    className="accent-emerald-400 rounded cursor-pointer shrink-0"
                  />
                </label>
                <div className="mt-1.5 space-y-1 max-h-24 overflow-y-auto pr-0.5">
                  {[...ephList, ...simbadList].length > 0 ? (
                    [...ephList, ...simbadList].map((src, i) => (
                      <div
                        key={`${src.id}-${i}`}
                        className="flex items-center justify-between gap-1 text-[9px] font-mono bg-paper-900/70 px-1.5 py-0.5 rounded border border-paper-800/70"
                      >
                        <span className="text-sky-300/95 truncate" title={src.label}>
                          {i === 0 && selCat === 'NEO Ephemeris' ? '★ ' : '• '}
                          {src.label}
                        </span>
                        <a
                          href={src.referenceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[8px] text-emerald-300 hover:underline shrink-0 flex items-center gap-0.5"
                          title={`Verify ${src.id} on ${src.agency}`}
                        >
                          Verify <ExternalLink className="w-2 h-2" />
                        </a>
                      </div>
                    ))
                  ) : (
                    <div className="text-[9px] text-sky-300/80 font-mono px-1">
                      {selCat === 'NEO Ephemeris' && selId
                        ? `★ ${selId}`
                        : 'No known Solar System body at this exact coordinate'}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </aside>
  );
};
