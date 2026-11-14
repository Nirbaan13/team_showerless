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
    <div className="h-16 bg-nasa-surface border-t border-nasa-border px-4 flex items-center justify-between text-xs select-none z-20">
      {/* 1. Playback Engine Controls */}
      <div className="flex items-center space-x-1.5">
        <button
          onClick={onStepBackward}
          className="p-1.5 rounded bg-nasa-dark border border-nasa-border text-nasa-textMuted hover:text-white transition-colors"
          title="Previous Epoch Frame"
        >
          <SkipBack className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onTogglePlay}
          className="px-3 py-1.5 rounded bg-nasa-blue text-white hover:bg-blue-600 transition-colors flex items-center gap-1.5 font-mono text-[11px] font-medium"
        >
          {isPlaying ? (
            <>
              <Pause className="w-3.5 h-3.5 fill-white" />
              <span>Pause</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Blink Play</span>
            </>
          )}
        </button>

        <button
          onClick={onStepForward}
          className="p-1.5 rounded bg-nasa-dark border border-nasa-border text-nasa-textMuted hover:text-white transition-colors"
          title="Next Epoch Frame"
        >
          <SkipForward className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onToggleBlinkMode}
          className={`px-2.5 py-1.5 rounded border font-mono text-[11px] flex items-center gap-1.5 transition-colors ${
            blinkMode
              ? 'bg-blue-900/50 border-blue-500 text-blue-200'
              : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:text-nasa-textMain'
          }`}
          title="A/B Alternate Blink Comparison Mode"
        >
          <Eye className="w-3 h-3" />
          <span>Blink A/B</span>
        </button>
      </div>

      {/* 2. Epoch Timeline Scrubber */}
      <div className="flex-1 max-w-xl mx-6 flex flex-col space-y-1">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-1 text-nasa-textMuted">
            <Clock className="w-3 h-3 text-blue-400" />
            <span>Epoch Timeline</span>
          </div>
          <span className="text-nasa-textMain font-medium">
            Frame {activeFrameIndex + 1} of {frames.length}
          </span>
        </div>

        {/* Multi-Epoch Frame Buttons */}
        <div className="flex items-center space-x-1">
          {frames.map((frame, idx) => {
            const isActive = idx === activeFrameIndex;
            const isMissing = !frame.isAvailable;

            return (
              <button
                key={frame.frameId}
                disabled={isMissing}
                onClick={() => onSelectFrame(idx)}
                className={`flex-1 py-1 px-1 rounded text-center font-mono text-[10px] border transition-colors truncate ${
                  isMissing
                    ? 'bg-nasa-dark/40 border-dashed border-red-500/40 text-red-400/60 cursor-not-allowed'
                    : isActive
                    ? 'bg-blue-900/50 border-blue-500 text-blue-200 font-semibold'
                    : 'bg-nasa-dark border-nasa-border text-nasa-textMuted hover:border-nasa-subtle hover:text-nasa-textMain'
                }`}
                title={
                  isMissing
                    ? `Missing: ${frame.skipReason}`
                    : `Epoch ${idx + 1} (${frame.observationDate.split('T')[0]})`
                }
              >
                {isMissing ? 'Offline' : frame.observationDate.split('T')[0]}
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. FPS Speed Control */}
      <div className="flex items-center space-x-2">
        <div className="flex items-center gap-1.5 bg-nasa-dark border border-nasa-border px-2 py-1 rounded">
          <FastForward className="w-3 h-3 text-nasa-textMuted" />
          <span className="text-[10px] font-mono text-nasa-textMuted">FPS:</span>
          <span className="font-mono text-blue-300 font-medium text-[11px] w-6 text-right">
            {fps}
          </span>
          <input
            type="range"
            min="1"
            max="10"
            value={fps}
            onChange={(e) => onChangeFps(parseInt(e.target.value, 10))}
            className="w-16 accent-blue-500 h-1 bg-nasa-border rounded cursor-pointer"
          />
        </div>
      </div>
    </div>
  );
};
