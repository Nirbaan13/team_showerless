import React, { useState } from 'react';
import type { SpectralDataPoint } from '../types/spherex';
import { REFERENCE_MOLECULAR_LINES } from '../services/mockSpherexApi';

interface SpectrumPlotProps {
  data: SpectralDataPoint[];
  objectLabel: string;
}

export const SpectrumPlot: React.FC<SpectrumPlotProps> = ({ data, objectLabel: _objectLabel }) => {
  const [hoveredPoint, setHoveredPoint] = useState<SpectralDataPoint | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-space-500 font-mono text-xs">
        No spectral data loaded
      </div>
    );
  }

  // ViewBox bounds
  const svgWidth = 340;
  const svgHeight = 160;
  const padding = { top: 15, right: 15, bottom: 25, left: 35 };

  const plotW = svgWidth - padding.left - padding.right;
  const plotH = svgHeight - padding.top - padding.bottom;

  const minLambda = 0.75;
  const maxLambda = 5.0;

  const fluxValues = data.map((d) => d.fluxMjy);
  const minFlux = Math.max(0, Math.min(...fluxValues) * 0.85);
  const maxFlux = Math.max(...fluxValues) * 1.15;

  const getX = (lambda: number) => padding.left + ((lambda - minLambda) / (maxLambda - minLambda)) * plotW;
  const getY = (flux: number) => padding.top + plotH - ((flux - minFlux) / (maxFlux - minFlux)) * plotH;

  // Polyline points
  const pointsStr = data.map((d) => `${getX(d.wavelengthUm).toFixed(1)},${getY(d.fluxMjy).toFixed(1)}`).join(' ');

  return (
    <div className="bg-space-950 border border-space-700/80 rounded-md p-3 select-none">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-[11px] font-semibold text-space-200">
          Flux Density F_λ vs. Wavelength
        </span>
        <span className="text-[10px] font-mono text-cyan-400">
          WCS-WAVE (102 Bands)
        </span>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full h-auto overflow-visible"
        >
          {/* Reference Molecular Absorption Bands */}
          {REFERENCE_MOLECULAR_LINES.map((line) => {
            const x = getX(line.centerUm);
            const w = (line.widthUm / (maxLambda - minLambda)) * plotW;
            return (
              <g key={line.formula}>
                <rect
                  x={x - w / 2}
                  y={padding.top}
                  width={w}
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
                  strokeOpacity="0.6"
                />
              </g>
            );
          })}

          {/* Grid lines */}
          <line
            x1={padding.left}
            y1={padding.top + plotH}
            x2={padding.left + plotW}
            y2={padding.top + plotH}
            stroke="#21262d"
            strokeWidth="1"
          />
          <line
            x1={padding.left}
            y1={padding.top}
            x2={padding.left}
            y2={padding.top + plotH}
            stroke="#21262d"
            strokeWidth="1"
          />

          {/* Spectrum continuous curve */}
          <polyline
            fill="none"
            stroke="#00f2fe"
            strokeWidth="1.5"
            points={pointsStr}
          />

          {/* Interactive data points */}
          {data.map((pt) => {
            const cx = getX(pt.wavelengthUm);
            const cy = getY(pt.fluxMjy);
            return (
              <circle
                key={pt.channel}
                cx={cx}
                cy={cy}
                r={hoveredPoint?.channel === pt.channel ? 3.5 : 1.5}
                fill={hoveredPoint?.channel === pt.channel ? '#ffffff' : '#38bdf8'}
                className="cursor-pointer transition-all"
                onMouseEnter={() => setHoveredPoint(pt)}
              />
            );
          })}

          {/* Axis Labels */}
          <text
            x={padding.left}
            y={padding.top + plotH + 18}
            fill="#8b949e"
            fontSize="9"
            fontFamily="JetBrains Mono"
          >
            0.75 µm
          </text>
          <text
            x={padding.left + plotW / 2 - 14}
            y={padding.top + plotH + 18}
            fill="#8b949e"
            fontSize="9"
            fontFamily="JetBrains Mono"
          >
            2.8 µm
          </text>
          <text
            x={padding.left + plotW - 25}
            y={padding.top + plotH + 18}
            fill="#8b949e"
            fontSize="9"
            fontFamily="JetBrains Mono"
          >
            5.0 µm
          </text>
        </svg>

        {/* Hover Readout Tooltip */}
        {hoveredPoint && (
          <div className="absolute top-1 right-2 bg-space-900 border border-cyan-500/50 px-2 py-1 rounded text-[10px] font-mono text-cyan-300 shadow-md">
            Ch #{hoveredPoint.channel}: {hoveredPoint.wavelengthUm} µm | Flux: {hoveredPoint.fluxMjy} mJy
          </div>
        )}
      </div>

      {/* Molecular Line Legend */}
      <div className="mt-2.5 pt-2 border-t border-space-800 grid grid-cols-2 gap-1.5 text-[10px] font-mono">
        {REFERENCE_MOLECULAR_LINES.map((line) => (
          <div key={line.formula} className="flex items-center gap-1.5 text-space-400">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: line.color }} />
            <span className="text-space-200">{line.formula}</span>
            <span className="text-space-500">({line.centerUm} µm)</span>
          </div>
        ))}
      </div>
    </div>
  );
};
