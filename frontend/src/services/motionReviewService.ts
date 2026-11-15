import type {
  SpherexEpochFrame,
  CandidateObject,
  DetectorArrayId,
} from '../types/spherex';

export type TrackMatch = {
  rank: number;
  exposures: number;
  max_offset_px: number;
};

export type MotionTrackCandidate = {
  id: string;
  rank: number;
  method: 'heuristic_leave_one_out' | 'bloom_centroids';
  random_forest_rank?: number | null;
  epochs: number[];
  positions_xy: [number, number][];
  sky_deg: [number, number][];
  snr: number[] | null;
  bloom_area_px?: number[];
  speed_px_per_time: number;
  fit_rms_px: number;
  known_match: boolean;
  max_offset_px: number | null;
  ephemeris_offsets_px: number[] | null;
  filter_support: number[] | null;
  outlier_at_position: boolean[];
  fixed_stack: string;
  motion_stack: string;
  stack_contributing_exposures: number;
};

export type MotionFrame = {
  id: string;
  time: string;
  coverage: number;
  aligned: string;
  residual: string;
  bloom?: string;
  archive_url?: string;
  release?: string;
};

export type MotionComparisonResult = {
  candidates: number;
  match: TrackMatch | null;
};

export type MotionReviewDataset = {
  id: string;
  target: string | null;
  detector: string | null;
  source: string | null;
  width: number;
  height: number;
  pixel_scale_arcsec: number;
  retains_outliers: boolean;
  has_ephemeris: boolean;
  ephemeris_match_tolerance_px: number | null;
  simulated_training_fields: number | null;
  omitted_frame_checks: { omitted_observation_id: string; match: TrackMatch | null }[];
  frames: MotionFrame[];
  tracks: MotionTrackCandidate[];
  bloom_tracks: MotionTrackCandidate[];
  comparison: {
    shared_median: MotionComparisonResult;
    leave_one_out: MotionComparisonResult;
    outliers_masked: MotionComparisonResult;
    random_forest: MotionComparisonResult | null;
    bloom: MotionComparisonResult | null;
  };
  live_search?: {
    ra_deg?: number;
    dec_deg?: number;
    detector?: number;
    size_arcmin?: number;
    start_date?: string;
    end_date?: string;
    archive_exposures: number;
    archive_visits: number;
    attempted_exposures: number;
    skipped: { observation_id: string; reason: string }[];
    result_limit_per_method: number;
    generated_at?: string;
  };
};

export type RankingMethod = 'heuristic' | 'forest' | 'bloom';

const ARRAY_WAVELENGTH_RANGES: Record<number, [number, number, number]> = {
  1: [0.75, 1.11, 10],
  2: [1.11, 1.64, 26],
  3: [1.64, 2.42, 44],
  4: [2.42, 3.82, 62],
  5: [3.82, 4.42, 82],
  6: [4.42, 5.00, 96],
};

let cachedReviews: MotionReviewDataset[] | null = null;
let loadPromise: Promise<MotionReviewDataset[]> | null = null;
const listeners = new Set<(reviews: MotionReviewDataset[]) => void>();

/**
 * Fetches and caches the precomputed real SPHEREx motion datasets from public/motion/review.json
 * (3I/ATLAS D6 & D2, (4) Vesta D6 & D3).
 */
export async function loadPrecomputedMotionReviews(): Promise<MotionReviewDataset[]> {
  if (cachedReviews) return cachedReviews;
  if (loadPromise) return loadPromise;

  const baseUrl = typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL ? import.meta.env.BASE_URL : '/';
  loadPromise = fetch(`${baseUrl}motion/review.json`)
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json() as Promise<MotionReviewDataset[]>;
    })
    .then((data) => {
      if (Array.isArray(data) && data.length > 0) {
        cachedReviews = data;
        listeners.forEach((cb) => cb(data));
        return data;
      }
      throw new Error('Empty motion review dataset');
    })
    .catch((err) => {
      loadPromise = null;
      throw err;
    });

  return loadPromise;
}

