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
    <div className="h-16 bg-paper-900 border-t border-paper-800 px-4 flex items-center justify-between text-xs select-none z-20">
      {/* 1. Playback Engine Controls */}
      <div className="flex items-center space-x-1.5">
        <button
          onClick={onStepBackward}
          className="p-1.5 rounded bg-paper-950 border border-paper-800 text-paper-400 hover:text-paper-100 hover:border-paper-700 transition-colors"
          title="Previous Epoch Frame"
        >
          <SkipBack className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onTogglePlay}
          className="px-3.5 py-1.5 rounded bg-ochre-400 hover:bg-ochre-300 text-paper-950 transition-colors flex items-center gap-1.5 font-mono text-[11px] font-semibold"
        >
          {isPlaying ? (
            <>
              <Pause className="w-3.5 h-3.5 fill-paper-950" />
              <span>Pause</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-paper-950" />
              <span>Play Movie</span>
            </>
          )}
        </button>

        <button
          onClick={onStepForward}
          className="p-1.5 rounded bg-paper-950 border border-paper-800 text-paper-400 hover:text-paper-100 hover:border-paper-700 transition-colors"
          title="Next Epoch Frame"
        >
          <SkipForward className="w-3.5 h-3.5" />
        </button>

        {/* Clyde Tombaugh Blink Comparator Mode */}
        <button
          onClick={onToggleBlinkMode}
          className={`px-2.5 py-1.5 rounded border font-mono text-[11px] flex items-center gap-1.5 transition-colors ${
            blinkMode
              ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-semibold'
              : 'bg-paper-950 border-paper-800 text-paper-400 hover:text-paper-200 hover:border-paper-700'
          }`}
          title="Alternate rapidly between 2 observation dates to spot moving objects"
        >
          <Eye className="w-3 h-3 text-ochre-400" />
          <span>Blink (A / B)</span>
        </button>
      </div>

      {/* 2. Epoch Timeline Scrubber */}
      <div className="flex-1 max-w-xl mx-6 flex flex-col space-y-1">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-1 text-paper-400">
            <Clock className="w-3 h-3 text-ochre-400" />
            <span>Epoch Timeline</span>
          </div>
          <span className="text-paper-200 font-medium">
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
                    ? 'bg-paper-950/40 border-dashed border-red-500/40 text-red-400/60 cursor-not-allowed'
                    : isActive
                    ? 'bg-paper-800 border-ochre-400 text-ochre-300 font-semibold'
                    : 'bg-paper-950 border-paper-800 text-paper-400 hover:border-paper-700 hover:text-paper-200'
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
        <div className="flex items-center gap-1.5 bg-paper-950 border border-paper-800 px-2.5 py-1 rounded">
          <FastForward className="w-3 h-3 text-paper-400" />
          <span className="text-[10px] font-mono text-paper-400">Speed:</span>
          <span className="font-mono text-ochre-300 font-semibold text-[11px] w-9 text-right">
            {fps} fps
          </span>
          <input
            type="range"
            min="1"
            max="10"
            value={fps}
            onChange={(e) => onChangeFps(parseInt(e.target.value, 10))}
            className="w-16 accent-amber-500 h-1 bg-paper-800 rounded cursor-pointer"
          />
        </div>
      </div>
    </div>
  );
};
