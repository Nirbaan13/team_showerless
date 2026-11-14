import { useState, useEffect, useRef, useCallback } from 'react';
import type { SpherexEpochFrame } from '../types/spherex';

interface UseSpherexPlayerProps {
  frames: SpherexEpochFrame[];
  fps: number;
  isPlaying: boolean;
  blinkMode?: boolean;
  onFrameChange: (index: number) => void;
  currentIndex: number;
}

export function useSpherexPlayer({
  frames,
  fps,
  isPlaying,
  blinkMode = false,
  onFrameChange,
  currentIndex,
}: UseSpherexPlayerProps) {
  const [skippedNotice, setSkippedNotice] = useState<string | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const blinkPairRef = useRef<[number, number]>([0, 1]);

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

  // Compute valid A/B blink pair whenever frames change or blinkMode activates
  useEffect(() => {
    if (!blinkMode || frames.length <= 1) return;
    const availIndices = frames
      .map((f, idx) => (f.isAvailable ? idx : -1))
      .filter((idx) => idx >= 0);
    if (availIndices.length >= 2) {
      const frameA = availIndices[0];
      // Use the last available epoch as Frame B so motion displacement is maximal and obvious
      const frameB = availIndices[availIndices.length - 1];
      blinkPairRef.current = [frameA, frameB];
    }
  }, [blinkMode, frames]);

  const stepForward = useCallback(() => {
    if (blinkMode && frames.length > 1) {
      const [a, b] = blinkPairRef.current;
      onFrameChange(currentIndex === a ? b : a);
      return;
    }
    const next = getNextAvailableIndex(currentIndex, 1);
    onFrameChange(next);
  }, [blinkMode, frames.length, currentIndex, getNextAvailableIndex, onFrameChange]);

  const stepBackward = useCallback(() => {
    if (blinkMode && frames.length > 1) {
      const [a, b] = blinkPairRef.current;
      onFrameChange(currentIndex === a ? b : a);
      return;
    }
    const prev = getNextAvailableIndex(currentIndex, -1);
    onFrameChange(prev);
  }, [blinkMode, frames.length, currentIndex, getNextAvailableIndex, onFrameChange]);

  // Main playback / Blink A/B loop (runs when either Play Movie OR Blink A/B is active)
  useEffect(() => {
    if ((!isPlaying && !blinkMode) || frames.length <= 1) return;

    const intervalMs = blinkMode
      ? Math.max(180, Math.floor(700 / Math.max(1, fps / 2)))
      : Math.max(100, Math.floor(1000 / fps));

    const loop = () => {
      timeoutRef.current = window.setTimeout(() => {
        if (blinkMode) {
          const [a, b] = blinkPairRef.current;
          const nextBlink = currentIndex === a ? b : a;
          onFrameChange(nextBlink);
        } else {
          const next = getNextAvailableIndex(currentIndex, 1);
          onFrameChange(next);
        }
      }, intervalMs);
    };

    loop();

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [isPlaying, blinkMode, fps, currentIndex, frames, getNextAvailableIndex, onFrameChange]);

  return {
    skippedNotice,
    clearSkippedNotice: () => setSkippedNotice(null),
    stepForward,
    stepBackward,
    blinkPair: blinkPairRef.current,
  };
}
