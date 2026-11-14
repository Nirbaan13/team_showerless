import React, { useRef, useEffect, useState, useCallback } from 'react';
import type { SpherexEpochFrame, CandidateObject, CatalogOverlayState, SubtractionMode } from '../types/spherex';
import { ZoomIn, ZoomOut, RotateCcw, AlertTriangle } from 'lucide-react';

interface CanvasViewportProps {
  frames: SpherexEpochFrame[];
  activeFrameIndex: number;
  candidates: CandidateObject[];
  selectedCandidateId: string | null;
  onSelectCandidate: (candidateId: string) => void;
  overlays: CatalogOverlayState;
  subtractionMode: SubtractionMode;
  centerRa: number;
  centerDec: number;
  skippedNotice: string | null;
  onClearSkippedNotice: () => void;
}

export const CanvasViewport: React.FC<CanvasViewportProps> = ({
  frames,
  activeFrameIndex,
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  overlays,
  subtractionMode,
  centerRa,
  centerDec,
  skippedNotice,
  onClearSkippedNotice,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Inertial Pan & Zoom State
  const [zoom, setZoom] = useState(1.4);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [cursorCoords, setCursorCoords] = useState<{ ra: string; dec: string; x: number; y: number } | null>(null);

  const activeFrame = frames[activeFrameIndex] || null;

  // Reset Viewport
  const handleResetView = () => {
    setZoom(1.4);
    setPan({ x: 0, y: 0 });
  };

  // Convert canvas pixel offsets to celestial coordinates (approximate local WCS projection)
  const calculateRaDecFromPixel = useCallback(
    (canvasX: number, canvasY: number, width: number, height: number) => {
      const centerX = width / 2 + pan.x;
      const centerY = height / 2 + pan.y;
      const scaleArcsecPerPx = 6.2 / zoom; // SPHEREx 6.2 arcsec/pixel native scale

      const dxArcsec = (canvasX - centerX) * scaleArcsecPerPx;
      const dyArcsec = (centerY - canvasY) * scaleArcsecPerPx;

      const raOffsetDeg = dxArcsec / 3600 / Math.cos((centerDec * Math.PI) / 180);
      const decOffsetDeg = dyArcsec / 3600;

      const computedRa = (centerRa - raOffsetDeg + 360) % 360;
      const computedDec = centerDec + decOffsetDeg;

      // Format RA into HH:MM:SS.ss
      const raHours = computedRa / 15;
      const rh = Math.floor(raHours);
      const rm = Math.floor((raHours - rh) * 60);
      const rs = ((raHours - rh - rm / 60) * 3600).toFixed(2);

      // Format Dec into DD:MM:SS.s
      const sign = computedDec >= 0 ? '+' : '-';
      const absDec = Math.abs(computedDec);
      const dd = Math.floor(absDec);
      const dm = Math.floor((absDec - dd) * 60);
      const ds = ((absDec - dd - dm / 60) * 3600).toFixed(1);

      return {
        ra: `${rh.toString().padStart(2, '0')}h ${rm.toString().padStart(2, '0')}m ${rs.padStart(5, '0')}s`,
        dec: `${sign}${dd.toString().padStart(2, '0')}° ${dm.toString().padStart(2, '0')}' ${ds.padStart(4, '0')}"`,
      };
    },
    [pan, zoom, centerRa, centerDec]
  );

  // Main Canvas Rendering Engine
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle high DPI
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear background (Deep OLED celestial black)
    ctx.fillStyle = '#06070a';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    // Center pan & zoom transformation
    ctx.translate(width / 2 + pan.x, height / 2 + pan.y);
    ctx.scale(zoom, zoom);

    // 1. Render Simulated SPHEREx Celestial Background Noise & Point Sources
    const isDifferenceMode = subtractionMode === 'epoch_difference';
    const isZodiSubtracted = subtractionMode === 'zodi_reference_subtracted';

    // Sky background gradient or difference noise
    if (!isDifferenceMode) {
      const bgAlpha = isZodiSubtracted ? 0.05 : 0.16;
      const bgGrad = ctx.createRadialGradient(0, 0, 10, 0, 0, 320);
      bgGrad.addColorStop(0, `rgba(30, 41, 59, ${bgAlpha})`);
      bgGrad.addColorStop(1, 'rgba(6, 7, 10, 0)');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(-400, -400, 800, 800);
    } else {
      // In difference mode, show subtle zero-mean speckle noise
      ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
      for (let i = 0; i < 200; i++) {
        const nx = Math.sin(i * 99) * 240;
        const ny = Math.cos(i * 77) * 240;
        ctx.fillRect(nx, ny, 1.5, 1.5);
      }
    }

    // 2. Render Static Background Field Stars
    const staticStars = [
      { x: -140, y: -90, mag: 1.8 },
      { x: 120, y: -160, mag: 2.2 },
      { x: -180, y: 130, mag: 1.2 },
      { x: 210, y: 95, mag: 1.5 },
      { x: -70, y: 190, mag: 2.0 },
      { x: 160, y: 180, mag: 1.1 },
      { x: -30, y: -180, mag: 0.9 },
    ];

    if (!isDifferenceMode) {
      staticStars.forEach((star) => {
        const grad = ctx.createRadialGradient(star.x, star.y, 0, star.x, star.y, star.mag * 3);
        grad.addColorStop(0, '#e2e8f0');
        grad.addColorStop(0.4, 'rgba(148, 163, 184, 0.6)');
        grad.addColorStop(1, 'rgba(148, 163, 184, 0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.mag * 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // 3. Render Candidate Objects and Motion Vectors
    candidates.forEach((cand) => {
      const isSelected = selectedCandidateId === cand.id;
      // Get position for active epoch
      const currentPos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const offsetX = currentPos.x - 256;
      const offsetY = currentPos.y - 256;

      // Draw faint motion track across all epochs
      if (cand.epochPositions.length > 1) {
        ctx.strokeStyle = isSelected ? 'rgba(0, 242, 254, 0.5)' : 'rgba(100, 116, 139, 0.3)';
        ctx.lineWidth = 1 / zoom;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        cand.epochPositions.forEach((pos, idx) => {
          const px = pos.x - 256;
          const py = pos.y - 256;
          if (idx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Draw Candidate Point Spread Function (PSF)
      const psfRadius = Math.max(3, Math.min(10, currentPos.flux / 15));
      const psfGrad = ctx.createRadialGradient(offsetX, offsetY, 0, offsetX, offsetY, psfRadius * 2);

      if (isDifferenceMode) {
        // Difference dipole or positive residual
        psfGrad.addColorStop(0, '#38bdf8');
        psfGrad.addColorStop(0.6, 'rgba(56, 189, 248, 0.5)');
        psfGrad.addColorStop(1, 'rgba(56, 189, 248, 0)');
      } else {
        psfGrad.addColorStop(0, '#ffffff');
        psfGrad.addColorStop(0.4, '#38bdf8');
        psfGrad.addColorStop(1, 'rgba(56, 189, 248, 0)');
      }

      ctx.fillStyle = psfGrad;
      ctx.beginPath();
      ctx.arc(offsetX, offsetY, psfRadius * 2, 0, Math.PI * 2);
      ctx.fill();

      // WorldWideTelescope style Reticle & Target Rings
      if (isSelected) {
        // Animated target bracket
        ctx.strokeStyle = '#00f2fe';
        ctx.lineWidth = 1.5 / zoom;
        ctx.beginPath();
        ctx.arc(offsetX, offsetY, psfRadius * 2.5 + 4, 0, Math.PI * 2);
        ctx.stroke();

        // Crosshairs
        const crossLength = 8 / zoom;
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.8)';
        ctx.beginPath();
        // Top
        ctx.moveTo(offsetX, offsetY - psfRadius * 2.5 - 2);
        ctx.lineTo(offsetX, offsetY - psfRadius * 2.5 - 2 - crossLength);
        // Bottom
        ctx.moveTo(offsetX, offsetY + psfRadius * 2.5 + 2);
        ctx.lineTo(offsetX, offsetY + psfRadius * 2.5 + 2 + crossLength);
        // Left
        ctx.moveTo(offsetX - psfRadius * 2.5 - 2, offsetY);
        ctx.lineTo(offsetX - psfRadius * 2.5 - 2 - crossLength, offsetY);
        // Right
        ctx.moveTo(offsetX + psfRadius * 2.5 + 2, offsetY);
        ctx.lineTo(offsetX + psfRadius * 2.5 + 2 + crossLength, offsetY);
        ctx.stroke();

        // Label
        ctx.font = `${11 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = '#00f2fe';
        ctx.fillText(cand.matchedCatalog || 'Candidate', offsetX + psfRadius * 2.5 + 6, offsetY - 4);
      }
    });

    // 4. Render Catalog Overlays
    if (overlays.gaiaDr3) {
      // Gaia DR3 Astrometry Diamond Markers
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 1 / zoom;
      const gaiaStars = [
        { x: -140, y: -90, id: 'Gaia DR3 ...81' },
        { x: 120, y: -160, id: 'Gaia DR3 ...42' },
      ];
      gaiaStars.forEach((star) => {
        ctx.strokeRect(star.x - 4, star.y - 4, 8, 8);
        ctx.fillStyle = '#10b981';
        ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillText(star.id, star.x + 6, star.y + 3);
      });
    }

    if (overlays.wise) {
      // AllWISE IR Point Source Circular Markers
      ctx.strokeStyle = '#f97316';
      ctx.lineWidth = 1 / zoom;
      ctx.beginPath();
      ctx.arc(210, 95, 6, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#f97316';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('WISE J1757...', 218, 98);
    }

    if (overlays.solarSystemEphemeris) {
      // Solar System Object Predicted Track (Asteroid)
      ctx.strokeStyle = '#60a5fa';
      ctx.lineWidth = 1.2 / zoom;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(-160, 160);
      ctx.lineTo(-80, 140);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#60a5fa';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('Asteroid Ephemeris (Epoch ±2d)', -76, 142);
    }

    ctx.restore();

    // 5. Center Reticle & Celestial Compass Overlay
    const cx = width / 2;
    const cy = height / 2;

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 16, cy);
    ctx.lineTo(cx + 16, cy);
    ctx.moveTo(cx, cy - 16);
    ctx.lineTo(cx, cy + 16);
    ctx.stroke();

    // Subtle center circle
    ctx.beginPath();
    ctx.arc(cx, cy, 32, 0, Math.PI * 2);
    ctx.stroke();

    // Celestial Compass Readout (N/E orientation)
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
    ctx.fillText('N ▲', cx - 8, cy - 40);
    ctx.fillText('E ◀', cx - 60, cy + 4);
  }, [zoom, pan, activeFrameIndex, candidates, selectedCandidateId, overlays, subtractionMode]);

  // Mouse wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.88;
    setZoom((prev) => Math.max(0.6, Math.min(8.0, prev * factor)));
  };

  // Mouse drag pan
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const clientY = e.clientY - rect.top;
      const { ra, dec } = calculateRaDecFromPixel(clientX, clientY, rect.width, rect.height);
      setCursorCoords({ ra, dec, x: clientX, y: clientY });
    }

    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  // Click to select candidate
  const handleCanvasClick = (e: React.MouseEvent) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const width = rect.width;
    const height = rect.height;

    // Transform click to canvas coordinate space
    const transformedX = (clickX - (width / 2 + pan.x)) / zoom;
    const transformedY = (clickY - (height / 2 + pan.y)) / zoom;

    // Find nearest candidate
    for (const cand of candidates) {
      const pos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const cx = pos.x - 256;
      const cy = pos.y - 256;
      const dist = Math.hypot(transformedX - cx, transformedY - cy);
      if (dist < 18 / zoom) {
        onSelectCandidate(cand.id);
        return;
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative flex-1 h-[calc(100vh-3.5rem-5rem)] bg-space-950 overflow-hidden cursor-crosshair select-none"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onClick={handleCanvasClick}
    >
      <canvas ref={canvasRef} className="w-full h-full block" />

      {/* Floating HUD: Live RA/Dec Cursor Coordinates */}
      <div className="absolute top-3 left-3 bg-space-900/85 backdrop-blur border border-space-700/80 px-2.5 py-1.5 rounded text-[11px] font-mono text-space-200 pointer-events-none flex items-center gap-3 shadow-lg">
        <div className="flex items-center gap-1.5">
          <span className="text-space-500 font-semibold">RA</span>
          <span className="text-cyan-300 font-telemetry">{cursorCoords?.ra || '17h 57m 48.5s'}</span>
        </div>
        <div className="w-[1px] h-3 bg-space-700" />
        <div className="flex items-center gap-1.5">
          <span className="text-space-500 font-semibold">DEC</span>
          <span className="text-cyan-300 font-telemetry">{cursorCoords?.dec || '+04° 41\' 36.1"'}</span>
        </div>
        <div className="w-[1px] h-3 bg-space-700" />
        <div className="text-[10px] text-space-400">
          Scale: {(6.2 / zoom).toFixed(2)}″/px
        </div>
      </div>

      {/* Missing Detector Frame Warning Badge */}
      {skippedNotice && (
        <div className="absolute top-14 left-3 right-3 md:right-auto md:max-w-md bg-amber-950/90 border border-amber-500/70 text-amber-200 px-3 py-2 rounded shadow-2xl flex items-center justify-between text-xs font-mono animate-in fade-in duration-200 z-30">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>{skippedNotice}</span>
          </div>
          <button
            onClick={onClearSkippedNotice}
            className="ml-3 px-1.5 py-0.5 rounded bg-amber-900/60 hover:bg-amber-900 text-[10px] text-amber-300 border border-amber-500/40"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Viewport Control Floating Pill */}
      <div className="absolute top-3 right-3 bg-space-900/85 backdrop-blur border border-space-700/80 p-1 rounded flex items-center space-x-1 shadow-lg z-10">
        <button
          onClick={() => setZoom((z) => Math.min(8.0, z * 1.25))}
          className="p-1.5 rounded hover:bg-space-800 text-space-300 hover:text-cyan-300 transition-colors"
          title="Zoom In (+)"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.6, z * 0.8))}
          className="p-1.5 rounded hover:bg-space-800 text-space-300 hover:text-cyan-300 transition-colors"
          title="Zoom Out (-)"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={handleResetView}
          className="p-1.5 rounded hover:bg-space-800 text-space-300 hover:text-cyan-300 transition-colors"
          title="Reset Inertial View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Active Epoch Watermark Pill */}
      {activeFrame && (
        <div className="absolute bottom-3 left-3 bg-space-900/80 backdrop-blur border border-space-700/60 px-2 py-1 rounded text-[10px] font-mono text-space-300 flex items-center gap-2 pointer-events-none">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span>Epoch {activeFrame.epochIndex + 1}/{frames.length}: {activeFrame.observationDate.split('T')[0]}</span>
          <span className="text-space-500">|</span>
          <span>Band {activeFrame.detectorArray} ({activeFrame.wavelengthMinUm}–{activeFrame.wavelengthMaxUm} µm)</span>
        </div>
      )}
    </div>
  );
};
