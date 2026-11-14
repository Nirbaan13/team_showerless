import React, { useRef, useEffect, useState, useCallback } from 'react';
import type {
  SpherexEpochFrame,
  CandidateObject,
  CatalogOverlayState,
  SubtractionMode,
  MLAnalysisStatus,
} from '../types/spherex';
import { getPriorityColors } from '../services/mlRanking';
import { resolveCoordinateCatalogContext } from '../services/mockSpherexApi';
import type { LiveCatalogResponse } from '../services/catalogService';
import { ZoomIn, ZoomOut, RotateCcw, AlertTriangle, Cpu } from 'lucide-react';

interface CanvasViewportProps {
  frames: SpherexEpochFrame[];
  activeFrameIndex: number;
  candidates: CandidateObject[];
  selectedCandidateId: string | null;
  onSelectCandidate: (candidateId: string) => void;
  overlays: CatalogOverlayState;
  subtractionMode: SubtractionMode;
  onChangeSubtractionMode?: (mode: SubtractionMode) => void;
  centerRa: number;
  centerDec: number;
  skippedNotice: string | null;
  onClearSkippedNotice: () => void;
  isScientistMode?: boolean;
  mlAnalysisStatus?: MLAnalysisStatus;
  onOpenMlInsights?: () => void;
  liveCatalog?: LiveCatalogResponse | null;
}

