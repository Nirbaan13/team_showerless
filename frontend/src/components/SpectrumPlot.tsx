import React, { useState, useEffect, useMemo } from 'react';
import type { SpectralDataPoint } from '../types/spherex';
import { REFERENCE_MOLECULAR_LINES } from '../services/mockSpherexApi';
import { fetchTargetSpectrum } from '../services/spherexBackendApi';
import type { TargetSpectrumResult, MolecularDetection } from '../services/spherexBackendApi';
import { Download, ShieldCheck, Activity, RefreshCw, Zap } from 'lucide-react';

interface SpectrumPlotProps {
  data?: SpectralDataPoint[];
  objectLabel?: string;
  ra?: number;
  dec?: number;
  candidateId?: string | null;
  isScientistMode?: boolean;
}

const DETECTOR_COLORS: Record<string, string> = {
  D1: '#38bdf8', // Cyan (0.75-1.11 µm)
  D2: '#818cf8', // Indigo (1.11-1.64 µm)
  D3: '#c084fc', // Purple (1.64-2.42 µm)
  D4: '#f472b6', // Pink (2.42-3.82 µm)
  D5: '#fbbf24', // Amber (3.82-4.42 µm - CO2)
  D6: '#34d399', // Emerald (4.42-5.00 µm - CO)
};

