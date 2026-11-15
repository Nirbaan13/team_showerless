import type { SpherexEpochFrame, SubtractionMode } from '../types/spherex';

/** A processing layer exists only when its own artifact was published. */
export function imageArtifact(frame: SpherexEpochFrame | undefined | null, mode: SubtractionMode): string | undefined {
  if (!frame) return undefined;
  switch (mode) {
    case 'raw_calibrated': return frame.imageDataUrl || undefined;
    case 'epoch_difference': return frame.residualDataUrl || undefined;
    case 'bloom_mask': return frame.bloomDataUrl || undefined;
    case 'zodi_reference_subtracted': return frame.zodiDataUrl || undefined;
  }
}

export function availableImageModes(frame: SpherexEpochFrame | undefined): SubtractionMode[] {
  return (['raw_calibrated', 'epoch_difference', 'bloom_mask', 'zodi_reference_subtracted'] as SubtractionMode[]).filter(mode => !!imageArtifact(frame, mode));
}
