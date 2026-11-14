import { useEffect, useCallback } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';

interface UrlParamsState {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
}

export function useUrlSync(
  state: UrlParamsState,
  onStateChange: (partial: Partial<UrlParamsState>) => void
) {
  // Read params on initial load
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const partial: Partial<UrlParamsState> = {};

      if (params.has('ra')) {
        const val = parseFloat(params.get('ra')!);
        if (!isNaN(val)) partial.ra = val;
      }
      if (params.has('dec')) {
        const val = parseFloat(params.get('dec')!);
        if (!isNaN(val)) partial.dec = val;
      }
      if (params.has('fov')) {
        const val = params.get('fov') as FOVOption;
        if (["1'", "3'", "5'", "10'"].includes(val)) partial.fov = val;
      }
      if (params.has('detector')) {
        const raw = params.get('detector');
        if (raw === 'all') partial.selectedArray = 'all';
        else {
          const num = parseInt(raw!, 10);
          if (num >= 1 && num <= 6) partial.selectedArray = num as DetectorArrayId;
        }
      }
      if (params.has('subtraction')) {
        const val = params.get('subtraction') as SubtractionMode;
        if (['raw_calibrated', 'zodi_reference_subtracted', 'epoch_difference'].includes(val)) {
          partial.subtractionMode = val;
        }
      }
      if (params.has('frame')) {
        const val = parseInt(params.get('frame')!, 10);
        if (!isNaN(val) && val >= 0) partial.activeFrameIndex = val;
      }

      if (Object.keys(partial).length > 0) {
        onStateChange(partial);
      }
    } catch {
      // Ignore URL parsing errors
    }
  }, []);

  // Sync to URL when state changes
  const updateUrl = useCallback((s: UrlParamsState) => {
    const params = new URLSearchParams();
    params.set('ra', s.ra.toFixed(6));
    params.set('dec', s.dec.toFixed(6));
    params.set('fov', s.fov);
    params.set('detector', String(s.selectedArray));
    params.set('subtraction', s.subtractionMode);
    params.set('frame', String(s.activeFrameIndex));

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
  }, []);

  useEffect(() => {
    updateUrl(state);
  }, [state.ra, state.dec, state.fov, state.selectedArray, state.subtractionMode, state.activeFrameIndex, updateUrl]);
}
