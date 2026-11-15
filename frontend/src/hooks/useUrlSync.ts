import { useEffect, useCallback } from 'react';
import type { FOVOption, DetectorArrayId, SubtractionMode } from '../types/spherex';

export interface UrlParamsState {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  subtractionMode: SubtractionMode;
  activeFrameIndex: number;
  candidateId?: string | null;
  tab?: 'home' | 'viewer' | 'feed' | 'report' | 'inference' | 'catalogue';
  presetId?: string | null;
  objectId?: string | null;
  archive?: string;
  observedFrom?: string;
  observedThrough?: string;
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

      const hasRa = params.has('ra');
      const hasDec = params.has('dec');

      if (hasRa) {
        const val = parseFloat(params.get('ra')!);
        if (!isNaN(val)) partial.ra = val;
      }
      if (hasDec) {
        const val = parseFloat(params.get('dec')!);
        if (!isNaN(val)) partial.dec = val;
      }
      if (params.has('archive')) partial.archive = params.get('archive')!;
      if (params.has('observed_from')) partial.observedFrom = params.get('observed_from')!;
      if (params.has('observed_through')) partial.observedThrough = params.get('observed_through')!;
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
        if (['raw_calibrated', 'zodi_reference_subtracted', 'epoch_difference', 'bloom_mask'].includes(val)) {
          partial.subtractionMode = val;
        }
      }
      if (params.has('frame')) {
        const val = parseInt(params.get('frame')!, 10);
        if (!isNaN(val) && val >= 0) partial.activeFrameIndex = val;
      }

      if (params.has('candidate')) {
        partial.candidateId = params.get('candidate');
      }

      if (params.has('preset')) {
        partial.presetId = params.get('preset');
      } else if (hasRa && hasDec) {
        // Direct coordinates provided: clear preset so custom frames are loaded
        partial.presetId = null;
      }
      if (params.has('object')) { partial.objectId = params.get('object'); partial.presetId = null; }

      if ((partial.archive && partial.archive !== 'irsa-spherex') || partial.observedFrom || partial.observedThrough) partial.presetId = null;
      if (params.has('tab')) {
        const requestedTab = params.get('tab') as UrlParamsState['tab'];
        if (['home', 'viewer', 'feed', 'report', 'inference', 'catalogue'].includes(requestedTab!)) {
          partial.tab = requestedTab;
        }
      } else if (hasRa && hasDec) {
        // Direct link to coordinates should open Sky Viewer
        partial.tab = 'viewer';
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
    const url = new URL(window.location.href);
    const params = url.searchParams;
    params.set('ra', s.ra.toFixed(6));
    params.set('dec', s.dec.toFixed(6));
    params.set('fov', s.fov);
    params.set('detector', String(s.selectedArray));
    params.set('subtraction', s.subtractionMode);
    params.set('frame', String(s.activeFrameIndex));
    for (const [key, value] of [['archive', s.archive], ['observed_from', s.observedFrom], ['observed_through', s.observedThrough]]) {
      if (value) params.set(key!, value); else params.delete(key!);
    }

    if (s.candidateId) {
      params.set('candidate', s.candidateId);
    } else {
      params.delete('candidate');
    }

    if (s.tab && s.tab !== 'home') {
      params.set('tab', s.tab);
    } else {
      params.delete('tab');
    }

    if (s.presetId) {
      params.set('preset', s.presetId);
    } else {
      params.delete('preset');
    }
    if (s.objectId) params.set('object', s.objectId); else params.delete('object');

    window.history.replaceState(window.history.state, '', url);
  }, []);

  useEffect(() => {
    updateUrl(state);
  }, [
    state.ra,
    state.dec,
    state.fov,
    state.selectedArray,
    state.subtractionMode,
    state.activeFrameIndex,
    state.candidateId,
    state.tab,
    state.presetId,
    state.objectId,
    state.archive, state.observedFrom, state.observedThrough,
    updateUrl,
  ]);
}
