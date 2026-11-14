/**
 * SPHEREx Sky-Viewer Core Types & Data Contracts
 * Designed for NASA Space Apps Challenge SPHEREx mission data inspection
 */

export type DetectorArrayId = 1 | 2 | 3 | 4 | 5 | 6;

export type SubtractionMode = 
  | 'raw_calibrated' 
  | 'zodi_reference_subtracted' 
  | 'epoch_difference';

export type CandidateClassification = 
  | 'moving_object' 
  | 'transient' 
  | 'already_known' 
  | 'artifact' 
  | 'unreviewed';

export type ConfidenceLevel = 'low' | 'medium' | 'high';

export type FOVOption = "1'" | "3'" | "5'" | "10'";

export interface TargetPreset {
  id: string;
  name: string;
  subtitle: string;
  raHms: string;
  decDms: string;
  raDeg: number;
  decDeg: number;
  description: string;
  recommendedArray: DetectorArrayId;
  expectedClass: CandidateClassification;
}

export interface SpherexEpochFrame {
  frameId: string;
  epochIndex: number;
  observationDate: string; // ISO or YYYY-MM-DD
  detectorArray: DetectorArrayId;
  wavelengthMinUm: number;
  wavelengthMaxUm: number;
  channelIndex?: number; // 1 to 102
  flaggedPixelPercentage: number;
  cosmicRayHits: number;
  isAvailable: boolean;
  skipReason?: string; // Reason if isAvailable is false
  imageDataUrl?: string; // Rendered cutout bitmap or SVG simulation
  headerMetadata: {
    exposureTimeSec: number;
    airmass: number;
    zodiBrightnessMjySr: number;
    snrEstimated: number;
  };
}

export interface CandidateObject {
  id: string;
  ra: number;
  dec: number;
  pixelX: number;
  pixelY: number;
  epochPositions: {
    epochIndex: number;
    x: number;
    y: number;
    flux: number;
    snr: number;
  }[];
  classification: CandidateClassification;
  confidence: ConfidenceLevel;
  volunteerNotes: string;
  flaggedBy?: string;
  isKnownCatalogMatch?: boolean;
  matchedCatalog?: 'Gaia DR3' | 'WISE' | 'NEO Ephemeris' | null;
  catalogId?: string;
  properMotionMasYr?: { pmRa: number; pmDec: number };
  validationData?: {
    objectName: string;
    maxOffsetPx: number;
    baselineRank: number;
    totalCandidates: number;
    randomForestRank: number;
    datasetDoi: string;
    sourceUrl: string;
    exposuresCount: number;
  };
}

export interface SpectralDataPoint {
  channel: number; // 1-102
  wavelengthUm: number;
  fluxMjy: number;
  uncertaintyMjy: number;
  detectorArray: DetectorArrayId;
}

export interface MolecularLine {
  name: string;
  formula: string;
  centerUm: number;
  widthUm: number;
  color: string;
}

export interface CatalogOverlayState {
  gaiaDr3: boolean;
  wise: boolean;
  solarSystemEphemeris: boolean;
}

export interface ViewerState {
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  selectedChannel: number | null; // 1-102 or null for grouped
  subtractionMode: SubtractionMode;
  overlays: CatalogOverlayState;
  activeFrameIndex: number;
  isPlaying: boolean;
  fps: number;
  blinkMode: boolean;
  selectedCandidateId: string | null;
  zoomLevel: number;
  panOffset: { x: number; y: number };
  simulateNetworkLatency: boolean;
}
