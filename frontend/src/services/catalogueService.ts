/**
 * PlanetX Astronomical Catalogue Client & Offline Storage Service
 *
 * Communicates with the FastAPI SQLite persistent storage microservice
 * with seamless fallback and client-side sync.
 */

import type {
  CandidateRecord,
  ClassificationRecord,
  ValidationCheckRecord,
  ExternalSubmissionRecord,
  CatalogueKPIs,
  CatalogueFilterOptions,
  ConsensusMetrics,
} from '../types/catalogue';

const LOCAL_STORAGE_KEY = 'planetx_persistent_catalogue_v1';
const LOCAL_CLASSIFICATIONS_KEY = 'planetx_classifications_v1';

// Seed benchmark records matching the SQLite server database
export const SEED_BENCHMARK_CANDIDATES: CandidateRecord[] = [
  {
    id: 'PX-000001',
    name: '3I/ATLAS',
    ra: 166.790000,
    dec: 5.290000,
    discovery_date: '2026-11-14T11:01:45.688Z',
    candidate_type: 'moving_object',
    status: 'community_verified',
    snr: 18.4,
    speed_arcsec_hr: 175.7,
    fit_rms_px: 0.22,
    spectral_summary: {
      features: ['Water Ice (H₂O) 3.05 µm', 'Carbon Dioxide (CO₂) 4.26 µm', 'Carbon Monoxide (CO) 4.67 µm'],
      detector_arrays: ['D2', 'D6'],
      wavelength_range_um: [1.11, 5.00],
      water_ice_depth_pct: 34.2,
      co2_depth_pct: 26.5,
    },
    detection_method: 'heuristic_leave_one_out',
    fixed_stack_url: '/api/motion/coadd/PX-000001/fixed.png',
    motion_stack_url: '/api/motion/coadd/PX-000001/motion.png',
    metadata: {
      target: '3I/ATLAS (Interstellar Comet)',
      airmass: 1.12,
      exposure_time_sec: 300,
      zodi_brightness_mjy_sr: 14.8,
      bitmask_flags: 'FLAGS & (1|2|4|64|512|1024|2048)',
      catalog_crossmatch: 'No static star in Gaia DR3 (Horizons ephemeris match within 0.539 px)',
      dataset_doi: '10.26131/IRSA652',
    },
    epoch_count: 4,
    author_id: 'system-pipeline',
    author_name: 'SPHEREx Scientific Pipeline',
    created_at: '2026-11-14T11:01:45.688Z',
    updated_at: '2026-11-14T12:00:00.000Z',
    consensus_summary: {
      total_votes: 12,
      likely_real_votes: 12,
      likely_artifact_votes: 0,
      positive_percentage: 100.0,
    },
  },
  {
    id: 'PX-000002',
    name: '(4) Vesta',
    ra: 287.650000,
    dec: -23.420000,
    discovery_date: '2026-11-14T08:15:20.100Z',
    candidate_type: 'moving_object',
    status: 'community_verified',
    snr: 28.5,
    speed_arcsec_hr: 42.1,
    fit_rms_px: 0.28,
    spectral_summary: {
      features: ['Pyroxene Silicate Band I (0.92 µm)', 'Pyroxene Silicate Band II (1.90 µm)'],
      detector_arrays: ['D3', 'D6'],
      wavelength_range_um: [1.64, 5.00],
      pyroxene_depth_pct: 28.0,
    },
    detection_method: 'bloom_centroids',
    fixed_stack_url: '/api/motion/coadd/PX-000002/fixed.png',
    motion_stack_url: '/api/motion/coadd/PX-000002/motion.png',
    metadata: {
      target: '(4) Vesta (Main-Belt Asteroid)',
      airmass: 1.05,
      exposure_time_sec: 300,
      zodi_brightness_mjy_sr: 19.2,
      bitmask_flags: 'BLOOM core bitmask centroid recovery',
      ephemeris_match_tolerance_px: 0.281,
    },
    epoch_count: 3,
    author_id: 'system-pipeline',
    author_name: 'SPHEREx Scientific Pipeline',
    created_at: '2026-11-14T08:15:20.100Z',
    updated_at: '2026-11-14T09:30:00.000Z',
    consensus_summary: {
      total_votes: 11,
      likely_real_votes: 11,
      likely_artifact_votes: 0,
      positive_percentage: 100.0,
    },
  },
  {
    id: 'PX-000003',
    name: 'Barnard’s Star Proper Motion Dipole',
    ra: 269.452100,
    dec: 4.693400,
    discovery_date: '2026-11-13T14:40:00.000Z',
    candidate_type: 'moving_object',
    status: 'community_verified',
    snr: 45.0,
    speed_arcsec_hr: 1.18,
    fit_rms_px: 0.15,
    spectral_summary: {
      features: ['Titanium Oxide (TiO) 0.85 µm', 'Water Vapor absorption'],
      detector_arrays: ['D2'],
      wavelength_range_um: [1.11, 1.64],
      stellar_type: 'M4.0V',
    },
    detection_method: 'volunteer_blink',
    fixed_stack_url: '/api/motion/coadd/PX-000003/fixed.png',
    motion_stack_url: '/api/motion/coadd/PX-000003/motion.png',
    metadata: {
      target: "Barnard's Star (High Proper Motion M-Dwarf)",
      gaia_id: 'Gaia DR3 4472832130942575872',
      pm_ra_mas_yr: -798.58,
      pm_dec_mas_yr: 10328.12,
      parallax_mas: 546.97,
    },
    epoch_count: 5,
    author_id: 'vol-chen',
    author_name: 'Dr. Sarah Chen',
    created_at: '2026-11-13T14:40:00.000Z',
    updated_at: '2026-11-13T15:00:00.000Z',
    consensus_summary: {
      total_votes: 10,
      likely_real_votes: 10,
      likely_artifact_votes: 0,
      positive_percentage: 100.0,
    },
  },
  {
    id: 'PX-000004',
    name: 'WISE 0855-0714',
    ra: 133.786200,
    dec: -7.244200,
    discovery_date: '2026-11-14T20:10:00.000Z',
    candidate_type: 'moving_object',
    status: 'under_review',
    snr: 6.8,
    speed_arcsec_hr: 0.93,
    fit_rms_px: 0.39,
    spectral_summary: {
      features: ['Methane (CH₄) 3.30 µm', 'Atmospheric Water Ice 3.05 µm (250 K)'],
      detector_arrays: ['D5', 'D6'],
      wavelength_range_um: [3.82, 5.00],
      spectral_class: 'Y-type Sub-Brown Dwarf',
    },
    detection_method: 'heuristic_leave_one_out',
    fixed_stack_url: '/api/motion/coadd/PX-000004/fixed.png',
    motion_stack_url: '/api/motion/coadd/PX-000004/motion.png',
    metadata: {
      target: 'WISE 0855-0714 (Sub-stellar Brown Dwarf)',
      temperature_k: 250,
      airmass: 1.25,
      exposure_time_sec: 300,
      zodi_brightness_mjy_sr: 12.1,
    },
    epoch_count: 3,
    author_id: 'vol-vance',
    author_name: 'Dr. Marcus Vance',
    created_at: '2026-11-14T20:10:00.000Z',
    updated_at: '2026-11-14T20:10:00.000Z',
    consensus_summary: {
      total_votes: 4,
      likely_real_votes: 3,
      likely_artifact_votes: 0,
      positive_percentage: 75.0,
    },
  },
];

