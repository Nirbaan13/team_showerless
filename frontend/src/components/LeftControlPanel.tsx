import { DEMO_REAL_ONLY } from '../lib/demoMode';
import React, { useState } from 'react';
import { OBSERVATION_ERA_PRESETS, type ObservationEraSpec } from '../services/spherexBackendApi';
import { DEFAULT_ARCHIVE, isArchiveBrowse, observationBounds, type ArchiveSelection, type ArchiveInventory } from '../services/archiveObservationsApi';
import type { FOVOption, DetectorArrayId, SubtractionMode, CatalogOverlayState, CandidateObject, SpherexEpochFrame } from '../types/spherex';
import { DETECTOR_ARRAY_SPECS, getDetectorCoverageForTarget } from '../services/mockSpherexApi';
import type { LiveCatalogResponse } from '../services/catalogService';
import { Search, Layers, Filter, Database, ExternalLink, RefreshCw, AlertTriangle, ChevronDown } from 'lucide-react';

interface LeftControlPanelProps {
  ra: number;
  dec: number;
  fov: FOVOption;
  onUpdateCoords: (ra: number, dec: number, archive?: ArchiveSelection) => void;
  archiveSelection?: ArchiveSelection;
  archiveInventory?: ArchiveInventory[];
  archiveInventoryError?: string;
  onUpdateFov: (fov: FOVOption) => void;
  selectedArray: DetectorArrayId | 'all';
  onSelectArray: (arr: DetectorArrayId | 'all') => void;
  subtractionMode: SubtractionMode;
  availableModes: SubtractionMode[];
  onChangeSubtractionMode: (mode: SubtractionMode) => void;
  overlays: CatalogOverlayState;
  onToggleOverlay: (key: keyof CatalogOverlayState) => void;
  onRefreshCutout: () => void;
  viewMode?: 'volunteer' | 'scientist';
  searchStatus?: {
    source: 'live' | 'fallback' | 'preset' | 'loading' | 'error' | 'idle' | 'archive' | 'packaged';
    message: string;
  };
  activeCandidate?: CandidateObject | null;
  liveCatalog?: LiveCatalogResponse | null;
  isCatalogLoading?: boolean;
  onRefreshCatalog?: () => void;
  currentPresetId?: string | null;
  frames?: SpherexEpochFrame[];
  className?: string;
}

