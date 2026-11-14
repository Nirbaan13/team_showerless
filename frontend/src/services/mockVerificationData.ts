import type { VerificationComment } from '../types/spherex';

export const SEEDED_VERIFICATION_DISCUSSIONS: VerificationComment[] = [
  {
    id: 'verify-3i-atlas-01',
    author: 'Dr. Elena Rostova',
    role: 'Science Team',
    timestamp: '2 hours ago',
    candidateId: '3I/ATLAS',
    message:
      'Detected non-sidereal moving object across 4 QR2 exposures within 0.54 px of NASA/JPL Horizons ephemeris. Clear hyperbolic interstellar trajectory verified.',
    vote: 'confirm_motion',
    upvotes: 18,
    setting: {
      targetPresetId: '3i-atlas',
      candidateId: '3I/ATLAS',
      candidateName: '3I/ATLAS Comet (C/2024 S1)',
      ra: 166.790000,
      dec: 5.290000,
      fov: "3'",
      selectedArray: 6,
      activeFrameIndex: 2,
      subtractionMode: 'raw_calibrated',
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
    id: 'verify-3i-coma',
    author: 'Shasta P.',
    role: 'Science Team',
    timestamp: '7 hours ago',
    candidateId: 'cand-3i-tail-clump',
    message:
      'Cometary dust coma ion clump trailing 0.02 deg southeast of 3I/ATLAS nucleus. High linear correlation with primary ephemeris vector.',
    vote: 'confirm_motion',
    upvotes: 8,
    setting: {
      targetPresetId: '3i-atlas',
      candidateId: 'cand-3i-tail-clump',
      candidateName: '3I/ATLAS Coma Dust Structure',
      ra: 166.812400,
      dec: 5.275100,
      fov: "3'",
      selectedArray: 6,
      activeFrameIndex: 2,
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