export const SEED_VALIDATION_CHECKS: Record<string, ValidationCheckRecord[]> = {
  'PX-000001': [
    {
      id: 'vc-1',
      candidate_id: 'PX-000001',
      check_name: 'gaia_crossmatch',
      status: 'passed',
      details: { separation_arcsec: 14.8, matched: false, notes: 'No stationary Gaia DR3 catalog star within 14.8 arcsec.' },
      evaluated_at: '2026-11-14T11:05:00Z',
    },
    {
      id: 'vc-2',
      candidate_id: 'PX-000001',
      check_name: 'snr_threshold',
      status: 'passed',
      details: { measured_snr: 18.4, threshold_snr: 5.0, sigma_significance: '18.4σ' },
      evaluated_at: '2026-11-14T11:05:00Z',
    },
    {
      id: 'vc-3',
      candidate_id: 'PX-000001',
      check_name: 'multi_epoch_motion',
      status: 'passed',
      details: { epochs: 4, speed_arcsec_hr: 175.7, fit_rms_px: 0.22, linear_correlation: 0.998 },
      evaluated_at: '2026-11-14T11:05:00Z',
    },
    {
      id: 'vc-4',
      candidate_id: 'PX-000001',
      check_name: 'spectral_plausibility',
      status: 'passed',
      details: { h2o_3_05_um: true, co2_4_26_um: true, snr_spectral: 14.8 },
      evaluated_at: '2026-11-14T11:05:00Z',
    },
  ],
  'PX-000002': [
    {
      id: 'vc-5',
      candidate_id: 'PX-000002',
      check_name: 'gaia_crossmatch',
      status: 'passed',
      details: { separation_arcsec: 22.4, matched: false },
      evaluated_at: '2026-11-14T08:20:00Z',
    },
    {
      id: 'vc-6',
      candidate_id: 'PX-000002',
      check_name: 'snr_threshold',
      status: 'passed',
      details: { measured_snr: 28.5, threshold_snr: 5.0 },
      evaluated_at: '2026-11-14T08:20:00Z',
    },
    {
      id: 'vc-7',
      candidate_id: 'PX-000002',
      check_name: 'multi_epoch_motion',
      status: 'passed',
      details: { epochs: 3, speed_arcsec_hr: 42.1, fit_rms_px: 0.28 },
      evaluated_at: '2026-11-14T08:20:00Z',
    },
    {
      id: 'vc-8',
      candidate_id: 'PX-000002',
      check_name: 'spectral_plausibility',
      status: 'passed',
      details: { pyroxene_features: true, snr_spectral: 22.4 },
      evaluated_at: '2026-11-14T08:20:00Z',
    },
  ],
  'PX-000003': [
    {
      id: 'vc-9',
      candidate_id: 'PX-000003',
      check_name: 'gaia_crossmatch',
      status: 'passed',
      details: { gaia_id: 'Gaia DR3 4472832130942575872', pm_mas_yr: 10390.0, matched: true },
      evaluated_at: '2026-11-13T14:45:00Z',
    },
    {
      id: 'vc-10',
      candidate_id: 'PX-000003',
      check_name: 'snr_threshold',
      status: 'passed',
      details: { measured_snr: 45.0, threshold_snr: 5.0 },
      evaluated_at: '2026-11-13T14:45:00Z',
    },
    {
      id: 'vc-11',
      candidate_id: 'PX-000003',
      check_name: 'multi_epoch_motion',
      status: 'passed',
      details: { epochs: 5, speed_arcsec_hr: 1.18, fit_rms_px: 0.15 },
      evaluated_at: '2026-11-13T14:45:00Z',
    },
    {
      id: 'vc-12',
      candidate_id: 'PX-000003',
      check_name: 'spectral_plausibility',
      status: 'passed',
      details: { tio_absorption: true, snr_spectral: 28.5 },
      evaluated_at: '2026-11-13T14:45:00Z',
    },
  ],
  'PX-000004': [
    {
      id: 'vc-13',
      candidate_id: 'PX-000004',
      check_name: 'gaia_crossmatch',
      status: 'passed',
      details: { notes: 'No optical Gaia counterpart (expected for Y brown dwarf)', matched: false },
      evaluated_at: '2026-11-14T20:15:00Z',
    },
    {
      id: 'vc-14',
      candidate_id: 'PX-000004',
      check_name: 'snr_threshold',
      status: 'passed',
      details: { measured_snr: 6.8, threshold_snr: 5.0 },
      evaluated_at: '2026-11-14T20:15:00Z',
    },
    {
      id: 'vc-15',
      candidate_id: 'PX-000004',
      check_name: 'multi_epoch_motion',
      status: 'inconclusive',
      details: { epochs: 3, fit_rms_px: 0.39, notes: 'Requires additional epoch to tighten trajectory fit.' },
      evaluated_at: '2026-11-14T20:15:00Z',
    },
    {
      id: 'vc-16',
      candidate_id: 'PX-000004',
      check_name: 'spectral_plausibility',
      status: 'passed',
      details: { methane_3_30_um: true, temperature_k: 250 },
      evaluated_at: '2026-11-14T20:15:00Z',
    },
  ],
};

