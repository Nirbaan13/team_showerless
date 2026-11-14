import type {
  TargetPreset,
  SpherexEpochFrame,
  CandidateObject,
  SpectralDataPoint,
  MolecularLine,
} from '../types/spherex';

export const NASA_TEST_PRESETS: TargetPreset[] = [
  {
    id: '3i-atlas',
    name: '3I/ATLAS',
    subtitle: 'Interstellar Comet (Real SPHEREx Detection)',
    raHms: '11h 07m 09.6s',
    decDms: '+05° 17\' 24.0"',
    raDeg: 166.790000,
    decDeg: 5.290000,
    description: 'Real NASA/IPAC IRSA QR2 detection across 4 exposures. Offset within 0.54 px of ephemeris. Ranked #1/25 baseline & #2/25 Random Forest.',
    recommendedArray: 6,
    expectedClass: 'moving_object',
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
 * Generates simulated multi-epoch frames for the celestial viewport.
 */
export function getMockEpochFrames(targetId: string, arrayId: number): SpherexEpochFrame[] {
  // Real SPHEREx Interim Results: 3I/ATLAS (NASA/IPAC IRSA Quick Release 2)
  if (targetId === '3i-atlas') {
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
      detectorArray: 6 as any,
      wavelengthMinUm: 4.42,
      wavelengthMaxUm: 5.00,
      channelIndex: 94 + idx * 2,
      flaggedPixelPercentage: 0.12,
      cosmicRayHits: 8,
      isAvailable: true,
      headerMetadata: {
        exposureTimeSec: 142.5,
        airmass: 1.0,
        zodiBrightnessMjySr: 12.43,
        snrEstimated: obs.snr,
      }
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
 * Generates mock candidate objects in the field of view.
 */
export function getMockCandidates(targetId: string): CandidateObject[] {
  if (targetId === '3i-atlas') {
    return [
      {
        id: '3I/ATLAS',
        ra: 166.790000,
        dec: 5.290000,
        pixelX: 195,
        pixelY: 47,
        epochPositions: [
          { epochIndex: 0, x: 19, y: 108, flux: 18.4, snr: 12.1 },
          { epochIndex: 1, x: 63, y: 93, flux: 19.2, snr: 13.4 },
          { epochIndex: 2, x: 195, y: 47, flux: 21.0, snr: 14.8 },
          { epochIndex: 3, x: 237, y: 32, flux: 20.5, snr: 14.2 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'Interstellar comet track matched across all 4 real SPHEREx exposures. Max offset 0.539 px from ephemeris. Ranked #1/25 baseline & #2/25 Random Forest.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'NEO Ephemeris',
        catalogId: '3I/ATLAS (C/2024 S1)',
        validationData: {
          objectName: '3I/ATLAS',
          maxOffsetPx: 0.539,
          baselineRank: 1,
          totalCandidates: 25,
          randomForestRank: 2,
          datasetDoi: '10.26131/IRSA652',
          sourceUrl: 'https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html',
          exposuresCount: 4,
        }
      }
    ];
  }

  if (targetId === 'barnards-star') {
    return [
      {
        id: 'cand-barnard-primary',
        ra: 269.452075,
        dec: 4.693365,
        pixelX: 250,
        pixelY: 250,
        epochPositions: [
          { epochIndex: 0, x: 235, y: 240, flux: 142.0, snr: 38.2 },
          { epochIndex: 1, x: 242, y: 245, flux: 141.5, snr: 37.9 },
          { epochIndex: 2, x: 250, y: 250, flux: 143.1, snr: 38.0 },
          { epochIndex: 3, x: 258, y: 255, flux: 140.8, snr: 37.4 },
          { epochIndex: 4, x: 265, y: 260, flux: 142.9, snr: 38.5 },
        ],
        classification: 'moving_object',
        confidence: 'high',
        volunteerNotes: 'Clear high proper motion vector confirmed across all epochs. Consistent with Gaia DR3 cross-match.',
        isKnownCatalogMatch: true,
        matchedCatalog: 'Gaia DR3',
        catalogId: 'Gaia DR3 4472832130942575872',
        properMotionMasYr: { pmRa: -802.8, pmDec: 10362.5 }
      },
      {
        id: 'cand-barnard-anomaly-1',
        ra: 269.461100,
        dec: 4.689200,
        pixelX: 380,
        pixelY: 170,
        epochPositions: [
          { epochIndex: 0, x: 380, y: 170, flux: 3.2, snr: 4.1 },
          { epochIndex: 1, x: 380, y: 170, flux: 14.8, snr: 12.4 },
          { epochIndex: 2, x: 380, y: 170, flux: 2.9, snr: 3.8 },
          { epochIndex: 3, x: 380, y: 170, flux: 1.8, snr: 2.1 },
          { epochIndex: 4, x: 380, y: 170, flux: 2.0, snr: 2.3 },
        ],
        classification: 'transient',
        confidence: 'medium',
        volunteerNotes: 'Epoch 2 flare event. No match in Gaia DR3 or WISE within 3 arcsec radius. Candidate optical/IR flare.',
        isKnownCatalogMatch: false,
      }
    ];
  }

  // Default mock candidate set for any other preset
  return [
    {
      id: `cand-${targetId}-01`,
      ra: 133.795,
      dec: -7.245,
      pixelX: 256,
      pixelY: 256,
      epochPositions: [
        { epochIndex: 0, x: 248, y: 252, flux: 22.0, snr: 14.2 },
        { epochIndex: 1, x: 252, y: 254, flux: 21.8, snr: 13.9 },
        { epochIndex: 2, x: 256, y: 256, flux: 22.4, snr: 14.5 },
        { epochIndex: 3, x: 260, y: 258, flux: 21.9, snr: 14.1 },
        { epochIndex: 4, x: 264, y: 260, flux: 22.7, snr: 14.6 },
      ],
      classification: 'unreviewed',
      confidence: 'medium',
      volunteerNotes: 'Infrared excess observed in 3.8-5.0 um channels. Awaiting volunteer triage.',
      isKnownCatalogMatch: true,
      matchedCatalog: 'WISE',
      catalogId: 'WISE J085510.83-071442.5'
    }
  ];
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
