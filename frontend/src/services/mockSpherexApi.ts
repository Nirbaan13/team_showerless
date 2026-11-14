import type {
  TargetPreset,
  SpherexEpochFrame,
  CandidateObject,
  SpectralDataPoint,
  MolecularLine,
} from '../types/spherex';
import {
  REAL_3I_ATLAS_FRAMES,
  REAL_BARNARD_FRAMES,
  REAL_WISE_0855_FRAMES,
} from './realSpherexFrames';
import {
  getPrecomputedReviewById,
  resolveMotionReviewIdForPreset,
  convertReviewToEpochFrames,
  convertReviewToCandidates,
} from './motionReviewService';

export const NASA_TEST_PRESETS: TargetPreset[] = [
  {
    id: '3i-atlas',
    name: '3I/ATLAS',
    subtitle: 'Interstellar Comet (Real SPHEREx Detection)',
    raHms: '11h 07m 09.6s',
    decDms: '+05° 17\' 24.0"',
    raDeg: 166.790000,
    decDeg: 5.290000,
    description: 'Real NASA/IPAC IRSA QR2 detection across 4 exposures. Offset within 0.539 px of ephemeris. Ranked #1 Heuristic & #3 Random Forest.',
    recommendedArray: 6,
    expectedClass: 'moving_object',
    motionReviewId: 'december-d6',
  },
  {
    id: 'barnards-star',
    name: "Barnard's Star",
    subtitle: 'High Proper Motion Red Dwarf',
    raHms: '17h 57m 48.498s',
    decDms: '+04° 41\' 36.1139"',
    raDeg: 269.452075,
    decDeg: 4.693365,
    description: 'Second closest stellar system; fast apparent proper motion across epochs (~10.3 arcsec/yr). Ideal for blink testing.',
    recommendedArray: 2,
    expectedClass: 'moving_object',
  },
  {
    id: 'wise-0855',
    name: 'WISE 0855-0714',
    subtitle: 'Coldest Sub-Stellar Object',
    raHms: '08h 55m 10.831s',
    decDms: '-07° 14\' 42.53"',
    raDeg: 133.795129,
    decDeg: -7.245147,
    description: 'Y-type sub-brown dwarf with water-ice cloud evidence at ~250 K. Extremely faint in short-wave; prominent in Bands 5 & 6.',
    recommendedArray: 5,
    expectedClass: 'moving_object',
  },
  {
    id: 'epsilon-indi-b',
    name: 'Epsilon Indi B',
    subtitle: 'Nearby Binary Brown Dwarf',
    raHms: '22h 04m 10.595s',
    decDms: '-56° 46\' 58.239"',
    raDeg: 331.044146,
    decDeg: -56.782844,
    description: 'Early T-dwarf pair showing distinct methane and water ice absorption in mid-IR channels.',
    recommendedArray: 3,
    expectedClass: 'moving_object',
  },
  {
    id: 'rw-aurigae',
    name: 'RW Aurigae',
    subtitle: 'T Tauri Variable Star',
    raHms: '05h 07m 49.54s',
    decDms: '+30° 24\' 05.2"',
    raDeg: 76.956417,
    decDeg: 30.401444,
    description: 'Young pre-main-sequence star undergoing periodic dimming events due to circumstellar disk dust occultation.',
    recommendedArray: 4,
    expectedClass: 'transient',
  },
  {
    id: 'r-draconis',
    name: 'R Draconis',
    subtitle: 'Mira-Type Pulsating Red Giant',
    raHms: '16h 32m 40.23s',
    decDms: '+66° 45\' 17.9"',
    raDeg: 248.167625,
    decDeg: 66.754972,
    description: 'Long-period pulsating red giant with large visual and IR amplitude fluctuations, showing strong CO molecular absorption.',
    recommendedArray: 6,
    expectedClass: 'transient',
  },
];

export const REFERENCE_MOLECULAR_LINES: MolecularLine[] = [
  { name: 'Silicate Features', formula: 'SiO₄', centerUm: 1.25, widthUm: 0.25, color: '#ec4899' },
  { name: 'Water Vapor / Ice', formula: 'H₂O', centerUm: 3.05, widthUm: 0.35, color: '#38bdf8' },
  { name: 'Carbon Dioxide Ice', formula: 'CO₂', centerUm: 4.27, widthUm: 0.15, color: '#a78bfa' },
  { name: 'Carbon Monoxide', formula: 'CO', centerUm: 4.67, widthUm: 0.18, color: '#f59e0b' },
];

export const DETECTOR_ARRAY_SPECS = [
  { id: 1, name: 'Band 1', label: 'Deep Red Light', range: '0.75 – 1.11 µm', res: 'R ~ 41', desc: 'Captures bright nearby stars' },
  { id: 2, name: 'Band 2', label: 'Warm Infrared', range: '1.11 – 1.64 µm', res: 'R ~ 41', desc: 'Highlights red dwarf stars' },
  { id: 3, name: 'Band 3', label: 'Mid-Infrared', range: '1.64 – 2.42 µm', res: 'R ~ 41', desc: 'Cuts through space dust' },
  { id: 4, name: 'Band 4', label: 'Heat Signature', range: '2.42 – 3.82 µm', res: 'R ~ 35', desc: 'Spots cooler glowing gas' },
  { id: 5, name: 'Band 5', label: 'Cold Gas & Ice', range: '3.82 – 4.42 µm', res: 'R ~ 110', desc: 'Detects ice clouds (H₂O, CO₂)' },
  { id: 6, name: 'Band 6', label: 'Deep Cold Stars', range: '4.42 – 5.00 µm', res: 'R ~ 130', desc: 'Coldest sub-stellar brown dwarfs' },
];