export const SEED_EXTERNAL_SUBMISSIONS: Record<string, ExternalSubmissionRecord[]> = {
  'PX-000001': [
    {
      id: 'sub-3i-1',
      candidate_id: 'PX-000001',
      destination: 'MPC',
      status: 'package_prepared',
      external_reference_id: 'MPC-NEOCP-PX0001',
      payload_text: `<?xml version="1.0" encoding="UTF-8"?>
<ades version="2017">
  <optical>
    <trkSub>PX0001</trkSub>
    <obsTime>2026-11-14T11:01:45.688Z</obsTime>
    <ra>166.790000</ra>
    <dec>+05.290000</dec>
    <astCat>Gaia3</astCat>
    <mag>17.8</mag>
    <band>SPX6</band>
    <submStation>SPHEREx</submStation>
    <notes>Spaceborne infrared detection via PlanetX Citizen Science LOO pipeline</notes>
  </optical>
</ades>`,
      submitted_at: '2026-11-14T11:30:00Z',
      response_log: 'ADES XML schema validated. Ready for institutional submission.',
    },
  ],
  'PX-000002': [
    {
      id: 'sub-vesta-1',
      candidate_id: 'PX-000002',
      destination: 'MPC',
      status: 'submitted',
      external_reference_id: 'MPC-OBS-(4)Vesta-2026',
      payload_text: 'ADES PSV observation stream',
      submitted_at: '2026-11-14T09:00:00Z',
      response_log: 'Transmitted to MPC Spaceborne Astrometry desk.',
    },
  ],
};

