import type { VerificationComment } from '../types/spherex';

export const SEEDED_VERIFICATION_DISCUSSIONS: VerificationComment[] = [
  {
    id: 'verify-3i-atlas-01',
    author: 'Dr. Elena Rostova',
    role: 'Science Team',
    timestamp: '1 hour ago',
    candidateId: '3I/ATLAS',
    message:
      'Detected non-sidereal moving object across 4 QR2 Band-6 exposures within 0.539 px of NASA/JPL Horizons ephemeris. Ranked #1/10 by per-frame leave-one-out heuristic & #3/10 by Random Forest.',
    vote: 'confirm_motion',
    upvotes: 24,
    setting: {
      targetPresetId: '3i-atlas',
      candidateId: '3I/ATLAS',
      candidateName: '3I/ATLAS Comet (D6 · 4 QR2 Exposures)',
      ra: 166.790000,
      dec: 5.290000,
      fov: "5'",
      selectedArray: 6,
      activeFrameIndex: 2,
      subtractionMode: 'epoch_difference',
    },
  },
  {
    id: 'verify-vesta-d6-bloom',
    author: 'Ivan K. · ML Pipeline',
    role: 'Science Team',
    timestamp: '2 hours ago',
    candidateId: '(4) Vesta (D6 BLOOM)',
    message:
      'Bright asteroid (4) Vesta saturates the SPHEREx D6 detector core, leaving NaN holes in standard difference images. Linking BLOOM bitmask centroids recovers the track at #1 within 0.281 px of JPL Horizons.',
    vote: 'confirm_motion',
    upvotes: 19,
    setting: {
      targetPresetId: 'vesta-d6',
      candidateId: '(4) Vesta (D6 BLOOM)',
      candidateName: '(4) Vesta Asteroid (D6 · BLOOM Core Track)',
      ra: 223.024527,
      dec: -11.992267,
      fov: "5'",
      selectedArray: 6,
      activeFrameIndex: 1,
      subtractionMode: 'bloom_mask',
    },
  },
  {
    id: 'verify-3i-atlas-d2',
    author: 'Ivan K. · ML Pipeline',
    role: 'Researcher',
    timestamp: '3 hours ago',
    candidateId: '3I/ATLAS (D2)',
    message:
      'Short-wave Band 2 (D2) sequence of 3I/ATLAS across 3 visits. A shared median reference drops the first detection due to a mask gap, whereas per-frame leave-one-out subtraction recovers the track at #1 (0.604 px offset).',
    vote: 'confirm_motion',
    upvotes: 16,
    setting: {
      targetPresetId: '3i-atlas-d2',
      candidateId: '3I/ATLAS (D2)',
      candidateName: '3I/ATLAS Comet (D2 · Mask Gap Recovery)',
      ra: 167.206653,
      dec: 5.146825,
      fov: "3'",
      selectedArray: 2,
      activeFrameIndex: 1,
      subtractionMode: 'epoch_difference',
    },
  },
  {
    id: 'verify-vesta-d3-bloom',
    author: 'Dr. Marcus Vance',
    role: 'Science Team',
    timestamp: '3 hours ago',
    candidateId: '(4) Vesta (D3 BLOOM)',
    message:
      'Mid-IR Band 3 (D3) sequence of (4) Vesta across 3 DR1 visits (32–33 BLOOM-flagged core pixels per visit). BLOOM centroid linking achieves 0.382 px max ephemeris offset vs 25 unlinked halo residual tracks.',
    vote: 'confirm_motion',
    upvotes: 15,
    setting: {
      targetPresetId: 'vesta-d3',
      candidateId: '(4) Vesta (D3 BLOOM)',
      candidateName: '(4) Vesta Asteroid (D3 · Mid-IR BLOOM Mask)',
      ra: 223.024527,
      dec: -11.992267,
      fov: "5'",
      selectedArray: 3,
      activeFrameIndex: 0,
      subtractionMode: 'bloom_mask',
    },
  },
  {
    id: 'verify-barnard-01',
    author: 'Dr. Sarah Chen',
    role: 'Researcher',
    timestamp: '4 hours ago',
    candidateId: 'cand-barnard-primary',
    message:
      'Rapid apparent vector motion of 10.3 arcsec/year confirmed across 5 SPHEREx epochs. Cross-matched with Gaia DR3 4472832130942575872.',
    vote: 'confirm_motion',
    upvotes: 12,
    setting: {
      targetPresetId: 'barnards-star',
      candidateId: 'cand-barnard-primary',
      candidateName: "Barnard's Star (Proper Motion Vector)",
      ra: 269.452075,
      dec: 4.693365,
      fov: "3'",
      selectedArray: 2,
      activeFrameIndex: 2,
      subtractionMode: 'raw_calibrated',
    },
  },
  {
    id: 'verify-barnard-flare',
    author: 'Alex Mercer',
    role: 'Volunteer',
    timestamp: '5 hours ago',
    candidateId: 'cand-barnard-anomaly-1',
    message:
      'Epoch 2 exhibits a sharp ~6x infrared flux spike at pixel (380, 170). No catalog counterpart in AllWISE. Highly recommended for follow-up triage.',
    vote: 'investigate',
    upvotes: 9,
    setting: {
      targetPresetId: 'barnards-star',
      candidateId: 'cand-barnard-anomaly-1',
      candidateName: 'Candidate IR Flare Anomaly (Epoch 2 Flare)',
      ra: 269.461100,
      dec: 4.689200,
      fov: "3'",
      selectedArray: 2,
      activeFrameIndex: 1,
      subtractionMode: 'raw_calibrated',
    },
  },
  {
    id: 'verify-wise-0855',
    author: 'Dr. Marcus Vance',
    role: 'Science Team',
    timestamp: '1 day ago',
    candidateId: 'cand-wise-0855-01',
    message:
      'Ultra-cold Y-type sub-brown dwarf detected predominantly in Band 6 (4.42–5.00 µm). Atmospheric water ice absorption band confirmed.',
    vote: 'confirm_motion',
    upvotes: 14,
    setting: {
      targetPresetId: 'wise-0855',
      candidateId: 'cand-wise-0855-01',
      candidateName: 'WISE 0855-0714 (Coldest Sub-Brown Dwarf)',
      ra: 133.795129,
      dec: -7.245147,
      fov: "3'",
      selectedArray: 5,
      activeFrameIndex: 0,
      subtractionMode: 'raw_calibrated',
    },
  },
];

export function getInitialVerificationComments(): VerificationComment[] {
  try {
    const saved = typeof window !== 'undefined' ? localStorage.getItem('spherex_community_comments') : null;
    if (saved) {
      const parsed: VerificationComment[] = JSON.parse(saved);
      const userWithSettings = parsed.filter((c) => c.setting);
      const combined = [...userWithSettings, ...SEEDED_VERIFICATION_DISCUSSIONS];
      return Array.from(new Map(combined.map((c) => [c.id, c])).values());
    }
  } catch {
    // Ignore localStorage failures
  }
  return SEEDED_VERIFICATION_DISCUSSIONS;
}