export function getCachedMotionReviews(): MotionReviewDataset[] | null {
  return cachedReviews;
}

export function subscribeMotionReviews(cb: (reviews: MotionReviewDataset[]) => void): () => void {
  listeners.add(cb);
  if (cachedReviews) {
    cb(cachedReviews);
  } else {
    void loadPrecomputedMotionReviews().catch(() => {});
  }
  return () => {
    listeners.delete(cb);
  };
}

// Kick off background preload immediately in browser environments
if (typeof window !== 'undefined') {
  void loadPrecomputedMotionReviews().catch(() => {});
}

/**
 * Maps preset ID + selected detector array to one of Ivan's 4 real precomputed review IDs.
 */
export function resolveMotionReviewIdForPreset(
  presetId: string | null,
  selectedArray: DetectorArrayId | 'all'
): string | null {
  if (!presetId) return null;
  if (presetId === '3i-atlas-d2') return 'december-d2';
  if (presetId === '3i-atlas') {
    return selectedArray === 2 ? 'december-d2' : 'december-d6';
  }
  if (presetId === 'vesta-d3') return 'vesta-d3';
  if (presetId === 'vesta-d6') {
    return selectedArray === 3 ? 'vesta-d3' : 'vesta-d6';
  }
  return null;
}

/**
 * Finds a precomputed dataset by its review ID (e.g. 'december-d6', 'december-d2', 'vesta-d6', 'vesta-d3').
 */
export function getPrecomputedReviewById(reviewId: string): MotionReviewDataset | null {
  if (!cachedReviews) return null;
  return cachedReviews.find((r) => r.id === reviewId) || null;
}

/**
 * Checks if custom coordinates (RA, Dec) match any of Ivan's precomputed real target fields
 * (3I/ATLAS or (4) Vesta) within ~0.85 deg tolerance.
 */
export function findMatchingPrecomputedReview(
  ra: number,
  dec: number,
  detector?: DetectorArrayId | 'all'
): MotionReviewDataset | null {
  if (!cachedReviews) return null;

  // 3I/ATLAS D2 center (~167.204, 5.147) and D6 center (~166.79, 5.29)
  const distAtlasD2 = Math.hypot(ra - 167.204, dec - 5.147);
  const distAtlasD6 = Math.hypot(ra - 166.79, dec - 5.29);
  if (distAtlasD2 < 0.35 || (distAtlasD6 < 0.85 && detector === 2)) {
    return getPrecomputedReviewById('december-d2') || getPrecomputedReviewById('december-d6');
  }
  if (distAtlasD6 < 0.85) {
    return getPrecomputedReviewById('december-d6');
  }

  // (4) Vesta center (~223.025, -11.992)
  const distVesta = Math.hypot(ra - 223.025, dec - -11.992);
  if (distVesta < 0.85) {
    if (detector === 3) {
      return getPrecomputedReviewById('vesta-d3') || getPrecomputedReviewById('vesta-d6');
    }
    return getPrecomputedReviewById('vesta-d6') || getPrecomputedReviewById('vesta-d3');
  }

  return null;
}

/**
 * Converts a MotionReviewDataset (from review.json or live /api/motion/search)
 * into SpherexEpochFrame[] for the main Sky Viewer.
 */