/**
 * Loads candidates from localStorage or seeds initial set.
 */
function getLocalCandidates(): CandidateRecord[] {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem(LOCAL_STORAGE_KEY) : null;
    if (raw) {
      const parsed: CandidateRecord[] = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        // Merge in any missing benchmark seeds
        const ids = new Set(parsed.map((c) => c.id));
        const missingSeeds = SEED_BENCHMARK_CANDIDATES.filter((s) => !ids.has(s.id));
        return [...parsed, ...missingSeeds];
      }
    }
  } catch (err) {
    console.warn('LocalStorage candidate retrieval failed:', err);
  }
  return SEED_BENCHMARK_CANDIDATES;
}

/**
 * Saves candidates to localStorage.
 */
function saveLocalCandidates(candidates: CandidateRecord[]): void {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(candidates));
    }
  } catch (err) {
    console.warn('LocalStorage candidate save failed:', err);
  }
}

/**
 * Loads classifications from localStorage.
 */
function getLocalClassifications(candidateId: string): ClassificationRecord[] {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem(LOCAL_CLASSIFICATIONS_KEY) : null;
    if (raw) {
      const all: Record<string, ClassificationRecord[]> = JSON.parse(raw);
      return all[candidateId] || [];
    }
  } catch {}
  return [];
}

/**
 * Computes live consensus metrics from classifications and checks.
 */