export const LeftControlPanel: React.FC<LeftControlPanelProps> = ({
  ra,
  dec,
  fov,
  onUpdateCoords,
  archiveSelection = DEFAULT_ARCHIVE,
  archiveInventory = [],
  archiveInventoryError = '',
  onUpdateFov,
  selectedArray,
  onSelectArray,
  subtractionMode,
  availableModes,
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
  currentPresetId,
  frames,
  className = '',
}) => {
  const [raInput, setRaInput] = useState(ra.toFixed(6));
  const [decInput, setDecInput] = useState(dec.toFixed(6));
  const [coordError, setCoordError] = useState<string | null>(null);
  const [archiveDraft, setArchiveDraft] = useState(archiveSelection);
  React.useEffect(() => setArchiveDraft(archiveSelection), [archiveSelection]);
  const archiveBrowse = isArchiveBrowse(archiveDraft);
  const selectedIds = archiveDraft.provider.split(',').filter(Boolean);
  const selectedProviders = selectedIds.map(id => archiveInventory.find(item => item.id === id));
  const imageProviders = archiveInventory.filter(item => item.capabilities.availability === 'available' && item.capabilities.product_kinds.includes('image') && (item.capabilities.original || item.capabilities.cutout));
  const allProviderIds = imageProviders.map(item => item.id).join(',');
  const eraSelection = (era: ObservationEraSpec): ArchiveSelection => ({
    provider: (era.id === 'all' ? imageProviders.map(item => item.id) : era.providers.filter(id => imageProviders.some(item => item.id === id))).join(','),
    from: era.timeStartUtc?.slice(0, 10) || '',
    through: era.timeEndUtc ? new Date(Date.parse(era.timeEndUtc) - 1).toISOString().slice(0, 10) : '',
  });

  const detectorCoverage = React.useMemo(() => {
    return getDetectorCoverageForTarget(currentPresetId || null, frames);
  }, [currentPresetId, frames]);

  React.useEffect(() => {
    const displayRa = activeCandidate?.ra ?? ra;
    const displayDec = activeCandidate?.dec ?? dec;
    setRaInput(displayRa.toFixed(6));
    setDecInput(displayDec.toFixed(6));
    setCoordError(null);
  }, [ra, dec, activeCandidate?.ra, activeCandidate?.dec]);

  const handleApplyCoords = (e: React.FormEvent) => {
    e.preventDefault();
    const decimal = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;
    const parsedRa = Number(raInput.trim());
    const parsedDec = Number(decInput.trim());
    if (!decimal.test(raInput.trim()) || !decimal.test(decInput.trim()) || !Number.isFinite(parsedRa) || !Number.isFinite(parsedDec)) {
      setCoordError('Enter valid numerical coordinates');
      return;
    }
    if (parsedDec < -90 || parsedDec > 90) {
      setCoordError('Declination must be between -90° and +90°');
      return;
    }
    try { observationBounds(archiveDraft); } catch (error) {
      setCoordError(error instanceof Error ? error.message : 'Invalid observation dates'); return;
    }
    if (archiveBrowse && (!selectedIds.length || selectedProviders.some(item => !item))) { setCoordError('Archive inventory is unavailable. Retry when the source can be verified.'); return; }
    setCoordError(null);
    const normalizedRa = ((parsedRa % 360) + 360) % 360;
    onUpdateCoords(normalizedRa, parsedDec, archiveDraft);
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
              <label htmlFor="field-ra" className="text-[10px] font-mono text-paper-400 block mb-0.5">RA (deg)</label>
              <input
                id="field-ra"
                aria-invalid={!!coordError}
                aria-describedby="coordinate-hint coordinate-error"
                type="text"
                value={raInput}
                onChange={(e) => {
                  setRaInput(e.target.value);
                  if (coordError) setCoordError(null);
                }}
                className={`w-full bg-paper-950 border rounded px-2 py-1 font-mono text-[11px] text-paper-100 focus:outline-none ${
                  coordError ? 'border-red-500/80 focus:border-red-400' : 'border-paper-800 focus:border-ochre-400'
                }`}
              />
            </div>
            <div>
              <label htmlFor="field-dec" className="text-[10px] font-mono text-paper-400 block mb-0.5">Dec (deg)</label>
              <input
                id="field-dec"
                aria-invalid={!!coordError}
                aria-describedby="coordinate-hint coordinate-error"
                type="text"
                value={decInput}
                onChange={(e) => {
                  setDecInput(e.target.value);
                  if (coordError) setCoordError(null);
                }}
                className={`w-full bg-paper-950 border rounded px-2 py-1 font-mono text-[11px] text-paper-100 focus:outline-none ${
                  coordError ? 'border-red-500/80 focus:border-red-400' : 'border-paper-800 focus:border-ochre-400'
                }`}
              />
            </div>
          </div>

          <div>
            <label htmlFor="field-archive" className="block text-paper-400 mb-1">Archive</label>
            <select id="field-archive" value={archiveDraft.provider} onChange={e => { setArchiveDraft(value => ({ ...value, provider: e.target.value })); setCoordError(null); }}
              className="w-full bg-paper-950 border border-paper-700 rounded px-2 py-1">
              {!archiveInventory.some(item => item.id === 'irsa-spherex') && <option value="irsa-spherex">IRSA SPHEREx</option>}
              {allProviderIds.includes(',') && <option value={allProviderIds}>All available image archives</option>}
              {archiveDraft.provider.includes(',') && archiveDraft.provider !== allProviderIds && <option value={archiveDraft.provider}>Multiple selected archives</option>}
              {!archiveDraft.provider && <option value="">Choose archives</option>}
              {archiveDraft.provider && !archiveDraft.provider.includes(',') && archiveDraft.provider !== 'irsa-spherex' && !selectedProviders[0] && <option value={archiveDraft.provider} disabled>{archiveDraft.provider} · inventory unavailable</option>}
              {archiveInventory.map(item => <option key={item.id} value={item.id}
                disabled={item.capabilities.availability !== 'available' || !item.capabilities.product_kinds.includes('image') || (!item.capabilities.original && !item.capabilities.cutout)}>
                {item.id === 'cadc' ? 'CADC' : item.id === 'irsa-spherex' ? 'IRSA SPHEREx' : item.id.toUpperCase()}
                {item.capabilities.availability !== 'available' ? ` · ${item.capabilities.availability}` : !item.capabilities.product_kinds.includes('image') ? ' · no images' : (!item.capabilities.original && !item.capabilities.cutout) ? ' · delivery unavailable' : ''}
              </option>)}
            </select>
            {archiveInventoryError && <p role="alert" className="text-amber-300">Archive inventory unavailable: {archiveInventoryError}</p>}
            {selectedProviders.filter((item): item is ArchiveInventory => !!item).map(item => <div key={item.id} className="text-paper-400 mt-1">{item.id} · Time filter: {item.capabilities.time_filter}
              {item.capabilities.restrictions?.map((restriction, i) => <p key={i}>{restriction}</p>)}
            </div>)}
          </div>
          <details id="tutorial-target-epoch" className="group">
            <summary className="flex items-center gap-1.5 cursor-pointer list-none text-paper-400 [&::-webkit-details-marker]:hidden">
              <ChevronDown aria-hidden="true" className="h-3 w-3 shrink-0 transition-transform group-open:rotate-180" />
              <span>Observation Era</span>
            </summary>
            <div className="space-y-1 pt-1">
            <div className="grid grid-cols-2 gap-1">
              {OBSERVATION_ERA_PRESETS.map(era => <button key={era.id} type="button" disabled={era.id !== 'custom' && !eraSelection(era).provider}
                onClick={() => {
                  if (era.id === 'custom') document.getElementById('observed-from')?.focus();
                  else setArchiveDraft(eraSelection(era));
                  setCoordError(null);
                }} title={era.description} className="rounded border border-paper-700 bg-paper-950 px-2 py-1 text-left disabled:opacity-40">
                {era.label}<span className="block text-paper-400">{era.periodLabel}</span>
              </button>)}
            </div>
            <label htmlFor="observed-from" className="block text-paper-400">Observed from</label>
            <input id="observed-from" type="date" value={archiveDraft.from} onChange={e => { setArchiveDraft(value => ({ ...value, from: e.target.value })); setCoordError(null); }} className="w-full bg-paper-950 border border-paper-700 rounded px-2 py-1" />
            <label htmlFor="observed-through" className="block text-paper-400">Observed through</label>
            <input id="observed-through" type="date" value={archiveDraft.through} onChange={e => { setArchiveDraft(value => ({ ...value, through: e.target.value })); setCoordError(null); }} className="w-full bg-paper-950 border border-paper-700 rounded px-2 py-1" />
            <p className="text-paper-400">Observation dates in UTC; end date includes the whole day. Apply source and period with Update Field.</p>
            </div>
          </details>
          <p id="coordinate-hint" className="text-[10px] text-paper-400">RA wraps into [0°, 360°). Dec must be −90° to +90°.</p>
          {coordError && (
            <div id="coordinate-error" role="alert" className="text-[10px] font-mono text-red-400 bg-red-950/40 border border-red-500/40 rounded px-2 py-1">
              {coordError}
            </div>
          )}

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
              title="Refresh the last applied coordinates, archive and observation period"
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
              <span className="text-paper-300">{searchStatus.source === 'packaged' ? 'Packaged real archive data' : searchStatus.source === 'archive' ? 'Archive metadata · images not implied' : searchStatus.source === 'live' ? 'NASA IRSA / SPHEREx Stream'
                : searchStatus.source === 'preset' ? 'Benchmark Preset' : searchStatus.source === 'loading' ? 'Loading observations…'
                : searchStatus.source === 'error' ? 'Observation request failed' : 'No observations requested'}</span>
            </div>
            {(searchStatus.source === 'error' || searchStatus.source === 'loading' || searchStatus.source === 'archive' || searchStatus.source === 'packaged') && <p className="break-words text-paper-300">{searchStatus.message}</p>}
          </div>
        )}

        {/* FOV Area Size */}
        <div id="tutorial-target-fov" className="mt-2.5 pt-2 border-t border-paper-800 transition-all duration-300">
          <span className="text-[10px] font-mono text-paper-400 block mb-1">Field of View (FOV)</span>
          <div className="grid grid-cols-4 gap-1.5">
            {(["1'", "3'", "5'", "10'", ...(DEMO_REAL_ONLY ? ["12'"] : [])] as FOVOption[]).map((f) => (
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
      <fieldset disabled={archiveBrowse} id="tutorial-target-bands" className="p-3 border-b border-paper-800 transition-all duration-300">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-semibold text-paper-200 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-emerald-400" />
            Infrared Filter
          </span>
          <button
            onClick={() => {
              onSelectArray('all');
            }}
            disabled
            title="Unavailable: no multi-detector composite artifact has been supplied"
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
            const cov = detectorCoverage[spec.id];
            return (
              <button
                key={spec.id}
                onClick={() => {
                  onSelectArray(spec.id as DetectorArrayId);
                    }}
                className={`btn-tactile-sm w-full px-2.5 py-1.5 rounded-lg border-2 border-black text-left flex items-center justify-between transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-paper-800 text-paper-100 font-medium'
                    : cov?.status === 'none'
                    ? 'bg-paper-950/60 text-paper-500 hover:text-paper-300'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-200'
                }`}
                title={`Wavelength: ${spec.range} | Resolving Power: ${spec.res} (${spec.desc})${cov?.notes ? ` — ${cov.notes}` : ''}`}
              >
                <div className="font-mono text-[11px] font-semibold text-paper-200 flex items-center gap-1.5 min-w-0">
                  <span>{spec.name}</span>
                  {viewMode === 'scientist' ? (
                    <span className="text-[10px] font-mono text-emerald-400 font-normal truncate">
                      ({spec.range})
                    </span>
                  ) : (
                    <span className="text-[10px] font-sans font-normal text-paper-400 truncate">
                      ({spec.label})
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {cov?.status === 'stacked' && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950/70 border border-emerald-500/50 text-emerald-300 font-bold">
                      ✓ {cov.exposureCount} exp · Stack eligible
                    </span>
                  )}
                  {cov?.status === 'insufficient' && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-950/70 border border-amber-500/50 text-amber-300 font-bold">
                      {cov.exposureCount} exp (&lt;3)
                    </span>
                  )}
                  {cov?.status === 'none' && (
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-paper-900 border border-paper-800 text-paper-500">
                      No data
                    </span>
                  )}
                  {isSelected && (
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* Warning Banner when an unobserved detector band is selected */}
        {!archiveBrowse && selectedArray !== 'all' && detectorCoverage[selectedArray]?.status === 'none' && (
          <div className="mt-2 p-2 rounded-lg bg-amber-950/30 border border-amber-500/40 text-[10px] font-mono text-amber-200">
            <div className="flex items-center gap-1.5 font-bold text-amber-300 mb-1">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              <span>Band {selectedArray} Data Unavailable</span>
            </div>
            <p className="text-paper-400 leading-tight mb-2">
              No image artifacts are loaded for this detector. Archive coverage may be broader. Stacking eligibility requires at least 3 exposures.
            </p>
            {(() => {
              const bestBand = Object.values(detectorCoverage).find((c) => c.canStack);
              if (bestBand) {
                return (
                  <button
                    type="button"
                    onClick={() => onSelectArray(bestBand.detectorId as DetectorArrayId)}
                    className="w-full py-1 px-2 rounded bg-amber-500 text-gray-950 font-bold text-[10px] hover:bg-amber-400 transition-colors cursor-pointer"
                  >
                    Switch to {bestBand.name} ({bestBand.exposureCount} exp · Stackable)
                  </button>
                );
              }
              return null;
            })()}
          </div>
        )}

        <p className="mt-2 text-[10px] text-paper-400">Images are selected by detector. Channel-resolved images are unavailable.</p>
        {archiveBrowse && <p className="text-amber-300 mt-2">SPHEREx detector controls do not filter other instruments or generic archive products.</p>}
      </fieldset>

      {/* 3. Image Filtering & Movement Isolation */}
      <fieldset disabled={archiveBrowse} id="tutorial-target-filters" className="p-3 border-b border-paper-800 transition-all duration-300">
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
                disabled={!availableModes.includes(mode.id as SubtractionMode)}
                onClick={() => onChangeSubtractionMode(mode.id as SubtractionMode)}
                className={`btn-tactile-sm w-full px-2.5 py-1.5 rounded-lg border-2 border-black flex items-center justify-between transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-paper-800 text-emerald-300 font-semibold'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-100'
                }`}
                title={availableModes.includes(mode.id as SubtractionMode) ? mode.desc : 'Unavailable: the processing artifact has not been supplied'}
              >
                <span className="font-mono text-[11px]">{mode.label}</span>
                {isSelected && (
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                )}
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* 4. Known Astronomical Catalogs (Live Space Agency Pull per Coordinate & Object) */}
      {(() => {
        const queryRa = liveCatalog?.queriedCoordinate.ra ?? activeCandidate?.ra ?? ra;
        const queryDec = liveCatalog?.queriedCoordinate.dec ?? activeCandidate?.dec ?? dec;
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

            {searchStatus?.source === 'packaged' && <p className="text-xs text-paper-300">Catalog overlays unavailable: frame WCS was not supplied.</p>}
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
                    : !liveCatalog || liveCatalog.status === 'unavailable' ? 'Catalogue query unavailable'
                    : `Catalogue query ${liveCatalog.status === 'partial' ? 'partial' : 'complete'}: ${liveCatalog.totalObjects} objects`}
                </span>
                <span className="text-[8px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                  {isCatalogLoading ? 'QUERYING' : liveCatalog?.status === 'live_agency' ? 'LIVE TAP' : liveCatalog?.status === 'partial' ? 'PARTIAL' : 'UNAVAILABLE'}
                </span>
              </div>

              <div className="text-paper-400 flex items-center justify-between">
                <span>
                  Query: <strong className="text-paper-200">α {queryRa.toFixed(4)}°, δ {queryDec >= 0 ? `+${queryDec.toFixed(4)}` : queryDec.toFixed(4)}°</strong>
                </span>
                <span>{liveCatalog?.providers.filter(provider => provider.status === 'failed').map(provider => provider.catalog).join(', ')} unavailable</span>
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
                    disabled={searchStatus?.source === 'packaged'}
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
                    disabled={searchStatus?.source === 'packaged'}
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
                    disabled={searchStatus?.source === 'packaged'}
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
