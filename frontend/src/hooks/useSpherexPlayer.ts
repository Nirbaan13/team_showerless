import { useState, useEffect, useRef, useCallback } from 'react';
import type { SpherexEpochFrame } from '../types/spherex';

interface UseSpherexPlayerProps {
  frames: SpherexEpochFrame[];
  fps: number;
  isPlaying: boolean;
  onFrameChange: (index: number) => void;
  currentIndex: number;
}

export function useSpherexPlayer({
  frames,
  fps,
  isPlaying,
  onFrameChange,
  currentIndex,
}: UseSpherexPlayerProps) {
  const [skippedNotice, setSkippedNotice] = useState<string | null>(null);
  const timeoutRef = useRef<number | null>(null);

  // Clear notice after 3.5s
  useEffect(() => {
    if (skippedNotice) {
      const timer = window.setTimeout(() => setSkippedNotice(null), 3500);
      return () => clearTimeout(timer);
    }
  }, [skippedNotice]);

  const getNextAvailableIndex = useCallback(
    (fromIdx: number, step: 1 | -1 = 1): number => {
      if (frames.length === 0) return 0;
      let next = (fromIdx + step + frames.length) % frames.length;
      let loopCount = 0;

      while (!frames[next].isAvailable && loopCount < frames.length) {
        if (frames[next].skipReason) {
          setSkippedNotice(`Frame #${next + 1} skipped: ${frames[next].skipReason}`);
        }
        next = (next + step + frames.length) % frames.length;
        loopCount++;
      }

      // If all are unavailable, fallback to current
      if (loopCount >= frames.length) return fromIdx;
      return next;
    },
    [frames]
  );

  const stepForward = useCallback(() => {
    const next = getNextAvailableIndex(currentIndex, 1);
    onFrameChange(next);
  }, [currentIndex, getNextAvailableIndex, onFrameChange]);

  const stepBackward = useCallback(() => {
    const prev = getNextAvailableIndex(currentIndex, -1);
    onFrameChange(prev);
  }, [currentIndex, getNextAvailableIndex, onFrameChange]);

  // Main playback loop
  useEffect(() => {
    if (!isPlaying || frames.length <= 1) return;

    const intervalMs = Math.max(100, Math.floor(1000 / fps));

    const loop = () => {
      timeoutRef.current = window.setTimeout(() => {
        const next = getNextAvailableIndex(currentIndex, 1);
        onFrameChange(next);
      }, intervalMs);
    };

    loop();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [isPlaying, fps, currentIndex, frames, getNextAvailableIndex, onFrameChange]);

  return {
    skippedNotice,
    clearSkippedNotice: () => setSkippedNotice(null),
    stepForward,
    stepBackward,
  };
}