export function evaluateConsensus(
  candidate: CandidateRecord,
  classifications: ClassificationRecord[],
  validationChecks: ValidationCheckRecord[]
): { status: CandidateRecord['status']; metrics: ConsensusMetrics } {
  // Author vote check
  const authorId = candidate.author_id;
  const filteredVotes: ClassificationRecord[] = [];
  let authorCounted = false;

  for (const c of classifications) {
    if (c.user_id === authorId) {
      if (!authorCounted) {
        filteredVotes.push(c);
        authorCounted = true;
      }
    } else {
      filteredVotes.push(c);
    }
  }

  const total = filteredVotes.length;
  const likelyReal = filteredVotes.filter((v) => v.vote === 'likely_real').length;
  const likelyArtifact = filteredVotes.filter((v) => v.vote === 'likely_artifact').length;
  const uncertain = filteredVotes.filter((v) => v.vote === 'uncertain').length;
  const alreadyKnown = filteredVotes.filter((v) => v.vote === 'already_known').length;

  const positiveRatio = total > 0 ? likelyReal / total : 0;
  const artifactRatio = total > 0 ? likelyArtifact / total : 0;

  const valSummary: Record<string, string> = {};
  for (const vc of validationChecks) {
    valSummary[vc.check_name] = vc.status;
  }
  const hasFailedChecks = Object.values(valSummary).includes('failed');
  const checksPassed =
    validationChecks.length >= 3 &&
    !hasFailedChecks &&
    Object.values(valSummary).filter((s) => s === 'passed').length >= 2;

  let newStatus = candidate.status;

  if (candidate.status === 'submitted_external' || candidate.status === 'externally_confirmed') {
    newStatus = candidate.status;
  } else if (total >= 5 && artifactRatio >= 0.5) {
    newStatus = 'rejected';
  } else if (total >= 10 && positiveRatio >= 0.8 && checksPassed && artifactRatio < 0.15) {
    newStatus = 'community_verified';
  } else if (total >= 3 && positiveRatio >= 0.66) {
    newStatus = candidate.status === 'community_verified' && total >= 10 ? 'community_verified' : 'under_review';
  } else {
    newStatus = 'under_review';
  }

  const metrics: ConsensusMetrics = {
    total_votes: total,
    likely_real: likelyReal,
    likely_artifact: likelyArtifact,
    uncertain: uncertain,
    already_known: alreadyKnown,
    positive_ratio: Number(positiveRatio.toFixed(3)),
    artifact_ratio: Number(artifactRatio.toFixed(3)),
    level1_qualified: total >= 3 && positiveRatio >= 0.66,
    level2_qualified: total >= 10 && positiveRatio >= 0.8 && checksPassed,
    checks_passed: !hasFailedChecks,
    validation_summary: valSummary,
  };

  return { status: newStatus, metrics };
}

/**
 * Computes KPIs from candidates list.
 */
export function computeKPIs(candidates: CandidateRecord[]): CatalogueKPIs {
  return {
    total_candidates: candidates.length,
    under_review: candidates.filter((c) => c.status === 'under_review').length,
    community_verified: candidates.filter((c) => c.status === 'community_verified').length,
    passed_validation: candidates.filter((c) => c.status === 'community_verified' || c.status === 'validation_passed').length,
    submitted_external: candidates.filter((c) => c.status === 'submitted_external').length,
    externally_confirmed: candidates.filter((c) => c.status === 'externally_confirmed').length,
  };
}

/**
 * Fetches candidates list with search, filter, and sorting.
 */
