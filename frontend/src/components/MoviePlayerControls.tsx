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
      <div className="flex items-center space-x-1.5 shrink-0">
        <button
          onClick={onStepBackward}
          className="btn-tactile-sm p-1.5 rounded-lg bg-paper-950 border-2 border-black text-paper-400 hover:text-paper-100 cursor-pointer"
          title="Previous Epoch Frame"
        >
          <SkipBack className="w-3.5 h-3.5" />
        </button>

        <button
          onClick={onTogglePlay}
          className="btn-tactile px-3.5 py-1.5 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-gray-950 border-2 border-black font-mono text-[11px] font-bold cursor-pointer flex items-center gap-1.5"
        >
          {isPlaying ? (
            <>
              <Pause className="w-3.5 h-3.5 fill-gray-950" />
              <span>Pause</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-gray-950" />
              <span>Play Movie</span>
            </>
          )}
        </button>

        <button
          onClick={onStepForward}
          className="btn-tactile-sm p-1.5 rounded-lg bg-paper-950 border-2 border-black text-paper-400 hover:text-paper-100 cursor-pointer"
          title="Next Epoch Frame"
        >
          <SkipForward className="w-3.5 h-3.5" />
        </button>

        {/* Clyde Tombaugh Blink Comparator Mode */}
        <button
          onClick={onToggleBlinkMode}
          className={`btn-tactile-sm px-2.5 py-1.5 rounded-lg border-2 border-black font-mono text-[11px] font-semibold flex items-center gap-1.5 cursor-pointer ${
            blinkMode
              ? 'bg-emerald-400 text-gray-950 font-bold'
              : 'bg-paper-950 text-paper-300 hover:text-white'
          }`}
          title="Alternate rapidly between 2 observation dates to spot moving objects"
        >
          <Eye className={`w-3 h-3 ${blinkMode ? 'text-gray-950' : 'text-emerald-400'}`} />
          <span>Blink (A / B)</span>
        </button>
      </div>

      {/* 2. Epoch Timeline Scrubber */}
      <div className="flex-1 min-w-0 max-w-xl mx-2 sm:mx-4 md:mx-6 flex flex-col space-y-1">
        <div className="flex items-center justify-between text-[11px] font-mono">
          <div className="flex items-center gap-1 text-paper-400">
            <Clock className="w-3 h-3 text-emerald-400" />
            <span>Epoch Timeline</span>
          </div>
          <span className="text-paper-200 font-medium">
            Frame {activeFrameIndex + 1} of {frames.length}
          </span>
        </div>

        {/* Multi-Epoch Frame Buttons */}
        <div className="flex items-center space-x-1.5 overflow-x-auto pb-0.5">
          {frames.map((frame, idx) => {
            const isActive = idx === activeFrameIndex;
            const isMissing = !frame.isAvailable;

            return (
              <button
                key={frame.frameId}
                disabled={isMissing}
                onClick={() => onSelectFrame(idx)}
                className={`btn-tactile-sm flex-1 min-w-[70px] py-1 px-1 rounded-lg text-center font-mono text-[10px] border-2 border-black transition-all truncate cursor-pointer ${
                  isMissing
                    ? 'bg-paper-950/40 border-dashed border-red-500/40 text-red-400/60 cursor-not-allowed shadow-none'
                    : isActive
                    ? 'bg-emerald-400 text-gray-950 font-bold'
                    : 'bg-paper-950 text-paper-400 hover:text-paper-200'
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
      <div className="flex items-center space-x-2 shrink-0">
        <div className="flex items-center gap-1.5 bg-paper-950 border border-paper-800 px-2.5 py-1 rounded">
          <FastForward className="w-3 h-3 text-paper-400" />
          <span className="text-[10px] font-mono text-paper-400">Speed:</span>
          <span className="font-mono text-emerald-300 font-semibold text-[11px] w-9 text-right">
            {fps} fps
          </span>
          <input
            type="range"
            min="1"
            max="10"
            value={fps}
            onChange={(e) => onChangeFps(parseInt(e.target.value, 10))}
            className="w-14 sm:w-16 accent-emerald-400 h-1 bg-paper-800 rounded cursor-pointer"
          />
        </div>
      </div>
    </div>
  );
};