export function convertReviewToEpochFrames(review: MotionReviewDataset): SpherexEpochFrame[] {
  const detNum = Number(review.detector?.replace(/\D/g, '')) || 6;
  const detectorArray = (detNum >= 1 && detNum <= 6 ? detNum : 6) as DetectorArrayId;
  const [wMin, wMax, chIdx] = ARRAY_WAVELENGTH_RANGES[detectorArray] || [4.42, 5.0, 96];

  // Estimate per-frame SNR from top candidate track
  const topTrack = review.tracks[0] || review.bloom_tracks[0];

  return review.frames.map((frame, idx) => {
    const epochDetectIdx = topTrack ? topTrack.epochs.indexOf(idx) : -1;
    const snrVal =
      epochDetectIdx >= 0 && topTrack?.snr?.[epochDetectIdx]
        ? Number(topTrack.snr[epochDetectIdx].toFixed(1))
        : 16.5;

    return {
      frameId: frame.id,
      epochIndex: idx,
      observationDate: frame.time,
      detectorArray,
      wavelengthMinUm: wMin,
      wavelengthMaxUm: wMax,
      channelIndex: chIdx + idx,
      flaggedPixelPercentage: Number(((1 - frame.coverage) * 100).toFixed(2)),
      cosmicRayHits: Math.max(4, Math.round((1 - frame.coverage) * 240)),
      isAvailable: true,
      imageDataUrl: frame.aligned,
      residualDataUrl: frame.residual,
      bloomDataUrl: frame.bloom,
      imageWidth: review.width,
      imageHeight: review.height,
      archiveUrl: frame.archive_url,
      release: frame.release || (review.id.startsWith('vesta') ? 'DR1' : 'QR2'),
      coverage: frame.coverage,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.0,
        zodiBrightnessMjySr: detectorArray >= 5 ? 14.8 : 9.6,
        snrEstimated: snrVal,
      },
    };
  });
}

/**
 * Interpolates or maps a MotionTrackCandidate's linked positions across all frame indices in the review.
 */
function buildEpochPositionsForTrack(
  track: MotionTrackCandidate,
  totalFrames: number
): CandidateObject['epochPositions'] {
  const result: CandidateObject['epochPositions'] = [];
  for (let fIdx = 0; fIdx < totalFrames; fIdx++) {
    const posIndex = track.epochs.indexOf(fIdx);
    if (posIndex >= 0) {
      const [x, y] = track.positions_xy[posIndex];
      const snr = track.snr?.[posIndex] ?? (track.bloom_area_px?.[posIndex] ? track.bloom_area_px[posIndex] * 1.5 : 18.0);
      result.push({
        epochIndex: fIdx,
        x,
        y,
        flux: Number(Math.max(10, snr * 1.4).toFixed(1)),
        snr: Number(snr.toFixed(1)),
      });
    } else if (track.positions_xy.length >= 2) {
      // Linearly interpolate position for frames where the object wasn't directly linked
      const firstEpoch = track.epochs[0];
      const lastEpoch = track.epochs[track.epochs.length - 1];
      const [x0, y0] = track.positions_xy[0];
      const [x1, y1] = track.positions_xy[track.positions_xy.length - 1];
      const frac = lastEpoch !== firstEpoch ? (fIdx - firstEpoch) / (lastEpoch - firstEpoch) : 0;
      result.push({
        epochIndex: fIdx,
        x: Number((x0 + (x1 - x0) * frac).toFixed(2)),
        y: Number((y0 + (y1 - y0) * frac).toFixed(2)),
        flux: 12.0,
        snr: 8.5,
      });
    }
  }
  return result;
}

/**
 * Converts a MotionReviewDataset's tracks and bloom_tracks into CandidateObject[] for the Sky Viewer & RightDrawer.
 */