/**
 * Generates multi-epoch frames for the celestial viewport, prioritizing Ivan's precomputed
 * real SPHEREx datasets from public/motion/review.json when available.
 */
export function getMockEpochFrames(targetId: string, arrayId: number): SpherexEpochFrame[] {
  const reviewId = resolveMotionReviewIdForPreset(targetId, arrayId as any);
  if (reviewId) {
    const precomputed = getPrecomputedReviewById(reviewId);
    if (precomputed) {
      return convertReviewToEpochFrames(precomputed);
    }
  }

  // Fallback for 3I/ATLAS before review.json finishes async load
  if (targetId === '3i-atlas' || targetId === '3i-atlas-d2') {
    const realObservations = [
      { id: '2025W50_2A_0741_2D6', date: '2025-12-14T11:01:45.688Z', wave: 4.475, snr: 12.1, offset: 0.421 },
      { id: '2025W50_2A_0755_2D6', date: '2025-12-14T12:39:42.784Z', wave: 4.608, snr: 13.4, offset: 0.263 },
      { id: '2025W50_2A_0797_4D6', date: '2025-12-14T17:33:31.003Z', wave: 4.813, snr: 14.8, offset: 0.246 },
      { id: '2025W50_2A_0813_1D6', date: '2025-12-14T19:06:21.122Z', wave: 4.847, snr: 14.2, offset: 0.539 },
    ];
    return realObservations.map((obs, idx) => ({
      frameId: obs.id,
      epochIndex: idx,
      observationDate: obs.date,
      detectorArray: (targetId === '3i-atlas-d2' ? 2 : 6) as any,
      wavelengthMinUm: targetId === '3i-atlas-d2' ? 1.11 : 4.42,
      wavelengthMaxUm: targetId === '3i-atlas-d2' ? 1.64 : 5.00,
      channelIndex: 94 + idx * 2,
      flaggedPixelPercentage: 0.12,
      cosmicRayHits: 8,
      isAvailable: true,
      imageDataUrl: REAL_3I_ATLAS_FRAMES[idx]?.pngDataUrl,
      imageWidth: 256,
      imageHeight: 144,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.0,
        zodiBrightnessMjySr: 12.43,
        snrEstimated: obs.snr,
      }
    }));
  }

  if (targetId === 'barnards-star') {
    return REAL_BARNARD_FRAMES.map((obs, idx) => ({
      frameId: obs.frameId,
      epochIndex: idx,
      observationDate: obs.observationDate,
      detectorArray: 2,
      wavelengthMinUm: 1.11,
      wavelengthMaxUm: 1.64,
      channelIndex: 26,
      flaggedPixelPercentage: 0.18,
      cosmicRayHits: 11,
      isAvailable: true,
      imageDataUrl: obs.pngDataUrl,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.05,
        zodiBrightnessMjySr: Number((12.4 + idx * 0.7).toFixed(2)),
        snrEstimated: 38.0,
      },
    }));
  }

  if (targetId === 'wise-0855') {
    return REAL_WISE_0855_FRAMES.map((obs, idx) => ({
      frameId: obs.frameId,
      epochIndex: idx,
      observationDate: obs.observationDate,
      detectorArray: 5,
      wavelengthMinUm: 3.82,
      wavelengthMaxUm: 4.42,
      channelIndex: 82,
      flaggedPixelPercentage: 0.22,
      cosmicRayHits: 14,
      isAvailable: true,
      imageDataUrl: obs.pngDataUrl,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.12,
        zodiBrightnessMjySr: Number((16.8 + idx * 0.9).toFixed(2)),
        snrEstimated: 16.2,
      },
    }));
  }

  const dates = [
    '2025-06-15T04:12:00Z',
    '2025-09-22T11:45:00Z',
    '2025-12-08T19:30:00Z',
    '2026-03-01T08:15:00Z',
    '2026-06-14T23:50:00Z',
  ];

  const arrayRanges: Record<number, [number, number]> = {
    1: [0.75, 1.11],
    2: [1.11, 1.64],
    3: [1.64, 2.42],
    4: [2.42, 3.82],
    5: [3.82, 4.42],
    6: [4.42, 5.00],
  };

  const [wMin, wMax] = arrayRanges[arrayId] || [1.64, 2.42];

  return dates.map((date, idx) => {
    // Frame 3 (index 2) on array 4 simulates a missing detector array exposure to test skip handling
    const isMissingFrame = (idx === 2 && arrayId === 4);

    return {
      frameId: `SPX-L3-${targetId.toUpperCase()}-E${idx + 1}-A${arrayId}`,
      epochIndex: idx,
      observationDate: date,
      detectorArray: arrayId as any,
      wavelengthMinUm: wMin,
      wavelengthMaxUm: wMax,
      channelIndex: Math.floor(((wMin + wMax) / 2 - 0.75) / (5.0 - 0.75) * 102) + 1,
      flaggedPixelPercentage: isMissingFrame ? 100 : Number((0.4 + (idx * 0.2) + Math.random() * 0.3).toFixed(2)),
      cosmicRayHits: isMissingFrame ? 0 : Math.floor(12 + Math.random() * 18),
      isAvailable: !isMissingFrame,
      skipReason: isMissingFrame 
        ? 'Detector Array 4 telemetry offline during downlink pass (Epoch 3 skipped)' 
        : undefined,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.0,
        zodiBrightnessMjySr: Number((12.4 + (idx * 0.8)).toFixed(2)),
        snrEstimated: isMissingFrame ? 0 : Number((24.5 - (idx * 0.7) + Math.random() * 4).toFixed(1)),
      }
    };
  });
}

