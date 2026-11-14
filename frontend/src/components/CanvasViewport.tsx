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
  const [colorMap, setColorMap] = useState<'grayscale' | 'inverted'>('grayscale');

  // Smooth Zoom-in transition state when target changes
  const prevRaRef = useRef(centerRa);
  const prevDecRef = useRef(centerDec);

  useEffect(() => {
    if (prevRaRef.current !== centerRa || prevDecRef.current !== centerDec) {
      prevRaRef.current = centerRa;
      prevDecRef.current = centerDec;

      // Animate smooth zoom into the new coordinate field
      let startZoom = 0.8;
      let targetZoom = 1.4;
      let startTime = performance.now();
      const duration = 600; // ms

      const animateZoom = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(1, elapsed / duration);
        // Ease-out cubic
        const ease = 1 - Math.pow(1 - progress, 3);
        setZoom(startZoom + (targetZoom - startZoom) * ease);
        setPan({ x: 0, y: 0 });

        if (progress < 1) {
          requestAnimationFrame(animateZoom);
        }
      };

      requestAnimationFrame(animateZoom);
    }
  }, [centerRa, centerDec]);

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

  // Minimalist Astronomical Rendering Engine
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

    const isWhiteBg = colorMap === 'inverted';
    // Warm Charcoal (#0a0a0c) or Editorial Paper Ivory (#f4f1ea)
    ctx.fillStyle = isWhiteBg ? '#f4f1ea' : '#0a0a0c';
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(width / 2 + pan.x, height / 2 + pan.y);
    ctx.scale(zoom, zoom);

    const isDifferenceMode = subtractionMode === 'epoch_difference';

    // Procedural field stars deterministically generated from celestial coordinates (centerRa, centerDec)
    let seed = Math.abs(Math.sin(centerRa * 12.9898 + centerDec * 78.233) * 43758.5453);
    const prng = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };

    const staticStars: { x: number; y: number; mag: number }[] = [];
    for (let i = 0; i < 32; i++) {
      staticStars.push({
        x: (prng() - 0.5) * 550,
        y: (prng() - 0.5) * 550,
        mag: 0.6 + prng() * 1.8,
      });
    }

    if (!isDifferenceMode) {
      staticStars.forEach((star) => {
        const grad = ctx.createRadialGradient(star.x, star.y, 0, star.x, star.y, star.mag * 3);
        if (isWhiteBg) {
          grad.addColorStop(0, '#1c1c22');
          grad.addColorStop(0.5, 'rgba(28, 28, 34, 0.4)');
          grad.addColorStop(1, 'rgba(28, 28, 34, 0)');
        } else {
          grad.addColorStop(0, '#f4f1ea');
          grad.addColorStop(0.5, 'rgba(244, 241, 234, 0.4)');
          grad.addColorStop(1, 'rgba(244, 241, 234, 0)');
        }
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(star.x, star.y, star.mag * 3, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // Candidate Point Spread Functions & Motion Track
    candidates.forEach((cand) => {
      const isSelected = selectedCandidateId === cand.id;
      const currentPos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const offsetX = currentPos.x - 256;
      const offsetY = currentPos.y - 256;

      const psfRadius = Math.max(3, Math.min(9, currentPos.flux / 16));
      const psfGrad = ctx.createRadialGradient(offsetX, offsetY, 0, offsetX, offsetY, psfRadius * 2);

      if (isWhiteBg) {
        psfGrad.addColorStop(0, '#d97706'); // Warm Ochre
        psfGrad.addColorStop(0.5, 'rgba(217, 119, 6, 0.4)');
        psfGrad.addColorStop(1, 'rgba(217, 119, 6, 0)');
      } else {
        psfGrad.addColorStop(0, '#ffffff');
        psfGrad.addColorStop(0.4, '#fbbf24');
        psfGrad.addColorStop(1, 'rgba(251, 191, 36, 0)');
      }

      ctx.fillStyle = psfGrad;
      ctx.beginPath();
      ctx.arc(offsetX, offsetY, psfRadius * 2, 0, Math.PI * 2);
      ctx.fill();

      // Motion Track
      if (cand.epochPositions.length > 1) {
        ctx.strokeStyle = isSelected ? '#d97706' : 'rgba(168, 162, 158, 0.4)';
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

      // Selected Reticle (Ochre accent without glow)
      if (isSelected) {
        ctx.strokeStyle = '#d97706';
        ctx.lineWidth = 1.2 / zoom;
        ctx.beginPath();
        ctx.arc(offsetX, offsetY, psfRadius * 2 + 4, 0, Math.PI * 2);
        ctx.stroke();

        const tLen = 6 / zoom;
        ctx.beginPath();
        ctx.moveTo(offsetX, offsetY - psfRadius * 2 - 2);
        ctx.lineTo(offsetX, offsetY - psfRadius * 2 - 2 - tLen);
        ctx.moveTo(offsetX, offsetY + psfRadius * 2 + 2);
        ctx.lineTo(offsetX, offsetY + psfRadius * 2 + 2 + tLen);
        ctx.moveTo(offsetX - psfRadius * 2 - 2, offsetY);
        ctx.lineTo(offsetX - psfRadius * 2 - 2 - tLen, offsetY);
        ctx.moveTo(offsetX + psfRadius * 2 + 2, offsetY);
        ctx.lineTo(offsetX + psfRadius * 2 + 2 + tLen, offsetY);
        ctx.stroke();

        ctx.font = `${10 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = isWhiteBg ? '#1c1c22' : '#f4f1ea';
        ctx.fillText(cand.matchedCatalog || cand.id, offsetX + psfRadius * 2 + 6, offsetY - 2);
      }
    });

    // Overlays
    if (overlays.gaiaDr3) {
      ctx.strokeStyle = '#059669';
      ctx.lineWidth = 1 / zoom;
      ctx.strokeRect(-144, -94, 8, 8);
      ctx.fillStyle = '#059669';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('Gaia DR3', -138, -98);
    }

    if (overlays.wise) {
      ctx.strokeStyle = '#d97706';
      ctx.lineWidth = 1 / zoom;
      ctx.beginPath();
      ctx.arc(210, 95, 5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#d97706';
      ctx.font = `${9 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillText('WISE', 218, 97);
    }

    ctx.restore();

    // Center Crosshair
    const cx = width / 2;
    const cy = height / 2;
    ctx.strokeStyle = isWhiteBg ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.15)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 10, cy);
    ctx.lineTo(cx + 10, cy);
    ctx.moveTo(cx, cy - 10);
    ctx.lineTo(cx, cy + 10);
    ctx.stroke();

    // Scale bar
    const scaleBarPixels = (30 / 6.2) * zoom;
    const sbX = width - 80;
    const sbY = height - 20;
    ctx.strokeStyle = isWhiteBg ? '#57534e' : '#a8a29e';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(sbX, sbY);
    ctx.lineTo(sbX + scaleBarPixels, sbY);
    ctx.stroke();
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = isWhiteBg ? '#57534e' : '#a8a29e';
    ctx.fillText('30″', sbX + scaleBarPixels / 2 - 6, sbY - 4);
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
      className="relative flex-1 h-[calc(100vh-3rem-4rem)] bg-paper-950 overflow-hidden cursor-crosshair select-none"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onClick={handleCanvasClick}
    >
      <canvas ref={canvasRef} className="w-full h-full block" />

      {/* Coordinate HUD */}
      <div className="absolute top-2.5 left-2.5 bg-paper-900/90 border border-paper-800 px-2.5 py-1 rounded text-[11px] font-mono text-paper-200 pointer-events-none flex items-center gap-3">
        <div>
          <span className="text-paper-500 mr-1">RA:</span>
          <span className="text-paper-100 font-medium">{cursorCoords?.ra || '17h 57m 48.5s'}</span>
        </div>
        <div className="w-[1px] h-3 bg-paper-800" />
        <div>
          <span className="text-paper-500 mr-1">Dec:</span>
          <span className="text-paper-100 font-medium">{cursorCoords?.dec || '+04° 41\' 36.1"'}</span>
        </div>
        <div className="w-[1px] h-3 bg-paper-800" />
        <span className="text-[10px] text-paper-400">
          {(6.2 / zoom).toFixed(2)}″/px
        </span>
      </div>

      {/* Skipped Frame Notification */}
      {skippedNotice && (
        <div className="absolute top-12 left-2.5 bg-paper-900 border border-ochre-500/60 text-ochre-300 px-3 py-1.5 rounded flex items-center justify-between text-xs font-mono z-30">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-ochre-400 shrink-0" />
            <span>{skippedNotice}</span>
          </div>
          <button
            onClick={onClearSkippedNotice}
            className="ml-3 text-[10px] text-ochre-400 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Viewport Toolbar */}
      <div className="absolute top-2.5 right-2.5 bg-paper-900/90 border border-paper-800 p-1 rounded flex items-center space-x-1 z-10">
        <select
          value={colorMap}
          onChange={(e) => setColorMap(e.target.value as any)}
          title="Colormap: Standard dark sky or inverted negative film (makes faint objects easier to see)"
          className="bg-paper-950 border border-paper-800 text-paper-300 text-[10px] font-mono rounded px-1.5 py-0.5 mr-1 focus:outline-none focus:border-ochre-400"
        >
          <option value="grayscale">Standard (Dark Sky)</option>
          <option value="inverted">Negative (White Sky)</option>
        </select>
        <button
          onClick={() => setZoom((z) => Math.min(8.0, z * 1.25))}
          className="p-1 rounded hover:bg-paper-800 text-paper-400 hover:text-paper-100 transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.6, z * 0.8))}
          className="p-1 rounded hover:bg-paper-800 text-paper-400 hover:text-paper-100 transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={handleResetView}
          className="p-1 rounded hover:bg-paper-800 text-paper-400 hover:text-paper-100 transition-colors"
          title="Reset View"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Frame Status Pill */}
      {activeFrame && (
        <div className="absolute bottom-2.5 left-2.5 bg-paper-900/90 border border-paper-800 px-2 py-0.5 rounded text-[10px] font-mono text-paper-400 flex items-center gap-2 pointer-events-none">
          <span className="w-1.5 h-1.5 rounded-full bg-ochre-400" />
          <span>Epoch {activeFrame.epochIndex + 1}/{frames.length}: {activeFrame.observationDate.split('T')[0]}</span>
          <span>|</span>
          <span>Band {activeFrame.detectorArray} ({activeFrame.wavelengthMinUm}–{activeFrame.wavelengthMaxUm} µm)</span>
        </div>
      )}
    </div>
  );
};