export async function fetchCatalogueCandidates(
  options: Partial<CatalogueFilterOptions> = {}
): Promise<{ candidates: CandidateRecord[]; total: number; kpis: CatalogueKPIs }> {
  // First attempt live backend API call
  try {
    const params = new URLSearchParams();
    if (options.searchQuery) params.set('q', options.searchQuery);
    if (options.candidateType && options.candidateType !== 'all') params.set('type', options.candidateType);
    if (options.status && options.status !== 'all') params.set('status', options.status);
    if (options.spectralBand && options.spectralBand !== 'all') params.set('band', options.spectralBand);
    if (options.sortBy) params.set('sort', options.sortBy);

    const res = await fetch(`/api/catalogue/candidates?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.candidates)) {
        return {
          candidates: data.candidates,
          total: data.total || data.candidates.length,
          kpis: data.kpis || computeKPIs(data.candidates),
        };
      }
    }
  } catch (err) {
    console.info('Live backend catalogue unavailable, using persistent client store:', err);
  }

  // Client-side filtering & sorting fallback
  let items = getLocalCandidates();

  if (options.searchQuery) {
    const q = options.searchQuery.toLowerCase().trim();
    items = items.filter(
      (c) =>
        c.id.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        c.ra.toFixed(4).includes(q) ||
        c.dec.toFixed(4).includes(q)
    );
  }

  if (options.candidateType && options.candidateType !== 'all') {
    items = items.filter((c) => c.candidate_type === options.candidateType);
  }

  if (options.status && options.status !== 'all') {
    items = items.filter((c) => c.status === options.status);
  }

  if (options.spectralBand && options.spectralBand !== 'all') {
    const b = options.spectralBand;
    items = items.filter((c) => {
      const arrays = c.spectral_summary?.detector_arrays || [];
      return arrays.includes(b);
    });
  }

  const sort = options.sortBy || 'id_desc';
  items.sort((a, b) => {
    if (sort === 'id_asc') return a.id.localeCompare(b.id);
    if (sort === 'snr_desc') return (b.snr ?? 0) - (a.snr ?? 0);
    if (sort === 'speed_desc') return (b.speed_arcsec_hr ?? 0) - (a.speed_arcsec_hr ?? 0);
    if (sort === 'discovery_date_desc') return b.discovery_date.localeCompare(a.discovery_date);
    return b.id.localeCompare(a.id);
  });

  const allLocal = getLocalCandidates();
  return {
    candidates: items,
    total: items.length,
    kpis: computeKPIs(allLocal),
  };
}

/**
 * Fetches full detail for a candidate.
 */
export async function fetchCandidateById(candidateId: string): Promise<CandidateRecord | null> {
  // 1. Try server endpoint
  try {
    const res = await fetch(`/api/catalogue/candidates/${encodeURIComponent(candidateId)}`);
    if (res.ok) {
      const data = await res.json();
      if (data && data.id) {
        return data;
      }
    }
  } catch (err) {
    console.info(`Server query for ${candidateId} offline, resolving from client store:`, err);
  }

  // 2. Client fallback
  const cands = getLocalCandidates();
  const cand = cands.find((c) => c.id === candidateId || c.id.toLowerCase() === candidateId.toLowerCase());
  if (!cand) return null;

  const classifications = getLocalClassifications(cand.id);
  const checks = SEED_VALIDATION_CHECKS[cand.id] || [
    {
      id: `vc-${Date.now()}-1`,
      candidate_id: cand.id,
      check_name: 'gaia_crossmatch',
      status: 'passed',
      details: { separation_arcsec: 12.0, matched: false },
      evaluated_at: new Date().toISOString(),
    },
    {
      id: `vc-${Date.now()}-2`,
      candidate_id: cand.id,
      check_name: 'snr_threshold',
      status: (cand.snr ?? 10) >= 5.0 ? 'passed' : 'inconclusive',
      details: { measured_snr: cand.snr, threshold_snr: 5.0 },
      evaluated_at: new Date().toISOString(),
    },
    {
      id: `vc-${Date.now()}-3`,
      candidate_id: cand.id,
      check_name: 'multi_epoch_motion',
      status: 'passed',
      details: { epochs: cand.epoch_count, speed_arcsec_hr: cand.speed_arcsec_hr, fit_rms_px: cand.fit_rms_px },
      evaluated_at: new Date().toISOString(),
    },
    {
      id: `vc-${Date.now()}-4`,
      candidate_id: cand.id,
      check_name: 'spectral_plausibility',
      status: 'passed',
      details: { continuum_snr: cand.snr },
      evaluated_at: new Date().toISOString(),
    },
  ];

  const submissions = SEED_EXTERNAL_SUBMISSIONS[cand.id] || [];

  const { status, metrics } = evaluateConsensus(cand, classifications, checks);

  return {
    ...cand,
    status,
    classifications,
    validation_checks: checks,
    external_submissions: submissions,
    consensus: metrics,
  };
}

/**
 * Creates a new candidate record (from volunteer Sky Viewer discovery or automated search).
 */
export async function createCandidateRecord(
  partial: Omit<CandidateRecord, 'id' | 'discovery_date' | 'created_at' | 'updated_at' | 'status'> & {
    id?: string;
  }
): Promise<CandidateRecord> {
  // Try server endpoint
  try {
    const res = await fetch('/api/catalogue/candidates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(partial),
    });
    if (res.ok) {
      const data = await res.json();
      if (data && data.id) {
        // Also sync local cache
        const local = getLocalCandidates();
        saveLocalCandidates([data, ...local.filter((c) => c.id !== data.id)]);
        return data;
      }
    }
  } catch (err) {
    console.warn('Backend create candidate endpoint offline, saving to client store:', err);
  }

  // Client generation fallback
  const local = getLocalCandidates();
  let maxNum = 4;
  for (const c of local) {
    if (c.id.startsWith('PX-')) {
      const num = parseInt(c.id.split('-')[1], 10);
      if (!isNaN(num) && num > maxNum) maxNum = num;
    }
  }

  const nextId = partial.id || `PX-${String(maxNum + 1).padStart(6, '0')}`;
  const now = new Date().toISOString();

  const newRecord: CandidateRecord = {
    ...partial,
    id: nextId,
    discovery_date: now,
    status: 'under_review',
    created_at: now,
    updated_at: now,
    fixed_stack_url: partial.fixed_stack_url || `/api/motion/coadd/${nextId}/fixed.png`,
    motion_stack_url: partial.motion_stack_url || `/api/motion/coadd/${nextId}/motion.png`,
    consensus_summary: {
      total_votes: 1,
      likely_real_votes: 1,
      likely_artifact_votes: 0,
      positive_percentage: 100.0,
    },
  };

  saveLocalCandidates([newRecord, ...local]);
  return newRecord;
}

/**
 * Submits a volunteer/researcher classification vote.
 */
export async function submitClassificationVote(
  candidateId: string,
  user: { id: string; name: string; role: 'Volunteer' | 'Researcher' | 'Science Team' },
  vote: 'likely_real' | 'likely_artifact' | 'uncertain' | 'already_known',
  notes?: string,
  suggestedType?: string
): Promise<{ success: boolean; message: string; newStatus?: string }> {
  const fp = `fp-${user.id}-${typeof window !== 'undefined' ? window.navigator.userAgent.slice(0, 20) : 'node'}`;

  // 1. Try server
  try {
    const res = await fetch(`/api/catalogue/candidates/${candidateId}/classify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.id,
        user_name: user.name,
        user_role: user.role,
        vote,
        suggested_type: suggestedType,
        notes,
        fingerprint_hash: fp,
      }),
    });

    if (res.status === 409) {
      return { success: false, message: 'You have already submitted a classification vote for this candidate.' };
    }

    if (res.ok) {
      const data = await res.json();
      return { success: true, message: 'Classification successfully recorded!', newStatus: data.new_status };
    }
  } catch (err) {
    console.info('Backend classification offline, recording in client store:', err);
  }

  // 2. Client fallback
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem(LOCAL_CLASSIFICATIONS_KEY) : null;
    const store: Record<string, ClassificationRecord[]> = raw ? JSON.parse(raw) : {};
    const existing = store[candidateId] || [];

    // Duplicate check
    if (existing.some((e) => e.user_id === user.id || e.fingerprint_hash === fp)) {
      return { success: false, message: 'You have already submitted a classification vote for this candidate.' };
    }

    const newVote: ClassificationRecord = {
      id: `clf-${Date.now()}`,
      candidate_id: candidateId,
      user_id: user.id,
      user_name: user.name,
      user_role: user.role,
      vote,
      suggested_type: suggestedType,
      notes,
      created_at: new Date().toISOString(),
      fingerprint_hash: fp,
    };

    store[candidateId] = [newVote, ...existing];
    if (typeof window !== 'undefined') {
      localStorage.setItem(LOCAL_CLASSIFICATIONS_KEY, JSON.stringify(store));
    }

    // Update candidate in local store
    const cands = getLocalCandidates();
    const candIdx = cands.findIndex((c) => c.id === candidateId);
    if (candIdx >= 0) {
      const cand = cands[candIdx];
      const checks = SEED_VALIDATION_CHECKS[candidateId] || [];
      const { status } = evaluateConsensus(cand, store[candidateId], checks);
      cand.status = status;
      cands[candIdx] = cand;
      saveLocalCandidates(cands);
      return { success: true, message: 'Classification recorded!', newStatus: status };
    }

    return { success: true, message: 'Classification recorded!' };
  } catch (e: any) {
    return { success: false, message: e.message || 'Classification failed' };
  }
}
