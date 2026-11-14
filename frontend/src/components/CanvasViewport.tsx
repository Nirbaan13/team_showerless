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

  const [zoom, setZoom] = useState(1.4);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [cursorCoords, setCursorCoords] = useState<{ ra: string; dec: string; x: number; y: number } | null>(null);
  const [colorMap, setColorMap] = useState<'grayscale' | 'inverted' | 'heat'>('grayscale');

  const activeFrame = frames[activeFrameIndex] || null;

  const handleResetView = () => {
    setZoom(1.4);
    setPan({ x: 0, y: 0 });
  };

  const calculateRaDecFromPixel = useCallback(
    (canvasX: number, canvasY: number, width: number, height: number) => {
      const centerX = width / 2 + pan.x;
      const centerY = height / 2 + pan.y;
      const scaleArcsecPerPx = 6.2 / zoom;

      const dxArcsec = (canvasX - centerX) * scaleArcsecPerPx;
      const dyArcsec = (centerY - canvasY) * scaleArcsecPerPx;

      const raOffsetDeg = dxArcsec / 3600 / Math.cos((centerDec * Math.PI) / 180);
      const decOffsetDeg = dyArcsec / 3600;

      const computedRa = (centerRa - raOffsetDeg + 360) % 360;
      const computedDec = centerDec + decOffsetDeg;

      const raHours = computedRa / 15;
      const rh = Math.floor(raHours);
      const rm = Math.floor((raHours - rh) * 60);
      const rs = ((raHours - rh - rm / 60) * 3600).toFixed(2);

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

  // Astronomical FITS Canvas Rendering Engine
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Astronomical background (scientific black or inverted paper white)
    const isWhiteBg = colorMap === 'inverted';
    ctx.fillStyle = isWhiteBg ? '#f8fafc' : '#040711';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(width / 2 + pan.x, height / 2 + pan.y);
    ctx.scale(zoom, zoom);

    const isDifferenceMode = subtractionMode === 'epoch_difference';

    // Static Field Stars (rendered as authentic astronomical point-spread functions)
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
        if (isWhiteBg) {
          grad.addColorStop(0, '#0f172a');
          grad.addColorStop(0.5, 'rgba(15, 23, 42, 0.4)');
          grad.addColorStop(1, 'rgba(15, 23, 42, 0)');
        } else {
          grad.addColorStop(0, '#f8fafc');
          grad.addColorStop(0.5, 'rgba(203, 213, 225, 0.4)');
          grad.addColorStop(1, 'rgba(203, 213, 225, 0)');
        }
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.mag * 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // Candidate Objects (Proper Motion PSF)
    candidates.forEach((cand) => {
      const isSelected = selectedCandidateId === cand.id;
      const currentPos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const offsetX = currentPos.x - 256;
      const offsetY = currentPos.y - 256;

      // Authentic astronomical PSF
      const psfRadius = Math.max(3, Math.min(9, currentPos.flux / 16));
      const psfGrad = ctx.createRadialGradient(offsetX, offsetY, 0, offsetX, offsetY, psfRadius * 2);

      if (isWhiteBg) {
        psfGrad.addColorStop(0, '#0284c7');
        psfGrad.addColorStop(0.5, 'rgba(2, 132, 199, 0.4)');
        psfGrad.addColorStop(1, 'rgba(2, 132, 199, 0)');
      } else {
        psfGrad.addColorStop(0, '#ffffff');
        psfGrad.addColorStop(0.4, '#93c5fd');
        psfGrad.addColorStop(1, 'rgba(147, 197, 253, 0)');
      }

      ctx.fillStyle = psfGrad;
      ctx.beginPath();
      ctx.arc(offsetX, offsetY, psfRadius * 2, 0, Math.PI * 2);
      ctx.fill();

      // Motion vector track (clean dashed line)
      if (cand.epochPositions.length > 1) {
        ctx.strokeStyle = isSelected ? '#3b82f6' : 'rgba(148, 163, 184, 0.4)';
        ctx.lineWidth = 1 / zoom;
        ctx.setLineDash([2, 2]);
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

      // Standard Astronomy Reticle (Crosshairs without neon glow)
      if (isSelected) {
        ctx.strokeStyle = '#2563eb';
        ctx.lineWidth = 1.2 / zoom;
        ctx.beginPath();
        ctx.arc(offsetX, offsetY, psfRadius * 2 + 5, 0, Math.PI * 2);
        ctx.stroke();

        // 4 crosshair ticks
        const tLen = 6 / zoom;
        ctx.beginPath();
        ctx.moveTo(offsetX, offsetY - psfRadius * 2 - 3);
        ctx.lineTo(offsetX, offsetY - psfRadius * 2 - 3 - tLen);
        ctx.moveTo(offsetX, offsetY + psfRadius * 2 + 3);
        ctx.lineTo(offsetX, offsetY + psfRadius * 2 + 3 + tLen);
        ctx.moveTo(offsetX - psfRadius * 2 - 3, offsetY);
        ctx.lineTo(offsetX - psfRadius * 2 - 3 - tLen, offsetY);
        ctx.moveTo(offsetX + psfRadius * 2 + 3, offsetY);
        ctx.lineTo(offsetX + psfRadius * 2 + 3 + tLen, offsetY);
        ctx.stroke();

        // Scientific label
        ctx.font = `${10 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = isWhiteBg ? '#1e293b' : '#f8fafc';
        ctx.fillText(cand.matchedCatalog || cand.id, offsetX + psfRadius * 2 + 7, offsetY - 2);
      }
    });

    // Catalog Overlays (Standard astronomical markers)
    if (overlays.gaiaDr3) {
      ctx.strokeStyle = '#059669'; // Emerald
      ctx.lineWidth = 1 / zoom;
      ctx.strokeRect(-144, -94, 8, 8);
      ctx.fillStyle = '#059669';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('Gaia DR3', -138, -98);
    }

    if (overlays.wise) {
      ctx.strokeStyle = '#d97706'; // Amber
      ctx.lineWidth = 1 / zoom;
      ctx.beginPath();
      ctx.arc(210, 95, 5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#d97706';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('WISE', 218, 97);
    }

    ctx.restore();

    // Center Crosshairs (Standard telescope reticle)
    const cx = width / 2;
    const cy = height / 2;
    ctx.strokeStyle = isWhiteBg ? 'rgba(0, 0, 0, 0.2)' : 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 12, cy);
    ctx.lineTo(cx + 12, cy);
    ctx.moveTo(cx, cy - 12);
    ctx.lineTo(cx, cy + 12);
    ctx.stroke();

    // WCS Compass
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = isWhiteBg ? '#64748b' : '#94a3b8';
    ctx.fillText('N ▲', cx - 8, cy - 24);
    ctx.fillText('E ◀', cx - 44, cy + 4);

    // Scale bar in bottom right (e.g., 30 arcsec)
    const scaleBarPixels = (30 / 6.2) * zoom;
    const sbX = width - 90;
    const sbY = height - 20;
    ctx.strokeStyle = isWhiteBg ? '#334155' : '#cbd5e1';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(sbX, sbY);
    ctx.lineTo(sbX + scaleBarPixels, sbY);
    ctx.moveTo(sbX, sbY - 3);
    ctx.lineTo(sbX, sbY + 3);
    ctx.moveTo(sbX + scaleBarPixels, sbY - 3);
    ctx.lineTo(sbX + scaleBarPixels, sbY + 3);
    ctx.stroke();
    ctx.fillText('30″', sbX + scaleBarPixels / 2 - 8, sbY - 5);
  }, [zoom, pan, activeFrameIndex, candidates, selectedCandidateId, overlays, subtractionMode, colorMap]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.88;
    setZoom((prev) => Math.max(0.6, Math.min(8.0, prev * factor)));
  };

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

  const handleCanvasClick = (e: React.MouseEvent) => {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const width = rect.width;
    const height = rect.height;

    const transformedX = (clickX - (width / 2 + pan.x)) / zoom;
    const transformedY = (clickY - (height / 2 + pan.y)) / zoom;

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
      className="relative flex-1 h-[calc(100vh-3rem-4.5rem)] bg-nasa-dark overflow-hidden cursor-crosshair select-none"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onClick={handleCanvasClick}
    >
      <canvas ref={canvasRef} className="w-full h-full block" />

      {/* Scientific Coordinate HUD */}
      <div className="absolute top-2.5 left-2.5 bg-nasa-surface/90 border border-nasa-border px-2.5 py-1 rounded text-[11px] font-mono text-nasa-textMain pointer-events-none flex items-center gap-3">
        <div>
          <span className="text-nasa-textMuted mr-1">RA:</span>
          <span className="text-white font-medium">{cursorCoords?.ra || '17h 57m 48.5s'}</span>
        </div>
        <div className="w-[1px] h-3 bg-nasa-border" />
        <div>
          <span className="text-nasa-textMuted mr-1">Dec:</span>
          <span className="text-white font-medium">{cursorCoords?.dec || '+04° 41\' 36.1"'}</span>
        </div>
        <div className="w-[1px] h-3 bg-nasa-border" />
        <span className="text-[10px] text-nasa-textMuted">
          Scale: {(6.2 / zoom).toFixed(2)}″/px
        </span>
      </div>

      {/* Skipped Frame Notification */}
      {skippedNotice && (
        <div className="absolute top-12 left-2.5 bg-amber-950/90 border border-amber-600 text-amber-200 px-3 py-1.5 rounded flex items-center justify-between text-xs font-mono z-30">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span>{skippedNotice}</span>
          </div>
          <button
            onClick={onClearSkippedNotice}
            className="ml-3 text-[10px] text-amber-300 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Viewport & Colormap Controls */}
      <div className="absolute top-2.5 right-2.5 bg-nasa-surface/90 border border-nasa-border p-1 rounded flex items-center space-x-1 z-10">
        <select
          value={colorMap}
          onChange={(e) => setColorMap(e.target.value as any)}
          className="bg-nasa-dark border border-nasa-border text-nasa-textMuted text-[10px] font-mono rounded px-1.5 py-0.5 mr-1"
        >
          <option value="grayscale">Grayscale</option>
          <option value="inverted">Inverted (Print)</option>
        </select>
        <button
          onClick={() => setZoom((z) => Math.min(8.0, z * 1.25))}
          className="p-1 rounded hover:bg-nasa-dark text-nasa-textMuted hover:text-white transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.6, z * 0.8))}
          className="p-1 rounded hover:bg-nasa-dark text-nasa-textMuted hover:text-white transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={handleResetView}
          className="p-1 rounded hover:bg-nasa-dark text-nasa-textMuted hover:text-white transition-colors"
          title="Reset View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Frame Status Pill */}
      {activeFrame && (
        <div className="absolute bottom-2.5 left-2.5 bg-nasa-surface/90 border border-nasa-border px-2 py-0.5 rounded text-[10px] font-mono text-nasa-textMuted flex items-center gap-2 pointer-events-none">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
          <span>Epoch {activeFrame.epochIndex + 1}/{frames.length}: {activeFrame.observationDate.split('T')[0]}</span>
          <span>|</span>
          <span>Band {activeFrame.detectorArray} ({activeFrame.wavelengthMinUm}–{activeFrame.wavelengthMaxUm} µm)</span>
        </div>
      )}
    </div>
  );
};
