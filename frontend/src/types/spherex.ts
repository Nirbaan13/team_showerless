/**
 * SPHEREx Sky-Viewer Core Types & Data Contracts
 * Designed for NASA Space Apps Challenge SPHEREx mission data inspection
 */

export type DetectorArrayId = 1 | 2 | 3 | 4 | 5 | 6;

export type SubtractionMode = 
  | 'raw_calibrated' 
  | 'zodi_reference_subtracted' 
  | 'epoch_difference'
  | 'bloom_mask';

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
  motionReviewId?: string;
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
  imageDataUrl?: string; // Rendered aligned cutout bitmap or SVG simulation
  residualDataUrl?: string; // Per-frame leave-one-out difference image PNG
  bloomDataUrl?: string; // Detector BLOOM core bitmask PNG
  imageWidth?: number; // Native pixel width of cutout
  imageHeight?: number; // Native pixel height of cutout
  archiveUrl?: string; // Direct NASA/IPAC IRSA FITS URL
  release?: string; // DR1 or QR2/QR3
  coverage?: number; // Fraction of valid finite pixels (0-1)
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
  /** Detector score 0–1 (higher = more likely a real moving object). Supplied by the ML pipeline when available. */
  mlScore?: number;
  mlRank?: number; // 1 = highest priority
  mlPriorityScore?: number; // 0.0 - 1.0
  priorityHexColor?: string;
  /** Precomputed or live 29x29 coadd at fixed median sky position (PNG data URL) */
  fixedStackDataUrl?: string;
  /** Precomputed or live 29x29 coadd following the fitted linear track (PNG data URL) */
  motionStackDataUrl?: string;
  /** Number of exposures contributing at the stack center */
  stackContributingExposures?: number;
  /** Ranking method that produced this track */
  detectionMethod?: 'heuristic_leave_one_out' | 'bloom_centroids' | 'baseline';
  /** Heuristic rank from leave-one-out / bloom pipeline */
  heuristicRank?: number;
  /** Random Forest rank from simulated-field classifier */
  randomForestRank?: number | null;
  /** Linear fit RMS residual in pixels */
  fitRmsPx?: number;
  /** Apparent speed in pixels per hour */
  speedPxPerHour?: number;
  /** Apparent sky speed in arcsec per hour */
  speedArcsecPerHour?: number;
  /** Per-epoch BLOOM flagged pixel area when detected via BLOOM centroids */
  bloomAreaPx?: number[];
  /** Per-epoch matched-filter support fraction (0-1) */
  filterSupport?: number[] | null;
  /** Whether an OUTLIER bitmask flag is near each epoch detection */
  outlierAtPosition?: boolean[];
  /** Per-epoch ephemeris offsets in pixels */
  ephemerisOffsetsPx?: number[] | null;
}

export interface VerificationSetting {
  targetPresetId?: string | null;
  candidateId: string;
  candidateName: string;
  ra: number;
  dec: number;
  fov: FOVOption;
  selectedArray: DetectorArrayId | 'all';
  activeFrameIndex: number;
  subtractionMode: SubtractionMode;
}

export interface VerificationComment {
  id: string;
  author: string;
  role: 'Volunteer' | 'Researcher' | 'Science Team';
  timestamp: string;
  candidateId: string;
  message: string;
  vote: 'confirm_motion' | 'artifact' | 'investigate' | 'known';
  upvotes: number;
  setting?: VerificationSetting;
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
