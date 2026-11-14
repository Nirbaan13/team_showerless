import React from 'react';
import type { SpherexEpochFrame } from '../types/spherex';
import { Play, Pause, SkipBack, SkipForward, Eye, FastForward, Clock } from 'lucide-react';

interface MoviePlayerControlsProps {
  frames: SpherexEpochFrame[];
  activeFrameIndex: number;
  onSelectFrame: (index: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  fps: number;
  onChangeFps: (fps: number) => void;
  blinkMode: boolean;
  onToggleBlinkMode: () => void;
  onStepForward: () => void;
  onStepBackward: () => void;
}

export const MoviePlayerControls: React.FC<MoviePlayerControlsProps> = ({
  frames,
  activeFrameIndex,
  onSelectFrame,
  isPlaying,
  onTogglePlay,
  fps,
  onChangeFps,
  blinkMode,
  onToggleBlinkMode,
  onStepForward,
  onStepBackward,
}) => {
  return (
    <div className="h-20 bg-space-900 border-t border-space-700/80 px-4 flex items-center justify-between text-xs select-none z-20">
      {/* 1. Playback Engine Controls */}
      <div className="flex items-center space-x-2">
        <button
          onClick={onStepBackward}
          className="p-2 rounded bg-space-850 border border-space-700 text-space-300 hover:text-cyan-300 hover:border-space-600 transition-colors"
          title="Previous Epoch Frame"
        >
          <SkipBack className="w-4 h-4" />
        </button>

        <button
          onClick={onTogglePlay}
          className="px-4 py-2 rounded bg-cyan-950 border border-cyan-400 text-cyan-300 hover:bg-cyan-900 transition-all shadow-[0_0_12px_rgba(0,242,254,0.25)] flex items-center gap-1.5 font-mono font-medium"
        >
          {isPlaying ? (
            <>
              <Pause className="w-4 h-4 fill-cyan-400" />
              <span>Pause</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-cyan-400" />
              <span>Blink Play</span>
            </>
          )}
        </button>

        <button
          onClick={onStepForward}
          className="p-2 rounded bg-space-850 border border-space-700 text-space-300 hover:text-cyan-300 hover:border-space-600 transition-colors"
          title="Next Epoch Frame"
        >
          <SkipForward className="w-4 h-4" />
        </button>

        <button
          onClick={onToggleBlinkMode}
          className={`px-3 py-2 rounded border font-mono flex items-center gap-1.5 transition-all ${
            blinkMode
              ? 'bg-amber-950/70 border-amber-400 text-amber-300'
              : 'bg-space-850 border-space-700 text-space-400 hover:text-space-200'
          }`}
          title="A/B Alternate Blink Comparison Mode"
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Blink A/B</span>
        </button>
      </div>

      {/* 2. Epoch Timeline Scrubber */}
      <div className="flex-1 max-w-xl mx-6 flex flex-col space-y-1.5">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-1 text-space-400">
            <Clock className="w-3 h-3 text-cyan-400" />
            <span>Epoch Timeline</span>
          </div>
          <span className="text-cyan-300 font-telemetry">
            Frame {activeFrameIndex + 1} of {frames.length}
          </span>
        </div>

        {/* Multi-Epoch Frame Buttons */}
        <div className="flex items-center space-x-1.5">
          {frames.map((frame, idx) => {
            const isActive = idx === activeFrameIndex;
            const isMissing = !frame.isAvailable;

            return (
              <button
                key={frame.frameId}
                disabled={isMissing}
                onClick={() => onSelectFrame(idx)}
                className={`flex-1 py-1 px-1 rounded text-center font-mono text-[10px] border transition-all truncate ${
                  isMissing
                    ? 'bg-space-950/40 border-dashed border-red-500/40 text-red-400/60 cursor-not-allowed'
                    : isActive
                    ? 'bg-cyan-950 border-cyan-400 text-cyan-200 font-semibold shadow-[0_0_8px_rgba(0,242,254,0.3)]'
                    : 'bg-space-850 border-space-700/80 text-space-400 hover:border-space-500 hover:text-space-200'
                }`}
                title={
                  isMissing
                    ? `Missing: ${frame.skipReason}`
                    : `Epoch ${idx + 1} (${frame.observationDate.split('T')[0]})`
                }
              >
                {isMissing ? '⚠️ Missing' : frame.observationDate.split('T')[0]}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. FPS Speed Control */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center gap-2 bg-space-850 border border-space-700/80 px-2.5 py-1.5 rounded">
          <FastForward className="w-3.5 h-3.5 text-space-400" />
          <span className="text-[10px] font-mono text-space-400">Speed:</span>
          <span className="font-mono text-cyan-300 font-medium text-[11px] w-10 text-right">
            {fps} fps
          </span>
          <input
            type="range"
            min="1"
            max="10"
            value={fps}
            onChange={(e) => onChangeFps(parseInt(e.target.value, 10))}
            className="w-20 accent-cyan-400 h-1 bg-space-700 rounded cursor-pointer"
          />
        </div>
      </div>
    </div>
  );
};