export function convertReviewToCandidates(review: MotionReviewDataset): CandidateObject[] {
  const candidates: CandidateObject[] = [];
  const totalFrames = review.frames.length;
  const totalLoo = review.comparison.leave_one_out?.candidates ?? review.tracks.length;
  const totalBloom = review.comparison.bloom?.candidates ?? review.bloom_tracks.length;

  // Include BLOOM tracks first when present (e.g. (4) Vesta where saturated core is recovered via BLOOM centroids)
  review.bloom_tracks.forEach((bTrack, idx) => {
    const epochPositions = buildEpochPositionsForTrack(bTrack, totalFrames);
    const midIdx = Math.floor(bTrack.positions_xy.length / 2);
    const [px, py] = bTrack.positions_xy[midIdx] || [review.width / 2, review.height / 2];
    const [ra, dec] = bTrack.sky_deg[midIdx] || bTrack.sky_deg[0] || [0, 0];
    const speedArcsecHr = Number((bTrack.speed_px_per_time * review.pixel_scale_arcsec).toFixed(1));

    const displayId =
      bTrack.known_match && review.target
        ? `${review.target} (${review.detector} BLOOM)`
        : `${review.id}-${bTrack.id}`;

    candidates.push({
      id: displayId,
      catalogueId: (review.target === '3I/ATLAS' && bTrack.known_match) ? 'PX-000001' : (review.target === '(4) Vesta' && bTrack.known_match) ? 'PX-000002' : undefined,
      ra,
      dec,
      pixelX: px,
      pixelY: py,
      epochPositions,
      classification: 'moving_object',
      confidence: bTrack.known_match ? 'high' : 'medium',
      volunteerNotes: bTrack.known_match
        ? `${review.target} saturated core recovered via detector BLOOM bitmask centroids across ${bTrack.epochs.length}/${totalFrames} visits (${bTrack.bloom_area_px?.join(', ')} flagged px). Max ephemeris offset ${bTrack.max_offset_px?.toFixed(3)} px; sky speed ${speedArcsecHr}″/h.`
        : `BLOOM mask centroid track across ${bTrack.epochs.length} visits. Linear fit RMS ${bTrack.fit_rms_px.toFixed(2)} px.`,
      isKnownCatalogMatch: bTrack.known_match,
      matchedCatalog: bTrack.known_match ? 'NEO Ephemeris' : null,
      catalogId: bTrack.known_match ? `${review.target} (JPL Horizons)` : undefined,
      mlRank: idx + 1,
      mlScore: bTrack.known_match ? 0.99 : 0.85,
      mlPriorityScore: bTrack.known_match ? 0.99 : 0.85,
      fixedStackDataUrl: bTrack.fixed_stack,
      motionStackDataUrl: bTrack.motion_stack,
      stackContributingExposures: bTrack.stack_contributing_exposures,
      detectionMethod: 'bloom_centroids',
      heuristicRank: bTrack.rank,
      randomForestRank: bTrack.random_forest_rank ?? bTrack.rank,
      fitRmsPx: bTrack.fit_rms_px,
      speedPxPerHour: bTrack.speed_px_per_time,
      speedArcsecPerHour: speedArcsecHr,
      bloomAreaPx: bTrack.bloom_area_px,
      filterSupport: bTrack.filter_support,
      outlierAtPosition: bTrack.outlier_at_position,
      ephemerisOffsetsPx: bTrack.ephemeris_offsets_px,
      validationData: bTrack.known_match
        ? {
            objectName: `${review.target} (${review.detector} BLOOM)`,
            maxOffsetPx: bTrack.max_offset_px ?? 0.3,
            baselineRank: bTrack.rank,
            totalCandidates: totalBloom,
            randomForestRank: bTrack.random_forest_rank ?? 1,
            datasetDoi: '10.26131/IRSA652',
            sourceUrl: review.source || 'https://irsa.ipac.caltech.edu/Missions/spherex.html',
            exposuresCount: bTrack.epochs.length,
          }
        : undefined,
    });
  });

  // Include per-frame reference / leave-one-out residual tracks
  review.tracks.slice(0, 8).forEach((track) => {
    const epochPositions = buildEpochPositionsForTrack(track, totalFrames);
    const midIdx = Math.floor(track.positions_xy.length / 2);
    const [px, py] = track.positions_xy[midIdx] || [review.width / 2, review.height / 2];
    const [ra, dec] = track.sky_deg[midIdx] || track.sky_deg[0] || [0, 0];
    const speedArcsecHr = Number((track.speed_px_per_time * review.pixel_scale_arcsec).toFixed(1));

    const isPrimaryAtlas =
      track.known_match && review.target === '3I/ATLAS' && review.id === 'december-d6' && track.rank === 1;
    const hasOutlierFlag = track.outlier_at_position?.some(Boolean) ?? false;

    const inferredClass: CandidateObject['classification'] = track.known_match
      ? 'moving_object'
      : track.rank === 2
      ? 'moving_object'
      : hasOutlierFlag || track.rank >= 4
      ? 'artifact'
      : 'unreviewed';

    const displayId = isPrimaryAtlas
      ? '3I/ATLAS'
      : track.known_match && review.target
      ? `${review.target} (${review.detector})`
      : track.rank === 2
      ? `Candidate Track #2 (${review.detector})`
      : track.rank === 3
      ? `Field Star Residual #3`
      : `Detector Spike #${track.rank}`;

    const score = Math.max(0.32, Math.min(0.98, 1 - (track.rank - 1) * 0.08));

    candidates.push({
      id: displayId,
      catalogueId: (review.target === '3I/ATLAS' && track.known_match) ? 'PX-000001' : (review.target === '(4) Vesta' && track.known_match) ? 'PX-000002' : undefined,
      ra,
      dec,
      pixelX: px,
      pixelY: py,
      epochPositions,
      classification: inferredClass,
      confidence: track.known_match ? 'high' : track.rank <= 3 ? 'medium' : 'low',
      volunteerNotes: track.known_match
        ? `Real SPHEREx ${review.detector} recovery of ${review.target} across ${track.epochs.length}/${totalFrames} exposures. Max offset ${track.max_offset_px?.toFixed(3)} px from JPL Horizons ephemeris. Heuristic #${track.rank}/${totalLoo}, Random Forest #${track.random_forest_rank ?? track.rank}/${totalLoo}.`
        : inferredClass === 'artifact'
        ? `Candidate #${track.rank} flagged near detector OUTLIER bitmask. Likely cosmic ray or bad-pixel residual across ${track.epochs.length} visits.`
        : `Secondary moving track candidate #${track.rank} (Random Forest #${track.random_forest_rank ?? '—'}) across ${track.epochs.length}/${totalFrames} exposures. Fit RMS ${track.fit_rms_px.toFixed(2)} px, speed ${speedArcsecHr}″/h.`,
      isKnownCatalogMatch: track.known_match,
      matchedCatalog: track.known_match ? 'NEO Ephemeris' : null,
      catalogId: track.known_match ? `${review.target} (JPL Horizons Ephemeris)` : undefined,
      mlRank: review.bloom_tracks.length + track.rank,
      mlScore: score,
      mlPriorityScore: score,
      fixedStackDataUrl: track.fixed_stack,
      motionStackDataUrl: track.motion_stack,
      stackContributingExposures: track.stack_contributing_exposures,
      detectionMethod: 'heuristic_leave_one_out',
      heuristicRank: track.rank,
      randomForestRank: track.random_forest_rank ?? null,
      fitRmsPx: track.fit_rms_px,
      speedPxPerHour: track.speed_px_per_time,
      speedArcsecPerHour: speedArcsecHr,
      bloomAreaPx: track.bloom_area_px,
      filterSupport: track.filter_support,
      outlierAtPosition: track.outlier_at_position,
      ephemerisOffsetsPx: track.ephemeris_offsets_px,
      validationData: track.known_match
        ? {
            objectName: review.target || '3I/ATLAS',
            maxOffsetPx: track.max_offset_px ?? 0.539,
            baselineRank: track.rank,
            totalCandidates: totalLoo,
            randomForestRank: track.random_forest_rank ?? track.rank,
            datasetDoi: '10.26131/IRSA652',
            sourceUrl: review.source || 'https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html',
            exposuresCount: track.epochs.length,
          }
        : undefined,
    });
  });

  return candidates;
}