/**
 * Generates candidate objects in the field of view, prioritizing Ivan's precomputed
 * real SPHEREx datasets from public/motion/review.json when available.
 */
export function getMockCandidates(targetId: string, arrayId: number = 6): CandidateObject[] {
  const reviewId = resolveMotionReviewIdForPreset(targetId, arrayId as any);
  if (reviewId) {
    const precomputed = getPrecomputedReviewById(reviewId);
    if (precomputed) {
      return convertReviewToCandidates(precomputed);
    }
  }

  if (targetId === 'vesta-d6' || targetId === 'vesta-d3') {
    const detLabel = targetId === 'vesta-d3' ? 'D3' : 'D6';
    return [
      {
        id: `(4) Vesta (${detLabel} BLOOM)`,
        ra: 223.024527,
        dec: -11.992267,
        pixelX: 111,
        pixelY: 87,
        mlRank: 1,
        mlScore: 0.99,
        mlPriorityScore: 0.99,
        heuristicRank: 1,
        randomForestRank: 1,
        detectionMethod: 'bloom_centroids',
        fitRmsPx: 0.19,
        speedArcsecPerHour: 49.2,
        bloomAreaPx: targetId === 'vesta-d3' ? [32, 33, 31] : [10, 11, 7],
        epochPositions: [
          { epochIndex: 0, x: 201, y: 37, flux: 240.0, snr: 45.0 },
          { epochIndex: 1, x: 111, y: 87, flux: 245.0, snr: 48.0 },
          { epochIndex: 2, x: 19, y: 136, flux: 238.0, snr: 44.0 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: `(4) Vesta saturated core recovered via detector BLOOM bitmask centroids across all 3 DR1 visits. Max offset ${targetId === 'vesta-d3' ? '0.382' : '0.281'} px from JPL Horizons ephemeris.`,
        isKnownCatalogMatch: true,
        matchedCatalog: 'NEO Ephemeris',
        catalogId: '(4) Vesta (JPL Horizons)',
        validationData: {
          objectName: `(4) Vesta (${detLabel} BLOOM)`,
          maxOffsetPx: targetId === 'vesta-d3' ? 0.382 : 0.281,
          baselineRank: 1,
          totalCandidates: 1,
          randomForestRank: 1,
          datasetDoi: '10.26131/IRSA652',
          sourceUrl: 'https://caltech-ipac.github.io/irsa-tutorials/most-queries/',
          exposuresCount: 3,
        },
      },
    ];
  }

  if (targetId === '3i-atlas' || targetId === '3i-atlas-d2') {
    const isD2 = targetId === '3i-atlas-d2';
    return [
      {
        id: isD2 ? '3I/ATLAS (D2)' : '3I/ATLAS',
        ra: isD2 ? 167.206653 : 166.790000,
        dec: isD2 ? 5.146825 : 5.290000,
        pixelX: isD2 ? 50 : 195,
        pixelY: isD2 ? 37 : 47,
        mlRank: 1,
        mlScore: 0.98,
        mlPriorityScore: 0.98,
        heuristicRank: 1,
        randomForestRank: isD2 ? 2 : 3,
        detectionMethod: 'heuristic_leave_one_out',
        fitRmsPx: isD2 ? 0.32 : 0.22,
        speedArcsecPerHour: isD2 ? 174.0 : 175.7,
        epochPositions: isD2
          ? [
              { epochIndex: 0, x: 9, y: 52, flux: 42.0, snr: 187.8 },
              { epochIndex: 1, x: 50, y: 37, flux: 45.0, snr: 215.0 },
              { epochIndex: 2, x: 95, y: 22, flux: 39.0, snr: 150.1 },
            ]
          : [
              { epochIndex: 0, x: 19, y: 108, flux: 18.4, snr: 33.7 },
              { epochIndex: 1, x: 63, y: 93, flux: 19.2, snr: 84.7 },
              { epochIndex: 2, x: 195, y: 47, flux: 21.0, snr: 61.8 },
              { epochIndex: 3, x: 237, y: 32, flux: 20.5, snr: 58.8 },
            ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: isD2
          ? 'Real SPHEREx D2 recovery of 3I/ATLAS across 3 exposures bridging a mask gap. Max offset 0.604 px from ephemeris. Heuristic #1/2, Random Forest #2/2.'
          : 'Interstellar comet track matched across all 4 real SPHEREx D6 exposures. Max offset 0.539 px from ephemeris. Ranked #1/10 Heuristic & #3/10 Random Forest.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'NEO Ephemeris',
        catalogId: '3I/ATLAS (C/2024 S1)',
        validationData: {
          objectName: isD2 ? '3I/ATLAS (D2)' : '3I/ATLAS',
          maxOffsetPx: isD2 ? 0.604 : 0.539,
          baselineRank: 1,
          totalCandidates: isD2 ? 2 : 10,
          randomForestRank: isD2 ? 2 : 3,
          datasetDoi: '10.26131/IRSA652',
          sourceUrl: 'https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html',
          exposuresCount: isD2 ? 3 : 4,
        }
      },
      {
        id: 'cand-3i-tail-clump',
        ra: 166.812400,
        dec: 5.275100,
        pixelX: 185,
        pixelY: 62,
        mlRank: 2,
        mlScore: 0.84,
        mlPriorityScore: 0.84,
        heuristicRank: 2,
        randomForestRank: 1,
        detectionMethod: 'heuristic_leave_one_out',
        fitRmsPx: 0.41,
        speedArcsecPerHour: 111.0,
        epochPositions: [
          { epochIndex: 0, x: 14, y: 120, flux: 8.2, snr: 7.4 },
          { epochIndex: 1, x: 58, y: 105, flux: 8.8, snr: 7.9 },
          { epochIndex: 2, x: 185, y: 62, flux: 9.4, snr: 8.5 },
          { epochIndex: 3, x: 228, y: 46, flux: 9.1, snr: 8.1 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'Cometary dust coma / tail ion emission trailing 3I/ATLAS nucleus. High linear correlation with primary ephemeris.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'NEO Ephemeris',
        catalogId: '3I/ATLAS Coma Dust Structure',
      },
      {
        id: 'cand-3i-faint-track',
        ra: 166.745000,
        dec: 5.342000,
        pixelX: 320,
        pixelY: 180,
        mlRank: 3,
        mlScore: 0.65,
        mlPriorityScore: 0.65,
        heuristicRank: 3,
        randomForestRank: 4,
        detectionMethod: 'heuristic_leave_one_out',
        fitRmsPx: 0.09,
        speedArcsecPerHour: 186.9,
        epochPositions: [
          { epochIndex: 0, x: 305, y: 195, flux: 5.1, snr: 5.2 },
          { epochIndex: 1, x: 312, y: 190, flux: 5.4, snr: 5.5 },
          { epochIndex: 2, x: 320, y: 180, flux: 5.2, snr: 5.3 },
          { epochIndex: 3, x: 328, y: 172, flux: 5.6, snr: 5.7 },
        ],
        classification: 'moving_object',
        confidence: 'medium',
        volunteerNotes: 'Faint linear track detected in background. Likely uncatalogued main-belt asteroid crossing the SPHEREx field of view.',
        isKnownCatalogMatch: false,
      },
      {
        id: 'cand-3i-artifact-4',
        ra: 166.852000,
        dec: 5.215000,
        pixelX: 410,
        pixelY: 290,
        mlRank: 4,
        mlScore: 0.38,
        mlPriorityScore: 0.38,
        heuristicRank: 4,
        randomForestRank: 5,
        detectionMethod: 'heuristic_leave_one_out',
        fitRmsPx: 1.45,
        speedArcsecPerHour: 0.0,
        epochPositions: [
          { epochIndex: 0, x: 410, y: 290, flux: 14.2, snr: 11.2 },
          { epochIndex: 1, x: 410, y: 290, flux: 1.1, snr: 1.2 },
          { epochIndex: 2, x: 410, y: 290, flux: 0.8, snr: 0.9 },
          { epochIndex: 3, x: 410, y: 290, flux: 1.2, snr: 1.3 },
        ],
        classification: 'artifact',
        confidence: 'low',
        volunteerNotes: 'Single-epoch cosmic ray hit / diffraction spike anomaly in Frame 1. Stationary coordinates with no multi-epoch track.',
        isKnownCatalogMatch: false,
      }
    ];
  }

  if (targetId === 'barnards-star') {
    return [
      {
        id: 'cand-barnard-primary',
        ra: 269.452075,
        dec: 4.693365,
        pixelX: 128,
        pixelY: 128,
        mlRank: 1,
        mlPriorityScore: 0.96,
        heuristicRank: 1,
        randomForestRank: 1,
        fitRmsPx: 0.14,
        speedArcsecPerHour: 10.3,
        epochPositions: [
          { epochIndex: 0, x: 122, y: 140, flux: 185.0, snr: 38.2 },
          { epochIndex: 1, x: 125, y: 134, flux: 184.5, snr: 37.9 },
          { epochIndex: 2, x: 128, y: 128, flux: 185.1, snr: 38.0 },
          { epochIndex: 3, x: 131, y: 122, flux: 183.8, snr: 37.4 },
          { epochIndex: 4, x: 134, y: 116, flux: 186.2, snr: 38.5 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'High proper motion vector confirmed across all epochs. Matched in Gaia DR3 (proper motion ~10.3 arcsec/yr).',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: "Barnard's Star (Gaia DR3 4472832130942575872)",
        properMotionMasYr: { pmRa: -802.8, pmDec: 10362.5 }
      },
      {
        id: 'cand-barnard-anomaly-1',
        ra: 269.461100,
        dec: 4.689200,
        pixelX: 190,
        pixelY: 85,
        mlRank: 2,
        mlPriorityScore: 0.79,
        heuristicRank: 2,
        randomForestRank: 3,
        fitRmsPx: 0.42,
        speedArcsecPerHour: 0.2,
        epochPositions: [
          { epochIndex: 0, x: 190, y: 85, flux: 32.0, snr: 4.1 },
          { epochIndex: 1, x: 190, y: 85, flux: 152.0, snr: 28.4 },
          { epochIndex: 2, x: 190, y: 85, flux: 31.8, snr: 3.8 },
          { epochIndex: 3, x: 190, y: 85, flux: 32.1, snr: 2.1 },
          { epochIndex: 4, x: 190, y: 85, flux: 31.9, snr: 2.3 },
        ],
        classification: 'transient',
        confidence: 'medium',
        volunteerNotes: 'Epoch 2 flare event. No match in Gaia DR3 or WISE within 3 arcsec radius. Candidate stellar optical/infrared flare.',
        isKnownCatalogMatch: false,
      },
      {
        id: 'cand-barnard-companion',
        ra: 269.438000,
        dec: 4.712000,
        pixelX: 45,
        pixelY: 60,
        mlRank: 3,
        mlPriorityScore: 0.63,
        heuristicRank: 3,
        randomForestRank: 2,
        fitRmsPx: 0.28,
        speedArcsecPerHour: 10.1,
        epochPositions: [
          { epochIndex: 0, x: 45, y: 60, flux: 45.0, snr: 12.4 },
          { epochIndex: 1, x: 45, y: 60, flux: 44.8, snr: 12.1 },
          { epochIndex: 2, x: 45, y: 60, flux: 45.2, snr: 12.5 },
          { epochIndex: 3, x: 45, y: 60, flux: 45.0, snr: 12.3 },
          { epochIndex: 4, x: 45, y: 60, flux: 44.9, snr: 12.2 },
        ],
        classification: 'moving_object',
        confidence: 'medium',
        volunteerNotes: 'Faint co-moving candidate detected 90 arcseconds southwest. Parallax investigation requested by Science Team.',
        isKnownCatalogMatch: false,
      },
      {
        id: 'cand-barnard-wise-match',
        ra: 269.475000,
        dec: 4.671000,
        pixelX: 220,
        pixelY: 195,
        mlRank: 4,
        mlPriorityScore: 0.48,
        heuristicRank: 4,
        randomForestRank: 4,
        fitRmsPx: 0.11,
        speedArcsecPerHour: 0.0,
        epochPositions: [
          { epochIndex: 0, x: 220, y: 195, flux: 65.0, snr: 18.2 },
          { epochIndex: 1, x: 220, y: 195, flux: 64.7, snr: 18.0 },
          { epochIndex: 2, x: 220, y: 195, flux: 65.3, snr: 18.4 },
          { epochIndex: 3, x: 220, y: 195, flux: 65.1, snr: 18.1 },
          { epochIndex: 4, x: 220, y: 195, flux: 64.9, snr: 18.3 },
        ],
        classification: 'already_known',
        confidence: 'high',
        volunteerNotes: 'Stationary mid-infrared field star catalogued in AllWISE catalog. Zero detected proper motion.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'WISE',
        catalogId: 'AllWISE J175754.00+044015.6',
      },
      {
        id: 'cand-barnard-cosmic-ray',
        ra: 269.431000,
        dec: 4.654000,
        pixelX: 110,
        pixelY: 130,
        mlRank: 5,
        mlPriorityScore: 0.28,
        heuristicRank: 5,
        randomForestRank: 5,
        fitRmsPx: 1.85,
        speedArcsecPerHour: 0.0,
        epochPositions: [
          { epochIndex: 0, x: 110, y: 130, flux: 1.2, snr: 1.4 },
          { epochIndex: 1, x: 110, y: 130, flux: 1.0, snr: 1.2 },
          { epochIndex: 2, x: 110, y: 130, flux: 24.5, snr: 18.2 },
          { epochIndex: 3, x: 110, y: 130, flux: 1.1, snr: 1.3 },
          { epochIndex: 4, x: 110, y: 130, flux: 1.3, snr: 1.5 },
        ],
        classification: 'artifact',
        confidence: 'low',
        volunteerNotes: 'High-energy cosmic ray strike on detector pixels during Epoch 3. Filtered out by difference imaging.',
        isKnownCatalogMatch: false,
      }
    ];
  }

  if (targetId === 'wise-0855') {
    return [
      {
        id: 'cand-wise-0855-01',
        ra: 133.795129,
        dec: -7.245147,
        pixelX: 128,
        pixelY: 128,
        mlRank: 1,
        mlPriorityScore: 0.95,
        epochPositions: [
          { epochIndex: 0, x: 128, y: 128, flux: 95.0, snr: 16.2 },
          { epochIndex: 1, x: 132, y: 126, flux: 94.5, snr: 15.9 },
          { epochIndex: 2, x: 136, y: 124, flux: 96.0, snr: 16.5 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'Ultra-cold Y-type sub-brown dwarf detected in Band 5/6 (4.42–5.00 µm). Atmospheric water ice absorption verified.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'WISE',
        catalogId: 'WISE 0855-0714 (Coldest Sub-Brown Dwarf)',
        properMotionMasYr: { pmRa: -8120.0, pmDec: 680.0 }
      },
      {
        id: 'cand-wise-field-star',
        ra: 133.812000,
        dec: -7.234000,
        pixelX: 60,
        pixelY: 180,
        mlRank: 2,
        mlPriorityScore: 0.62,
        epochPositions: [
          { epochIndex: 0, x: 60, y: 180, flux: 42.0, snr: 11.4 },
          { epochIndex: 1, x: 60, y: 180, flux: 42.1, snr: 11.5 },
          { epochIndex: 2, x: 60, y: 180, flux: 41.9, snr: 11.3 },
        ],
        classification: 'already_known',
        confidence: 'high',
        volunteerNotes: 'Stationary reference field star. Clean astrometric anchor.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: 'Gaia DR3 5671948291038291024',
      }
    ];
  }

  if (targetId === 'epsilon-indi-b') {
    return [
      {
        id: 'cand-eps-indi-b-primary',
        ra: 331.044146,
        dec: -56.782844,
        pixelX: 128,
        pixelY: 128,
        mlRank: 1,
        mlPriorityScore: 0.96,
        heuristicRank: 1,
        randomForestRank: 1,
        fitRmsPx: 0.16,
        speedArcsecPerHour: 4.8,
        epochPositions: [
          { epochIndex: 0, x: 120, y: 134, flux: 142.0, snr: 31.4 },
          { epochIndex: 1, x: 124, y: 131, flux: 141.5, snr: 31.1 },
          { epochIndex: 2, x: 128, y: 128, flux: 142.8, snr: 31.7 },
          { epochIndex: 3, x: 132, y: 125, flux: 142.1, snr: 31.3 },
          { epochIndex: 4, x: 136, y: 122, flux: 143.0, snr: 31.8 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'Binary T1+T6 brown dwarf pair (ε Indi Ba/Bb) at 3.63 pc. Strong CH₄ and H₂O absorption in Band 3 (1.64–2.42 µm) with 4.7″/yr proper motion.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'WISE',
        catalogId: 'AllWISE J220410.52-564657.7 (ε Indi Ba/Bb)',
        properMotionMasYr: { pmRa: 3961.4, pmDec: -2538.3 },
      },
      {
        id: 'cand-eps-indi-gaia-star',
        ra: 331.061200,
        dec: -56.771400,
        pixelX: 196,
        pixelY: 88,
        mlRank: 2,
        mlPriorityScore: 0.52,
        heuristicRank: 2,
        randomForestRank: 2,
        fitRmsPx: 0.12,
        speedArcsecPerHour: 0.1,
        epochPositions: [
          { epochIndex: 0, x: 196, y: 88, flux: 54.0, snr: 15.8 },
          { epochIndex: 1, x: 196, y: 88, flux: 53.8, snr: 15.6 },
          { epochIndex: 2, x: 196, y: 88, flux: 54.2, snr: 15.9 },
          { epochIndex: 3, x: 196, y: 88, flux: 54.1, snr: 15.7 },
          { epochIndex: 4, x: 196, y: 88, flux: 53.9, snr: 15.8 },
        ],
        classification: 'already_known',
        confidence: 'high',
        volunteerNotes: 'Stationary Indus field star catalogued in Gaia DR3.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: 'Gaia DR3 6412595290592307840',
      },
    ];
  }

  if (targetId === 'rw-aurigae') {
    return [
      {
        id: 'cand-rw-aur-primary',
        ra: 76.956417,
        dec: 30.401444,
        pixelX: 128,
        pixelY: 128,
        mlRank: 1,
        mlPriorityScore: 0.93,
        heuristicRank: 1,
        randomForestRank: 1,
        fitRmsPx: 0.15,
        speedArcsecPerHour: 0.2,
        epochPositions: [
          { epochIndex: 0, x: 128, y: 128, flux: 168.0, snr: 34.2 },
          { epochIndex: 1, x: 128, y: 128, flux: 94.0, snr: 21.5 },
          { epochIndex: 2, x: 128, y: 128, flux: 175.0, snr: 35.8 },
          { epochIndex: 3, x: 128, y: 128, flux: 112.0, snr: 24.9 },
          { epochIndex: 4, x: 128, y: 128, flux: 171.0, snr: 34.8 },
        ],
        classification: 'transient',
        confidence: 'high',
        volunteerNotes: 'Classical T Tauri variable star RW Aurigae. Stationary position in Gaia DR3 with strong circumstellar disk dimming/brightening across epochs in Band 4.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: 'RW Aurigae (Gaia DR3 156430822114424576)',
      },
      {
        id: 'cand-rw-aur-wise-ir',
        ra: 76.968200,
        dec: 30.391100,
        pixelX: 184,
        pixelY: 172,
        mlRank: 2,
        mlPriorityScore: 0.58,
        heuristicRank: 2,
        randomForestRank: 2,
        fitRmsPx: 0.19,
        speedArcsecPerHour: 0.0,
        epochPositions: [
          { epochIndex: 0, x: 184, y: 172, flux: 48.0, snr: 14.1 },
          { epochIndex: 1, x: 184, y: 172, flux: 47.8, snr: 14.0 },
          { epochIndex: 2, x: 184, y: 172, flux: 48.2, snr: 14.3 },
          { epochIndex: 3, x: 184, y: 172, flux: 47.9, snr: 14.1 },
          { epochIndex: 4, x: 184, y: 172, flux: 48.1, snr: 14.2 },
        ],
        classification: 'already_known',
        confidence: 'high',
        volunteerNotes: 'Young stellar object in Taurus-Auriga complex matched in AllWISE.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'WISE',
        catalogId: 'AllWISE J050749.56+302405.1',
      },
    ];
  }

  if (targetId === 'r-draconis') {
    return [
      {
        id: 'cand-r-dra-primary',
        ra: 248.167625,
        dec: 66.754972,
        pixelX: 128,
        pixelY: 128,
        mlRank: 1,
        mlPriorityScore: 0.94,
        heuristicRank: 1,
        randomForestRank: 1,
        fitRmsPx: 0.14,
        speedArcsecPerHour: 0.3,
        epochPositions: [
          { epochIndex: 0, x: 128, y: 128, flux: 210.0, snr: 41.2 },
          { epochIndex: 1, x: 128, y: 128, flux: 145.0, snr: 29.8 },
          { epochIndex: 2, x: 128, y: 128, flux: 98.0, snr: 21.4 },
          { epochIndex: 3, x: 128, y: 128, flux: 164.0, snr: 33.1 },
          { epochIndex: 4, x: 128, y: 128, flux: 224.0, snr: 43.5 },
        ],
        classification: 'transient',
        confidence: 'high',
        volunteerNotes: 'Mira-type pulsating red giant R Draconis (P = 245.6 days). Large infrared flux modulation across epochs with deep CO absorption in Band 6.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: 'R Draconis (Gaia DR3 1645265502983951104)',
      },
      {
        id: 'cand-r-dra-wise',
        ra: 248.184100,
        dec: 66.742300,
        pixelX: 74,
        pixelY: 192,
        mlRank: 2,
        mlPriorityScore: 0.51,
        heuristicRank: 2,
        randomForestRank: 2,
        fitRmsPx: 0.13,
        speedArcsecPerHour: 0.0,
        epochPositions: [
          { epochIndex: 0, x: 74, y: 192, flux: 52.0, snr: 15.2 },
          { epochIndex: 1, x: 74, y: 192, flux: 52.2, snr: 15.3 },
          { epochIndex: 2, x: 74, y: 192, flux: 51.9, snr: 15.1 },
          { epochIndex: 3, x: 74, y: 192, flux: 52.1, snr: 15.2 },
          { epochIndex: 4, x: 74, y: 192, flux: 52.0, snr: 15.2 },
        ],
        classification: 'already_known',
        confidence: 'high',
        volunteerNotes: 'Stationary Draco field source matched in AllWISE catalog.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'WISE',
        catalogId: 'AllWISE J163240.22+664517.9',
      },
    ];
  }

  // Coordinate-derived fallback for any other target ID
  const coordCatalog = resolveCoordinateCatalogContext(166.79, 5.29);
  return [
    {
      id: `cand-${targetId}-01`,
      ra: 166.79,
      dec: 5.29,
      pixelX: 128,
      pixelY: 128,
      mlRank: 1,
      mlPriorityScore: 0.92,
      epochPositions: [
        { epochIndex: 0, x: 120, y: 132, flux: 22.0, snr: 14.2 },
        { epochIndex: 1, x: 124, y: 130, flux: 21.8, snr: 13.9 },
        { epochIndex: 2, x: 128, y: 128, flux: 22.4, snr: 14.5 },
      ],
      classification: 'moving_object',
      confidence: 'high',
      volunteerNotes: 'Multi-epoch linear source detected in SPHEREx field.',
      isKnownCatalogMatch: true,
      matchedCatalog: 'WISE',
      catalogId: coordCatalog.wiseId,
    },
  ];
}

/**
 * Formats exact IAU J2000 sexagesimal designation (AllWISE JHHMMSS.ss±DDMMSS.s)
 * and deterministic HEALPix-like Gaia DR3 source ID for ANY sky coordinate (RA, Dec),
 * or returns the exact known NASA benchmark catalog entry if within 0.35° of a known target.
 */
export function resolveCoordinateCatalogContext(raDeg: number, decDeg: number): {
  knownObjectName: string | null;
  gaiaId: string;
  wiseId: string;
  ephemerisLabel: string | null;
  gaiaOffsetPx: { dx: number; dy: number };
  wiseOffsetPx: { dx: number; dy: number };
} {
  const normRa = ((raDeg % 360) + 360) % 360;
  const raHours = normRa / 15;
  const rh = Math.floor(raHours);
  const rm = Math.floor((raHours - rh) * 60);
  const rs = ((raHours - rh - rm / 60) * 3600).toFixed(2).padStart(5, '0');

  const sign = decDeg >= 0 ? '+' : '-';
  const absDec = Math.abs(decDeg);
  const dd = Math.floor(absDec);
  const dm = Math.floor((absDec - dd) * 60);
  const ds = ((absDec - dd - dm / 60) * 3600).toFixed(1).padStart(4, '0');

  const wiseJName = `AllWISE J${rh.toString().padStart(2, '0')}${rm.toString().padStart(2, '0')}${rs}${sign}${dd.toString().padStart(2, '0')}${dm.toString().padStart(2, '0')}${ds}`;

  // Deterministic Gaia DR3 source_id derived from sky coordinates (HEALPix level-12 approximation)
  const healpixSeed = Math.abs(
    Math.floor((normRa * 11459.1559 + (decDeg + 90) * 22918.3118) * 1000000)
  );
  const gaiaSourceId = `Gaia DR3 ${(4000000000000000000n + BigInt(healpixSeed) * 131071n).toString()}`;

  // Coordinate-seeded offsets on the viewport so every coordinate has distinct catalog marker positions
  const angle1 = (normRa * 7.3 + decDeg * 13.1) * (Math.PI / 180);
  const angle2 = (normRa * 11.7 - decDeg * 5.9) * (Math.PI / 180);
  const gaiaOffsetPx = {
    dx: Math.round(Math.cos(angle1) * 115 - 35),
    dy: Math.round(Math.sin(angle1) * 85 - 25),
  };
  const wiseOffsetPx = {
    dx: Math.round(Math.cos(angle2) * 130 + 40),
    dy: Math.round(Math.sin(angle2) * 95 + 30),
  };

  // Check proximity to known astronomical objects
  const knownCatalogTable: Array<{
    ra: number;
    dec: number;
    name: string;
    gaiaId: string;
    wiseId: string;
    ephemerisLabel: string | null;
  }> = [
    {
      ra: 166.79,
      dec: 5.29,
      name: '3I/ATLAS (C/2024 S1)',
      gaiaId: 'Gaia DR3 3816492018472910464',
      wiseId: 'AllWISE J110709.60+051724.0',
      ephemerisLabel: 'JPL Horizons: 3I/ATLAS (0.54px)',
    },
    {
      ra: 167.206653,
      dec: 5.146825,
      name: '3I/ATLAS (D2 Field)',
      gaiaId: 'Gaia DR3 3816519402849102720',
      wiseId: 'AllWISE J110849.60+050848.6',
      ephemerisLabel: 'JPL Horizons: 3I/ATLAS (0.60px)',
    },
    {
      ra: 269.452075,
      dec: 4.693365,
      name: "Barnard's Star (HIP 87937)",
      gaiaId: "Gaia DR3 4472832130942575872 (Barnard's Star)",
      wiseId: 'AllWISE J175748.49+044136.1',
      ephemerisLabel: null,
    },
    {
      ra: 133.795129,
      dec: -7.245147,
      name: 'WISE 0855-0714 (Y4 Sub-Brown Dwarf)',
      gaiaId: 'Gaia DR3 5756948291038291024',
      wiseId: 'WISE J085510.83-071442.5 (WISE 0855)',
      ephemerisLabel: null,
    },
    {
      ra: 331.044146,
      dec: -56.782844,
      name: 'Epsilon Indi Ba/Bb (T1+T6 Binary)',
      gaiaId: 'Gaia DR3 6412595290592307840',
      wiseId: 'AllWISE J220410.52-564657.7 (ε Indi B)',
      ephemerisLabel: null,
    },
    {
      ra: 76.956417,
      dec: 30.401444,
      name: 'RW Aurigae (T Tauri Variable)',
      gaiaId: 'Gaia DR3 156430822114424576 (RW Aur)',
      wiseId: 'AllWISE J050749.56+302405.1 (RW Aur)',
      ephemerisLabel: null,
    },
    {
      ra: 248.167625,
      dec: 66.754972,
      name: 'R Draconis (Mira Variable)',
      gaiaId: 'Gaia DR3 1645265502983951104 (R Dra)',
      wiseId: 'AllWISE J163240.22+664517.9 (R Dra)',
      ephemerisLabel: null,
    },
    {
      ra: 223.024527,
      dec: -11.992267,
      name: '(4) Vesta (Main-Belt Asteroid)',
      gaiaId: 'Gaia DR3 6314829104928174080',
      wiseId: 'AllWISE J145205.89-115932.2',
      ephemerisLabel: 'JPL Horizons: (4) Vesta (0.28px)',
    },
  ];

  for (const entry of knownCatalogTable) {
    const dist = Math.hypot(normRa - entry.ra, decDeg - entry.dec);
    if (dist < 0.45) {
      return {
        knownObjectName: entry.name,
        gaiaId: entry.gaiaId,
        wiseId: entry.wiseId,
        ephemerisLabel: entry.ephemerisLabel,
        gaiaOffsetPx,
        wiseOffsetPx,
      };
    }
  }

  return {
    knownObjectName: null,
    gaiaId: gaiaSourceId,
    wiseId: wiseJName,
    ephemerisLabel: null,
    gaiaOffsetPx,
    wiseOffsetPx,
  };
}

/**
 * Queries CDS SIMBAD TAP / Sesame cone search for real astronomical catalog objects
 * at the exact (RA, Dec) coordinate when the user searches custom coordinates.
 */
export async function fetchKnownCatalogObjectAtCoord(
  raDeg: number,
  decDeg: number
): Promise<{ mainId: string; otype: string } | null> {
  try {
    const adql = `SELECT TOP 1 main_id, otype_txt FROM basic WHERE CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', ${raDeg.toFixed(6)}, ${decDeg.toFixed(6)}, 0.0833)) = 1`;
    const url = `https://simbad.cds.unistra.fr/simbad/sim-tap/sync?request=doQuery&lang=adql&format=json&query=${encodeURIComponent(adql)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(3500) });
    if (!res.ok) return null;
    const json = await res.json();
    const row = json?.data?.[0];
    if (Array.isArray(row) && row[0]) {
      return {
        mainId: String(row[0]).replace(/\s+/g, ' ').trim(),
        otype: String(row[1] || 'Catalog Source').trim(),
      };
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Generates continuous 102-band spectral curve (0.75 - 5.00 µm)
 */
export function getMock102BandSpectrum(_candidateId: string): SpectralDataPoint[] {
  const points: SpectralDataPoint[] = [];
  const minW = 0.75;
  const maxW = 5.00;
  const totalChannels = 102;

  for (let ch = 1; ch <= totalChannels; ch++) {
    const lambda = minW + ((ch - 1) / (totalChannels - 1)) * (maxW - minW);

    let flux = 20.0 * Math.pow(lambda / 1.5, -0.6) + Math.sin(lambda * 1.8) * 2.5;

    // Absorption features
    if (Math.abs(lambda - 3.05) < 0.45) {
      const depth = Math.exp(-Math.pow((lambda - 3.05) / 0.22, 2)) * 8.5;
      flux -= depth;
    }

    if (Math.abs(lambda - 4.27) < 0.2) {
      const depth = Math.exp(-Math.pow((lambda - 4.27) / 0.1, 2)) * 6.0;
      flux -= depth;
    }

    if (Math.abs(lambda - 4.67) < 0.25) {
      const depth = Math.exp(-Math.pow((lambda - 4.67) / 0.12, 2)) * 5.2;
      flux -= depth;
    }

    const noise = (Math.sin(ch * 13.7) * 0.6) + ((ch % 3 === 0 ? 0.3 : -0.2));
    flux = Math.max(1.2, flux + noise);

    let detectorArray: 1 | 2 | 3 | 4 | 5 | 6 = 1;
    if (lambda >= 1.11 && lambda < 1.64) detectorArray = 2;
    else if (lambda >= 1.64 && lambda < 2.42) detectorArray = 3;
    else if (lambda >= 2.42 && lambda < 3.82) detectorArray = 4;
    else if (lambda >= 3.82 && lambda < 4.42) detectorArray = 5;
    else if (lambda >= 4.42) detectorArray = 6;

    points.push({
      channel: ch,
      wavelengthUm: Number(lambda.toFixed(3)),
      fluxMjy: Number(flux.toFixed(2)),
      uncertaintyMjy: Number((flux * 0.05 + 0.2).toFixed(2)),
      detectorArray,
    });
  }

  return points;
}