export const SpectrumPlot: React.FC<SpectrumPlotProps> = ({
  objectLabel = 'Target',
  ra = 284.14,
  dec = -45.12,
  candidateId = null,
  isScientistMode: _isScientistMode = false,
}) => {
  const apertureRadius = 2.0;
  const [subtractionMode, setSubtractionMode] = useState<'zodi_subtracted' | 'raw_calibrated'>('zodi_subtracted');
  const [selectedDetector, setSelectedDetector] = useState<string | 'all'>('all');
  const [spectrumResult, setSpectrumResult] = useState<TargetSpectrumResult | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<{
    channel: number;
    detector: string;
    wavelengthUm: number;
    bandwidthUm: number;
    fluxMjy: number;
    uncertaintyMjy: number;
    snr: number;
  } | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [spectrumError, setSpectrumError] = useState('');
  const [refreshRevision, setRefreshRevision] = useState(0);

  const handleMeasureLive = () => setRefreshRevision(value => value + 1);

  // Fetch live spectrophotometry from Shasta's WCS-WAVE endpoint
  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();
    setSpectrumResult(null);
    setSpectrumError('');
    setIsLoading(true);

    fetchTargetSpectrum(ra, dec, candidateId, apertureRadius, subtractionMode, controller.signal)
      .then((res) => {
        if (isMounted) {
          setSpectrumResult(res);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setSpectrumError(err instanceof Error ? err.message : 'Spectrum unavailable');
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [ra, dec, candidateId, apertureRadius, subtractionMode, refreshRevision]);

  // Unified channel points (from live Shasta endpoint or fallback prop)
  const channels = useMemo(() => {
    if (spectrumResult?.spectrum && spectrumResult.spectrum.length > 0) {
      return spectrumResult.spectrum.map((s) => ({
        channel: s.channel,
        detector: s.detector,
        detectorArray: s.detector_array,
        wavelengthUm: s.wavelength_um,
        bandwidthUm: s.bandwidth_um,
        fluxMjy: s.flux_mjy,
        uncertaintyMjy: s.uncertainty_mjy,
        snr: s.snr,
      }));
    }

    return [];
  }, [spectrumResult]);

  const molecularDetections = useMemo<MolecularDetection[]>(
    () => spectrumResult?.molecular_detections ?? [], [spectrumResult]
  );

  // Filtered channels for display
  const displayChannels = useMemo(() => {
    if (selectedDetector === 'all') return channels;
    return channels.filter((c) => c.detector === selectedDetector);
  }, [channels, selectedDetector]);

  // Export CSV Handler
  const handleExportCSV = () => {
    if (channels.length === 0) return;
    const header = 'channel,detector,wavelength_um,bandwidth_um,flux_mjy,uncertainty_mjy,snr\n';
    const rows = channels
      .map(
        (c) =>
          `${c.channel},${c.detector},${c.wavelengthUm},${c.bandwidthUm},${c.fluxMjy},${c.uncertaintyMjy},${c.snr.toFixed(1)}`
      )
      .join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `spherex_measured_spectrum_${objectLabel.replace(/[^a-zA-Z0-9]/g, '_')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (channels.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-paper-500 font-mono text-xs">
        {isLoading ? 'Downloading observations and measuring apertures…' : spectrumError || 'No measured spectral points available'}
      </div>
    );
  }

  // SVG dimensions & scaling
  const svgWidth = 360;
  const svgHeight = 180;
  const padding = { top: 18, right: 15, bottom: 26, left: 38 };

  const plotW = svgWidth - padding.left - padding.right;
  const plotH = svgHeight - padding.top - padding.bottom;

  const minLambda = 0.75;
  const maxLambda = 5.0;

  const lower = Math.min(0, ...channels.map(d => d.fluxMjy - d.uncertaintyMjy));
  const upper = Math.max(0, ...channels.map(d => d.fluxMjy + d.uncertaintyMjy));
  const margin = Math.max(upper - lower, 1e-6) * 0.1;
  const minFlux = lower - margin;
  const maxFlux = upper + margin;

  const getX = (lambda: number) => padding.left + ((lambda - minLambda) / (maxLambda - minLambda)) * plotW;
  const getY = (flux: number) => padding.top + plotH - ((flux - minFlux) / (maxFlux - minFlux)) * plotH;

  const pointsStr = displayChannels
    .map((d) => `${getX(d.wavelengthUm).toFixed(1)},${getY(d.fluxMjy).toFixed(1)}`)
    .join(' ');

  return (
    <div className="space-y-3.5 select-none text-xs">
      <p className="p-2 rounded border border-amber-700 text-amber-200" role="status">
        Experimental WCS-WAVE aperture measurements for visualization. Calibrated spectra
        and molecular detections are unavailable; spectral coverage may be incomplete.
      </p>
      {/* Header Info Banner: Physical Target & Export */}
      <div className="p-2 rounded-lg bg-paper-950 border border-paper-800 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-mono font-bold text-white truncate">
            {spectrumResult?.target || objectLabel}
          </div>
          <div className="text-[10px] font-mono text-emerald-400">
            RA {ra.toFixed(4)}°, Dec {dec.toFixed(4)}° · {channels.length} measured points
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={handleMeasureLive}
            disabled={isLoading}
            className="btn-tactile-sm px-2 py-1 rounded bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400 text-emerald-300 font-mono text-[10px] font-bold flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
            title="Measure real aperture fluxes from IRSA SPHEREx FITS cutouts"
          >
            {isLoading ? (
              <RefreshCw className="w-3 h-3 animate-spin text-emerald-400" />
            ) : (
              <Zap className="w-3 h-3 text-emerald-400" />
            )}
            <span>{isLoading ? 'Measuring...' : 'Measure IRSA'}</span>
          </button>

          <button
            onClick={handleExportCSV}
            className="px-2 py-1 rounded bg-paper-900 hover:bg-paper-800 border border-paper-700 text-paper-300 hover:text-white flex items-center gap-1 font-mono text-[10px] transition-colors cursor-pointer shrink-0"
            title="Download measured aperture points as CSV"
          >
            <Download className="w-3 h-3 text-emerald-400" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Detected Molecular Absorption Features */}
      {molecularDetections && molecularDetections.length > 0 && (
        <div className="p-2 rounded-lg bg-emerald-950/20 border border-emerald-500/30 flex flex-wrap gap-1.5 items-center">
          <span className="text-emerald-400 font-mono text-[10px] font-bold flex items-center gap-1 mr-1">
            <Activity className="w-3 h-3" />
            <span>Signatures:</span>
          </span>
          {molecularDetections.map((m: MolecularDetection) => (
            <span
              key={m.species}
              className="px-2 py-0.5 rounded-md bg-paper-950 border border-emerald-500/40 text-emerald-300 font-mono text-[10px] flex items-center gap-1.5"
            >
              <span className="font-bold">{m.species}</span>
              <span className="text-paper-400">{m.center_um} µm</span>
              <span className="px-1 rounded bg-emerald-900/60 text-emerald-300 text-[9px] font-bold">
                SNR {m.significance_snr}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Main SVG Plot */}
      <div className="bg-paper-950 border border-paper-800 rounded-lg p-2.5 relative select-none">
        <div className="flex items-center justify-between mb-2 font-mono text-[10px]">
          <span className="font-semibold text-paper-200">
            Flux Density F_ν (mJy) vs. Wavelength λ (µm)
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() =>
                setSubtractionMode((prev) =>
                  prev === 'zodi_subtracted' ? 'raw_calibrated' : 'zodi_subtracted'
                )
              }
              className={`px-2 py-0.5 rounded text-[9px] font-bold border transition-colors cursor-pointer ${
                subtractionMode === 'zodi_subtracted'
                  ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300'
                  : 'bg-paper-900 border-paper-800 text-paper-400 hover:text-white'
              }`}
              title="Toggle Zodiacal Light subtraction (clean = img - zodi)"
            >
              {subtractionMode === 'zodi_subtracted' ? 'Zodi Clean' : 'Raw Flux'}
            </button>
            <span className="text-emerald-400 font-bold">{channels.length} points</span>
          </div>
        </div>

        <div className="relative">
          <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-auto overflow-visible">
            {/* Detector array boundaries background shading */}
            {[
              { d: 'D1', start: 0.75, end: 1.11, color: DETECTOR_COLORS.D1 },
              { d: 'D2', start: 1.11, end: 1.64, color: DETECTOR_COLORS.D2 },
              { d: 'D3', start: 1.64, end: 2.42, color: DETECTOR_COLORS.D3 },
              { d: 'D4', start: 2.42, end: 3.82, color: DETECTOR_COLORS.D4 },
              { d: 'D5', start: 3.82, end: 4.42, color: DETECTOR_COLORS.D5 },
              { d: 'D6', start: 4.42, end: 5.0, color: DETECTOR_COLORS.D6 },
            ].map((det) => {
              const x1 = getX(det.start);
              const x2 = getX(det.end);
              const isSelected = selectedDetector === 'all' || selectedDetector === det.d;
              return (
                <g key={det.d}>
                  <rect
                    x={x1}
                    y={padding.top}
                    width={x2 - x1}
                    height={plotH}
                    fill={det.color}
                    fillOpacity={isSelected ? 0.05 : 0.01}
                  />
                  <line
                    x1={x2}
                    y1={padding.top}
                    x2={x2}
                    y2={padding.top + plotH}
                    stroke="#1e293b"
                    strokeDasharray="2 2"
                    strokeWidth="1"
                  />
                </g>
              );
            })}

            {/* Reference Molecular Absorption Bands */}
            {REFERENCE_MOLECULAR_LINES.map((line) => {
              const x = getX(line.centerUm);
              const w = (line.widthUm / (maxLambda - minLambda)) * plotW;
              return (
                <g key={line.formula}>
                  <rect
                    x={x - w / 2}
                    y={padding.top}
                    width={Math.max(2, w)}
                    height={plotH}
                    fill={line.color}
                    fillOpacity="0.12"
                  />
                  <line
                    x1={x}
                    y1={padding.top}
                    x2={x}
                    y2={padding.top + plotH}
                    stroke={line.color}
                    strokeDasharray="2 2"
                    strokeWidth="1"
                    strokeOpacity="0.5"
                  />
                  <text
                    x={x}
                    y={padding.top + 10}
                    fill={line.color}
                    fontSize="7.5"
                    fontFamily="JetBrains Mono, monospace"
                    textAnchor="middle"
                    fontWeight="bold"
                  >
                    {line.formula}
                  </text>
                </g>
              );
            })}

            {/* Grid Axes */}
            <line
              x1={padding.left}
              y1={padding.top + plotH}
              x2={padding.left + plotW}
              y2={padding.top + plotH}
              stroke="#334155"
              strokeWidth="1"
            />
            <line
              x1={padding.left}
              y1={padding.top}
              x2={padding.left}
              y2={padding.top + plotH}
              stroke="#334155"
              strokeWidth="1"
            />

            {/* Spectrum continuous curve */}
            <polyline
              fill="none"
              stroke="#34d399"
              strokeWidth="1.5"
              points={pointsStr}
            />

            {/* Error bars & interactive data points */}
            {displayChannels.map((pt) => {
              const cx = getX(pt.wavelengthUm);
              const cy = getY(pt.fluxMjy);
              const errTop = getY(pt.fluxMjy + pt.uncertaintyMjy);
              const errBottom = getY(Math.max(0, pt.fluxMjy - pt.uncertaintyMjy));
              const isHovered = hoveredPoint?.channel === pt.channel;
              const detColor = DETECTOR_COLORS[pt.detector] || '#38bdf8';

              return (
                <g key={pt.channel}>
                  {/* 1-sigma uncertainty vertical tick */}
                  <line
                    x1={cx}
                    y1={errTop}
                    x2={cx}
                    y2={errBottom}
                    stroke={detColor}
                    strokeOpacity={isHovered ? 0.9 : 0.4}
                    strokeWidth={isHovered ? 1.5 : 1}
                  />
                  {/* Interactive circle */}
                  <circle
                    cx={cx}
                    cy={cy}
                    r={isHovered ? 4.0 : 1.8}
                    fill={isHovered ? '#ffffff' : detColor}
                    stroke={detColor}
                    strokeWidth={isHovered ? 2 : 0}
                    className="cursor-pointer transition-all"
                    onMouseEnter={() => setHoveredPoint(pt)}
                  />
                </g>
              );
            })}

            {/* Axis Tick Labels */}
            <text x={padding.left} y={padding.top + plotH + 15} fill="#64748b" fontSize="8.5" fontFamily="monospace">
              0.75 µm
            </text>
            <text x={padding.left + plotW * 0.25} y={padding.top + plotH + 15} fill="#64748b" fontSize="8.5" fontFamily="monospace" textAnchor="middle">
              1.8 µm
            </text>
            <text x={padding.left + plotW * 0.58} y={padding.top + plotH + 15} fill="#64748b" fontSize="8.5" fontFamily="monospace" textAnchor="middle">
              3.2 µm
            </text>
            <text x={padding.left + plotW} y={padding.top + plotH + 15} fill="#64748b" fontSize="8.5" fontFamily="monospace" textAnchor="end">
              5.00 µm
            </text>
          </svg>

          {/* Interactive Hover Tooltip */}
          {hoveredPoint && (
            <div className="absolute top-2 right-2 bg-paper-900 border border-emerald-400 px-2.5 py-1.5 rounded-lg text-[10px] font-mono text-emerald-300 shadow-xl z-20 space-y-0.5">
              <div className="font-bold text-white flex items-center justify-between gap-2">
                <span>Ch #{hoveredPoint.channel} ({hoveredPoint.detector})</span>
                <span className="text-emerald-400 font-bold">SNR {hoveredPoint.snr.toFixed(1)}</span>
              </div>
              <div>λ: {hoveredPoint.wavelengthUm.toFixed(4)} µm (Δλ {hoveredPoint.bandwidthUm.toFixed(3)})</div>
              <div>Flux: {hoveredPoint.fluxMjy.toFixed(2)} ± {hoveredPoint.uncertaintyMjy.toFixed(2)} mJy</div>
            </div>
          )}
        </div>
      </div>

      {/* Shasta IRSA Aperture Detector Telemetry Summary */}
      {spectrumResult?.detectors_summary && Object.keys(spectrumResult.detectors_summary).length > 0 && (
        <div className="p-2 rounded-lg bg-paper-950 border border-paper-800 space-y-1.5 font-mono text-[10px]">
          <div className="flex items-center justify-between text-paper-300 font-bold text-[9px] uppercase tracking-wider">
            <span>IRSA Aperture Telemetry</span>
            <span className="text-emerald-400 font-normal">
              {spectrumResult.total_channels || channels.length} Bands Analyzed
            </span>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-1">
            {Object.entries(spectrumResult.detectors_summary).map(([det, stats]) => {
              const isFocused = selectedDetector === det;
              return (
                <button
                  key={det}
                  type="button"
                  onClick={() => setSelectedDetector(isFocused ? 'all' : det)}
                  className={`p-1 rounded border transition-all cursor-pointer flex flex-col text-center ${
                    isFocused
                      ? 'bg-paper-800 border-emerald-400 font-bold scale-[1.02]'
                      : 'bg-paper-900 border-paper-800 hover:border-paper-700'
                  }`}
                  title={`Click to focus ${det} bands on plot`}
                >
                  <span className="font-bold text-white text-[11px]" style={{ color: DETECTOR_COLORS[det] }}>
                    {det}
                  </span>
                  <span className="text-[9px] text-emerald-300 font-bold">{stats.mean_flux_mjy} mJy</span>
                  <span className="text-[8px] text-paper-400">SNR {stats.mean_snr}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Scientific Calibration Status */}
      <div className="px-2.5 py-1.5 rounded-lg bg-paper-950 border border-paper-800/80 flex items-center justify-between text-[10px] font-mono text-paper-400">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span>WCS-WAVE Spectrophotometry</span>
        </div>
        <span className="text-emerald-400 font-bold">Experimental</span>
      </div>
    </div>
  );
};