export const CanvasViewport: React.FC<CanvasViewportProps> = ({
  frames,
  activeFrameIndex,
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  overlays,
  subtractionMode,
  onChangeSubtractionMode,
  centerRa,
  centerDec,
  skippedNotice,
  onClearSkippedNotice,
  isScientistMode = false,
  mlAnalysisStatus,
  onOpenMlInsights: _onOpenMlInsights,
  liveCatalog,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [zoom, setZoom] = useState(1.4);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [cursorCoords, setCursorCoords] = useState<{ ra: string; dec: string; x: number; y: number } | null>(null);
  const [colorMap, setColorMap] = useState<'grayscale' | 'inverted'>('grayscale');
  const imgCacheRef = useRef<Map<string, HTMLImageElement>>(new Map());
  const [, setRepaintCount] = useState(0);

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
    const isBloomMode = subtractionMode === 'bloom_mask';

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

    // In Scientist Mode: Draw astronomical coordinate grid lines (RA/Dec J2000 ICRS)
    if (isScientistMode) {
      ctx.save();
      ctx.strokeStyle = isWhiteBg ? 'rgba(0, 0, 0, 0.12)' : 'rgba(52, 211, 153, 0.2)';
      ctx.lineWidth = 1 / zoom;
      ctx.setLineDash([4 / zoom, 4 / zoom]);

      for (let offset = -250; offset <= 250; offset += 100) {
        // Vertical grid line (RA)
        ctx.beginPath();
        ctx.moveTo(offset, -250);
        ctx.lineTo(offset, 250);
        ctx.stroke();

        // Horizontal grid line (Dec)
        ctx.beginPath();
        ctx.moveTo(-250, offset);
        ctx.lineTo(250, offset);
        ctx.stroke();
      }

      // Draw faint coordinate tick labels on the grid in scientist mode
      ctx.font = `${8 / zoom}px "JetBrains Mono", monospace`;
      ctx.fillStyle = isWhiteBg ? 'rgba(0, 0, 0, 0.35)' : 'rgba(52, 211, 153, 0.45)';
      ctx.setLineDash([]);
      ctx.fillText('α: 17h 57m 40s', -245, -5);
      ctx.fillText('α: 17h 57m 55s', 55, -5);
      ctx.fillText('δ: +04° 41\' 00"', -5, -95);
      ctx.fillText('δ: +04° 42\' 00"', -5, 105);
      ctx.restore();
    }

    const currentFrame = frames[activeFrameIndex];
    let hasDrawnRealImage = false;

    const targetBitmapUrl = isBloomMode
      ? currentFrame?.bloomDataUrl || currentFrame?.residualDataUrl || currentFrame?.imageDataUrl
      : isDifferenceMode
      ? currentFrame?.residualDataUrl
      : currentFrame?.imageDataUrl;

    if (targetBitmapUrl) {
      let cachedImg = imgCacheRef.current.get(targetBitmapUrl);
      if (!cachedImg) {
        cachedImg = new Image();
        cachedImg.src = targetBitmapUrl;
        cachedImg.onload = () => {
          setRepaintCount((c) => c + 1);
        };
        imgCacheRef.current.set(targetBitmapUrl, cachedImg);
      }

      if (cachedImg.complete && cachedImg.naturalWidth > 0) {
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        const aspect = cachedImg.naturalWidth / cachedImg.naturalHeight;
        const imgW = 512;
        const imgH = 512 / aspect;
        ctx.globalAlpha = isWhiteBg ? 0.75 : 0.92;
        if (isWhiteBg) {
          ctx.filter = 'invert(1)';
        }
        ctx.drawImage(cachedImg, -imgW / 2, -imgH / 2, imgW, imgH);
        ctx.restore();
        hasDrawnRealImage = true;
      }
    }

    if (!isDifferenceMode && !isBloomMode && !hasDrawnRealImage) {
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

    // Helper to draw a regular hexagon covering pixel cluster
    const drawHexagon = (hx: number, hy: number, radius: number) => {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i - Math.PI / 6;
        const x = hx + radius * Math.cos(angle);
        const y = hy + radius * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
    };

    // Helper to calculate canvas coordinates from image pixel coordinates
    const getCanvasCoords = (x: number, y: number) => {
      const natW = currentFrame?.imageWidth || 256;
      const natH = currentFrame?.imageHeight || (currentFrame?.detectorArray === 6 && y <= 144 ? 144 : 256);
      const scale = 512 / natW;
      const imgH = 512 * (natH / natW);
      const cx = (x + 0.5) * scale - 256;
      const cy = (y + 0.5) * scale - imgH / 2;
      return { cx, cy };
    };

    // Candidate Point Spread Functions, Motion Track & Priority-Graded Red Hexagons
    candidates.forEach((cand, candIdx) => {
      const isSelected = selectedCandidateId === cand.id;
      const currentPos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const { cx: offsetX, cy: offsetY } = getCanvasCoords(currentPos.x, currentPos.y);

      // Priority ranking: Priority 1 gets intense deep red, fading to softer reds for lower priority
      const rank = cand.mlRank || (candIdx + 1);
      const priority = getPriorityColors(rank);

      // 1. Point Spread Function Core
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

      // 2. Motion Track Across Epochs
      if (cand.epochPositions.length > 1) {
        ctx.strokeStyle = isSelected ? priority.border : 'rgba(239, 68, 68, 0.45)';
        ctx.lineWidth = (isSelected ? 1.6 : 1.0) / zoom;
        ctx.setLineDash([3 / zoom, 2 / zoom]);
        ctx.beginPath();
        cand.epochPositions.forEach((pos, idx) => {
          const { cx: px, cy: py } = getCanvasCoords(pos.x, pos.y);
          if (idx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // 3. ML Priority Hexagon Covering Detected Pixel Region
      // Priority 1 is deep red, fading to lighter shades for lower priority
      const hexRadius = Math.max(12, Math.min(26, psfRadius * 2 + 6));
      ctx.save();
      ctx.globalAlpha = isSelected ? 1.0 : 0.65;
      drawHexagon(offsetX, offsetY, hexRadius);
      ctx.fillStyle = isSelected ? 'rgba(16, 185, 129, 0.22)' : priority.fill;
      ctx.fill();

      ctx.strokeStyle = isSelected ? '#34d399' : priority.border;
      ctx.lineWidth = (isSelected ? 2.4 : rank === 1 ? 1.8 : 1.2) / zoom;
      ctx.stroke();

      // Priority Pill Badge (e.g. "★ #1" when selected, or "P2", "P3" when unselected)
      const badgeText = isSelected ? `★ #${rank} SELECTED` : `#${rank}`;
      ctx.font = `bold ${8.5 / zoom}px "JetBrains Mono", monospace`;
      const badgeWidth = ctx.measureText(badgeText).width + 7 / zoom;
      const badgeHeight = 12 / zoom;
      const badgeX = offsetX - hexRadius;
      const badgeY = offsetY - hexRadius - 2 / zoom;

      ctx.fillStyle = isSelected ? '#10b981' : priority.badgeBg;
      ctx.beginPath();
      if (typeof ctx.roundRect === 'function') {
        ctx.roundRect(badgeX, badgeY - badgeHeight, badgeWidth, badgeHeight, 2.5 / zoom);
      } else {
        ctx.rect(badgeX, badgeY - badgeHeight, badgeWidth, badgeHeight);
      }
      ctx.fill();

      ctx.fillStyle = isSelected ? '#052e16' : '#ffffff';
      ctx.fillText(badgeText, badgeX + 3.5 / zoom, badgeY - 3 / zoom);

      // 4. Object Name Label (for known / confirmed objects or selected candidate)
      const objectLabel =
        cand.validationData?.objectName ||
        cand.catalogId ||
        cand.matchedCatalog ||
        (cand.isKnownCatalogMatch ? 'Known Object' : `Candidate #${rank}`);

      if (objectLabel && (isSelected || cand.isKnownCatalogMatch || rank <= 4)) {
        ctx.font = `bold ${9 / zoom}px "JetBrains Mono", monospace`;
        const labelWidth = ctx.measureText(objectLabel).width + 8 / zoom;
        const labelHeight = 13 / zoom;
        const labelX = offsetX + hexRadius + 4 / zoom;
        const labelY = offsetY - 7 / zoom;

        // Label background pill
        ctx.fillStyle = isSelected ? 'rgba(6, 78, 59, 0.92)' : 'rgba(10, 10, 14, 0.88)';
        ctx.strokeStyle = isSelected ? '#34d399' : priority.border;
        ctx.lineWidth = (isSelected ? 1.5 : 1) / zoom;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(labelX, labelY, labelWidth, labelHeight, 3 / zoom);
        } else {
          ctx.rect(labelX, labelY, labelWidth, labelHeight);
        }
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? '#ecfdf5' : '#cbd5e1';
        ctx.fillText(objectLabel, labelX + 4 / zoom, labelY + 9.5 / zoom);
      }

      // 5. Selected Reticle & Crosshairs
      if (isSelected) {
        ctx.strokeStyle = '#34d399';
        ctx.lineWidth = 1.8 / zoom;
        ctx.beginPath();
        ctx.arc(offsetX, offsetY, hexRadius + 4.5 / zoom, 0, Math.PI * 2);
        ctx.stroke();

        const tLen = 7 / zoom;
        ctx.beginPath();
        ctx.moveTo(offsetX, offsetY - hexRadius - 2 / zoom);
        ctx.lineTo(offsetX, offsetY - hexRadius - 2 / zoom - tLen);
        ctx.moveTo(offsetX, offsetY + hexRadius + 2 / zoom);
        ctx.lineTo(offsetX, offsetY + hexRadius + 2 / zoom + tLen);
        ctx.moveTo(offsetX - hexRadius - 2 / zoom, offsetY);
        ctx.lineTo(offsetX - hexRadius - 2 / zoom - tLen, offsetY);
        ctx.moveTo(offsetX + hexRadius + 2 / zoom, offsetY);
        ctx.lineTo(offsetX + hexRadius + 2 / zoom + tLen, offsetY);
        ctx.stroke();

        // Scientist HUD telemetry apertures
        if (isScientistMode) {
          ctx.strokeStyle = 'rgba(52, 211, 153, 0.6)';
          ctx.lineWidth = 1 / zoom;
          ctx.setLineDash([2 / zoom, 2 / zoom]);
          ctx.beginPath();
          ctx.arc(offsetX, offsetY, psfRadius * 1.5, 0, Math.PI * 2);
          ctx.stroke();

          ctx.strokeStyle = 'rgba(52, 211, 153, 0.3)';
          ctx.beginPath();
          ctx.arc(offsetX, offsetY, psfRadius * 3.2, 0, Math.PI * 2);
          ctx.stroke();

          ctx.setLineDash([]);
          ctx.font = `${8 / zoom}px "JetBrains Mono", monospace`;
          ctx.fillStyle = '#34d399';
          ctx.fillText(`Priority: #${rank} | FWHM: 1.42px (8.8″)`, offsetX + hexRadius + 4 / zoom, offsetY + 18 / zoom);
          ctx.fillText(`Flux: ${(currentPos.flux || 18).toFixed(1)} mJy | SNR: ${(currentPos.snr || 12).toFixed(1)}`, offsetX + hexRadius + 4 / zoom, offsetY + 28 / zoom);
        }
      }

      ctx.restore();
    });

    // Per-Target & Per-Object Live Space Agency Catalog Overlays (ESA Gaia DR3, NASA AllWISE, CDS SIMBAD, JPL Horizons)
    const selectedCand =
      candidates.find((c) => c.id === selectedCandidateId) || candidates[0] || null;
    const coordCatalog = resolveCoordinateCatalogContext(
      selectedCand?.ra ?? centerRa,
      selectedCand?.dec ?? centerDec
    );

    const gaiaOverlaySources =
      liveCatalog && liveCatalog.gaiaSources.length > 0
        ? liveCatalog.gaiaSources
        : coordCatalog.gaiaSources;

    const wiseOverlaySources =
      liveCatalog && liveCatalog.wiseSources.length > 0
        ? liveCatalog.wiseSources
        : coordCatalog.wiseSources;

    if (overlays.gaiaDr3) {
      // 1. Draw live-pulled ESA Gaia DR3 stars in this field
      gaiaOverlaySources.forEach((src, idx) => {
        let gx = src.dx;
        let gy = src.dy;
        const matchingGaiaCand =
          idx === 0
            ? candidates.find((c) => c.matchedCatalog === 'Gaia DR3')
            : undefined;
        if (matchingGaiaCand) {
          const pos =
            matchingGaiaCand.epochPositions[activeFrameIndex] ||
            matchingGaiaCand.epochPositions[0];
          const cPos = getCanvasCoords(pos.x, pos.y);
          gx = cPos.cx;
          gy = cPos.cy;
        }
        const isSelectedGaia =
          selectedCand &&
          selectedCand.matchedCatalog === 'Gaia DR3' &&
          matchingGaiaCand?.id === selectedCand.id;

        ctx.strokeStyle = isSelectedGaia ? '#34d399' : '#10b981';
        ctx.lineWidth = (isSelectedGaia ? 2.2 : 1.5) / zoom;
        const boxHalf = (isSelectedGaia ? 8.5 : 6.5) / zoom;
        ctx.strokeRect(gx - boxHalf, gy - boxHalf, boxHalf * 2, boxHalf * 2);

        // Label pill
        const tag = `${isSelectedGaia ? '★ ' : ''}${src.label}`;
        ctx.font = `bold ${8 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = 'rgba(6, 78, 59, 0.85)';
        const tw = ctx.measureText(tag).width + 6 / zoom;
        ctx.fillRect(gx + boxHalf + 3 / zoom, gy - 11 / zoom, tw, 11 / zoom);
        ctx.fillStyle = '#6ee7b7';
        ctx.fillText(tag, gx + boxHalf + 6 / zoom, gy - 3 / zoom);
      });

      if (
        selectedCand &&
        selectedCand.matchedCatalog === 'Gaia DR3' &&
        candidates.find((c) => c.matchedCatalog === 'Gaia DR3')?.id !== selectedCand.id
      ) {
        const pos =
          selectedCand.epochPositions[activeFrameIndex] ||
          selectedCand.epochPositions[0];
        const { cx: gx, cy: gy } = getCanvasCoords(pos.x, pos.y);
        ctx.strokeStyle = '#34d399';
        ctx.lineWidth = 2.2 / zoom;
        ctx.strokeRect(gx - 8 / zoom, gy - 8 / zoom, 16 / zoom, 16 / zoom);
        ctx.font = `bold ${8 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = '#34d399';
        ctx.fillText(
          `★ ${selectedCand.catalogId || 'Gaia DR3 Match'} [F${activeFrameIndex + 1}]`,
          gx + 10 / zoom,
          gy - 4 / zoom
        );
      }
    }

    if (overlays.wise) {
      // 2. Draw live-pulled NASA/IPAC AllWISE mid-infrared sources in this field
      wiseOverlaySources.forEach((src, idx) => {
        let wx = src.dx;
        let wy = src.dy;
        const matchingWiseCand =
          idx === 0
            ? candidates.find((c) => c.matchedCatalog === 'WISE')
            : undefined;
        if (matchingWiseCand) {
          const pos =
            matchingWiseCand.epochPositions[activeFrameIndex] ||
            matchingWiseCand.epochPositions[0];
          const cPos = getCanvasCoords(pos.x, pos.y);
          wx = cPos.cx;
          wy = cPos.cy;
        }
        const isSelectedWise =
          selectedCand &&
          selectedCand.matchedCatalog === 'WISE' &&
          matchingWiseCand?.id === selectedCand.id;

        const rad = (isSelectedWise ? 9 : 7) / zoom;
        ctx.strokeStyle = isSelectedWise ? '#fbbf24' : '#f59e0b';
        ctx.lineWidth = (isSelectedWise ? 2.2 : 1.5) / zoom;
        ctx.beginPath();
        ctx.arc(wx, wy, rad, 0, Math.PI * 2);
        ctx.stroke();

        const tag = `${isSelectedWise ? '★ ' : ''}${src.label}`;
        ctx.font = `bold ${8 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = 'rgba(69, 26, 3, 0.85)';
        const tw = ctx.measureText(tag).width + 6 / zoom;
        ctx.fillRect(wx + rad + 3 / zoom, wy + 2 / zoom, tw, 11 / zoom);
        ctx.fillStyle = '#fde68a';
        ctx.fillText(tag, wx + rad + 6 / zoom, wy + 10 / zoom);
      });
    }

    // 3. Draw JPL Horizons Solar System Ephemeris & CDS SIMBAD sources when ticked
    const neoCandidate =
      (selectedCand?.matchedCatalog === 'NEO Ephemeris' ? selectedCand : null) ||
      candidates.find((c) => c.matchedCatalog === 'NEO Ephemeris');

    if (overlays.solarSystemEphemeris) {
      if (neoCandidate || coordCatalog.ephemerisLabel || (liveCatalog?.ephemerisSources.length ?? 0) > 0) {
        let ex = liveCatalog?.ephemerisSources[0]?.dx ?? 0;
        let ey = liveCatalog?.ephemerisSources[0]?.dy ?? 0;
        if (neoCandidate) {
          const pos =
            neoCandidate.epochPositions[activeFrameIndex] ||
            neoCandidate.epochPositions[0];
          const coords = getCanvasCoords(pos.x, pos.y);
          ex = coords.cx;
          ey = coords.cy;
        }
        const offsetPx =
          neoCandidate?.ephemerisOffsetsPx?.[activeFrameIndex] ??
          neoCandidate?.validationData?.maxOffsetPx ??
          0.54;
        const ephLabel = `★ ${
          liveCatalog?.ephemerisSources[0]?.label ||
          neoCandidate?.validationData?.objectName ||
          neoCandidate?.catalogId ||
          coordCatalog.ephemerisLabel ||
          'JPL Horizons'
        } [Epoch ${activeFrameIndex + 1} · Δ=${offsetPx.toFixed(2)}px]`;
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.8 / zoom;
        ctx.beginPath();
        ctx.moveTo(ex - 10 / zoom, ey);
        ctx.lineTo(ex + 10 / zoom, ey);
        ctx.moveTo(ex, ey - 10 / zoom);
        ctx.lineTo(ex, ey + 10 / zoom);
        ctx.stroke();
        ctx.font = `bold ${8.5 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = 'rgba(8, 47, 73, 0.88)';
        const tw = ctx.measureText(ephLabel).width + 6 / zoom;
        ctx.fillRect(ex + 10 / zoom, ey + 6 / zoom, tw, 12 / zoom);
        ctx.fillStyle = '#7dd3fc';
        ctx.fillText(ephLabel, ex + 13 / zoom, ey + 15 / zoom);
      }

      // Also draw live-pulled CDS SIMBAD objects
      (liveCatalog?.simbadSources ?? []).slice(0, 3).forEach((simSrc) => {
        const sx = simSrc.dx;
        const sy = simSrc.dy;
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.4 / zoom;
        ctx.beginPath();
        ctx.moveTo(sx - 7 / zoom, sy);
        ctx.lineTo(sx + 7 / zoom, sy);
        ctx.moveTo(sx, sy - 7 / zoom);
        ctx.lineTo(sx, sy + 7 / zoom);
        ctx.stroke();
        const sTag = `SIMBAD: ${simSrc.label}`;
        ctx.font = `bold ${7.5 / zoom}px "JetBrains Mono", monospace`;
        ctx.fillStyle = 'rgba(8, 47, 73, 0.85)';
        const tw = ctx.measureText(sTag).width + 5 / zoom;
        ctx.fillRect(sx + 8 / zoom, sy - 10 / zoom, tw, 10 / zoom);
        ctx.fillStyle = '#7dd3fc';
        ctx.fillText(sTag, sx + 10 / zoom, sy - 2.5 / zoom);
      });
    }

    // 4. If the currently selected candidate is UNCATALOGUED (new moving track / flare / artifact),
    // explicitly show a "No Catalog Match at Selected Object" callout tag right under it so switching objects visibly updates!
    if (
      selectedCand &&
      !selectedCand.isKnownCatalogMatch &&
      (overlays.gaiaDr3 || overlays.wise || overlays.solarSystemEphemeris)
    ) {
      const pos =
        selectedCand.epochPositions[activeFrameIndex] ||
        selectedCand.epochPositions[0];
      const { cx: ux, cy: uy } = getCanvasCoords(pos.x, pos.y);
      const uncatTag = `★ Selected Object: No Gaia/WISE/Horizons Match (${selectedCand.classification.replace('_', ' ')})`;
      ctx.font = `bold ${8 / zoom}px "JetBrains Mono", monospace`;
      const tw = ctx.measureText(uncatTag).width + 8 / zoom;
      ctx.fillStyle = 'rgba(88, 28, 135, 0.88)';
      ctx.fillRect(ux - tw / 2, uy + 20 / zoom, tw, 12 / zoom);
      ctx.strokeStyle = '#c084fc';
      ctx.lineWidth = 1 / zoom;
      ctx.strokeRect(ux - tw / 2, uy + 20 / zoom, tw, 12 / zoom);
      ctx.fillStyle = '#f3e8ff';
      ctx.fillText(uncatTag, ux - tw / 2 + 4 / zoom, uy + 28.5 / zoom);
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
  }, [zoom, pan, activeFrameIndex, candidates, selectedCandidateId, overlays, subtractionMode, colorMap, isScientistMode, centerRa, centerDec, frames, liveCatalog]);

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

    const natW = activeFrame?.imageWidth || 256;
    const natH = activeFrame?.imageHeight || (activeFrame?.detectorArray === 6 ? 144 : 256);
    const scale = 512 / natW;
    const imgH = 512 * (natH / natW);

    for (const cand of candidates) {
      const pos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
      const cx = (pos.x + 0.5) * scale - 256;
      const cy = (pos.y + 0.5) * scale - imgH / 2;
      const dist = Math.hypot(transformedX - cx, transformedY - cy);
      if (dist < 28 / zoom) {
        onSelectCandidate(cand.id);
        return;
      }
    }
  };

  // Mobile Touch Gestures: 1-finger pan, 2-finger pinch-to-zoom, tap to select
  const touchMetaRef = useRef<{ startX: number; startY: number; pinchDist: number }>({
    startX: 0,
    startY: 0,
    pinchDist: 0,
  });

  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      const touch = e.touches[0];
      setIsDragging(true);
      setDragStart({ x: touch.clientX - pan.x, y: touch.clientY - pan.y });
      touchMetaRef.current = { startX: touch.clientX, startY: touch.clientY, pinchDist: 0 };
    } else if (e.touches.length === 2) {
      setIsDragging(false);
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const dist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      touchMetaRef.current.pinchDist = dist;
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 1 && isDragging) {
      const touch = e.touches[0];
      setPan({
        x: touch.clientX - dragStart.x,
        y: touch.clientY - dragStart.y,
      });
    } else if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      const newDist = Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
      if (touchMetaRef.current.pinchDist > 0) {
        const factor = newDist / touchMetaRef.current.pinchDist;
        setZoom((prev) => Math.max(0.6, Math.min(8.0, prev * factor)));
      }
      touchMetaRef.current.pinchDist = newDist;
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (e.touches.length === 0) {
      setIsDragging(false);
      const touch = e.changedTouches[0];
      if (touch && canvasRef.current) {
        const moved = Math.hypot(
          touch.clientX - touchMetaRef.current.startX,
          touch.clientY - touchMetaRef.current.startY
        );
        if (moved < 12) {
          const rect = canvasRef.current.getBoundingClientRect();
          const clickX = touch.clientX - rect.left;
          const clickY = touch.clientY - rect.top;
          const width = rect.width;
          const height = rect.height;

          const transformedX = (clickX - (width / 2 + pan.x)) / zoom;
          const transformedY = (clickY - (height / 2 + pan.y)) / zoom;

          const natW = activeFrame?.imageWidth || 256;
          const natH = activeFrame?.imageHeight || (activeFrame?.detectorArray === 6 ? 144 : 256);
          const scale = 512 / natW;
          const imgH = 512 * (natH / natW);

          for (const cand of candidates) {
            const pos = cand.epochPositions[activeFrameIndex] || cand.epochPositions[0];
            const cx = (pos.x + 0.5) * scale - 256;
            const cy = (pos.y + 0.5) * scale - imgH / 2;
            const dist = Math.hypot(transformedX - cx, transformedY - cy);
            if (dist < 32 / zoom) {
              onSelectCandidate(cand.id);
              return;
            }
          }
        }
      }
    }
  };

  return (
    <div
      ref={containerRef}
      className="relative flex-1 h-[calc(100vh-3rem-4rem)] bg-paper-950 overflow-hidden cursor-crosshair select-none touch-none"
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onClick={handleCanvasClick}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <canvas ref={canvasRef} className="w-full h-full block" />

      {/* Coordinate HUD / Scientist Telemetry HUD */}
      {isScientistMode ? (
        <div className="absolute top-2.5 left-2.5 bg-paper-950/95 border-2 border-emerald-500/60 shadow-xl rounded-lg p-3 text-[11px] font-mono text-paper-200 pointer-events-none backdrop-blur-sm z-20 max-w-sm space-y-2">
          <div className="flex items-center justify-between border-b border-paper-800 pb-1.5">
            <span className="text-emerald-400 font-bold uppercase tracking-wider text-[10px] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              SPHEREx Astrophysics HUD (L2/L3)
            </span>
            <span className="text-[10px] text-paper-400 bg-paper-900 px-1.5 py-0.5 rounded border border-paper-700">
              ICRS J2000
            </span>
          </div>

          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
            <div>
              <span className="text-paper-500">RA (J2000): </span>
              <span className="text-emerald-300 font-semibold">{cursorCoords?.ra || '17h 57m 48.5s'}</span>
            </div>
            <div>
              <span className="text-paper-500">Dec (J2000): </span>
              <span className="text-emerald-300 font-semibold">{cursorCoords?.dec || '+04° 41\' 36.1"'}</span>
            </div>
            <div>
              <span className="text-paper-500">Plate Scale: </span>
              <span className="text-paper-200">{(6.2 / zoom).toFixed(2)}″/px</span>
            </div>
            <div>
              <span className="text-paper-500">PSF FWHM: </span>
              <span className="text-paper-200">~1.42 px (8.8″)</span>
            </div>
            <div>
              <span className="text-paper-500">Surface Flux: </span>
              <span className="text-emerald-400 font-medium">12.43 MJy/sr</span>
            </div>
            <div>
              <span className="text-paper-500">Est. SNR: </span>
              <span className="text-emerald-400 font-medium">18.4 σ</span>
            </div>
            <div>
              <span className="text-paper-500">Zodi IPD Model: </span>
              <span className="text-paper-300">DIRBE v4.1</span>
            </div>
            <div>
              <span className="text-paper-500">WCS Matrix: </span>
              <span className="text-paper-400">CD1_1: -1.72e-3</span>
            </div>
          </div>
          <div className="text-[9px] text-paper-500 border-t border-paper-800/80 pt-1 flex items-center justify-between">
            <span>Grid: Equat. RA/Dec lines</span>
            <span className="text-emerald-500/80">Photometric cal: ±1.8%</span>
          </div>
        </div>
      ) : (
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
      )}

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

      {/* Simultaneous Background ML Analysis Banner (only shown while running to avoid right-side clutter) */}
      {mlAnalysisStatus && mlAnalysisStatus.state === 'running' && (
        <div className="absolute bottom-11 left-2.5 right-2.5 sm:left-auto sm:right-2.5 sm:w-88 z-25 pointer-events-auto anim-fall">
          <div className="bg-paper-950/95 backdrop-blur-md border-2 border-emerald-400/80 rounded-xl p-2.5 shadow-[0_0_25px_rgba(16,185,129,0.25)] space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Cpu className="w-3.5 h-3.5 text-emerald-400 animate-spin shrink-0" />
                <span className="text-[10px] font-mono font-bold text-emerald-300">
                  ML Analysis Running Simultaneously...
                </span>
              </div>
              <span className="text-[9px] font-mono font-bold text-paper-200 bg-paper-900 px-1.5 py-0.5 rounded border border-paper-800">
                Step {mlAnalysisStatus.stepIndex}/3 · {mlAnalysisStatus.progress}%
              </span>
            </div>
            <p className="text-[10px] font-mono text-paper-300 truncate">
              {mlAnalysisStatus.stage}
            </p>
            <div className="w-full h-1.5 bg-paper-900 rounded-full overflow-hidden border border-paper-800">
              <div
                className="h-full bg-gradient-to-r from-emerald-400 to-sky-400 transition-all duration-300"
                style={{ width: `${mlAnalysisStatus.progress}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Viewport Toolbar: Quick Layer Toggle + Colormap + Zoom */}
      <div className="absolute top-2.5 right-2.5 bg-paper-900/95 border-2 border-black p-1 rounded-xl flex items-center space-x-1 z-10 shadow-lg">
        {onChangeSubtractionMode && (
          <div className="hidden sm:flex items-center gap-1 pr-1.5 mr-1 border-r border-paper-800 font-mono text-[10px]">
            <button
              type="button"
              onClick={() => onChangeSubtractionMode('raw_calibrated')}
              className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                subtractionMode === 'raw_calibrated'
                  ? 'bg-emerald-400 text-gray-950 border-black font-bold'
                  : 'bg-paper-950 text-paper-300 border-paper-800 hover:text-white'
              }`}
              title="Aligned SPHEREx Exposure"
            >
              Aligned
            </button>
            <button
              type="button"
              onClick={() => onChangeSubtractionMode('epoch_difference')}
              className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                subtractionMode === 'epoch_difference'
                  ? 'bg-sky-400 text-gray-950 border-black font-bold'
                  : 'bg-paper-950 text-paper-300 border-paper-800 hover:text-white'
              }`}
              title="Leave-one-out Difference Image"
            >
              Diff
            </button>
            {activeFrame?.bloomDataUrl && (
              <button
                type="button"
                onClick={() => onChangeSubtractionMode('bloom_mask')}
                className={`px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                  subtractionMode === 'bloom_mask'
                    ? 'bg-amber-400 text-gray-950 border-black font-bold'
                    : 'bg-paper-950 text-amber-300 border-paper-800 hover:text-white'
                }`}
                title="BLOOM Detector Saturation Bitmask"
              >
                BLOOM
              </button>
            )}
          </div>
        )}
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
          {subtractionMode === 'epoch_difference' && (
            <>
              <span>|</span>
              <span className="text-sky-400 font-bold">Diff Image</span>
            </>
          )}
          {subtractionMode === 'bloom_mask' && (
            <>
              <span>|</span>
              <span className="text-amber-400 font-bold">BLOOM Mask</span>
            </>
          )}
        </div>
      )}
    </div>
  );
};
