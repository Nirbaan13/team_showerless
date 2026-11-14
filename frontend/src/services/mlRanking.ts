import type { CandidateObject } from '../types/spherex';

export interface RankedCandidate {
  candidate: CandidateObject;
  rank: number;
  score: number; // 0–1
  source: 'pipeline' | 'baseline';
}

/**
 * Baseline heuristic (mirrors the team's detector.py idea):
 *  - brighter detections (SNR) score higher
 *  - tracks seen in more epochs score higher
 *  - motion that follows a straight line at constant speed scores higher
 *    (real asteroids/comets move linearly over a few hours; artifacts don't)
 */
export function baselineScore(c: CandidateObject): number {
  const pts = c.epochPositions;
  if (!pts || pts.length === 0) return 0;

  const meanSnr = pts.reduce((s, p) => s + p.snr, 0) / pts.length;
  const snrTerm = Math.min(1, meanSnr / 20);
  const coverageTerm = Math.min(1, pts.length / 4);

  // Linearity: residual of each point from the line between first & last point
  let linearTerm = 0.3; // stationary sources (no motion) get a low motion score
  if (pts.length >= 3) {
    const a = pts[0];
    const b = pts[pts.length - 1];
    const span = Math.hypot(b.x - a.x, b.y - a.y);
    if (span > 1) {
      let resid = 0;
      for (let i = 1; i < pts.length - 1; i++) {
        const t = i / (pts.length - 1);
        const ex = a.x + (b.x - a.x) * t;
        const ey = a.y + (b.y - a.y) * t;
        resid += Math.hypot(pts[i].x - ex, pts[i].y - ey);
      }
      resid /= Math.max(1, pts.length - 2);
      linearTerm = Math.max(0, 1 - resid / Math.max(4, span * 0.25));
    }
  }

  // Flux stability: a single-epoch spike is more likely an artifact/transient
  const fluxes = pts.map((p) => p.flux);
  const meanF = fluxes.reduce((s, f) => s + f, 0) / fluxes.length;
  const sd = Math.sqrt(fluxes.reduce((s, f) => s + (f - meanF) ** 2, 0) / fluxes.length);
  const stabilityTerm = meanF > 0 ? Math.max(0, 1 - sd / meanF) : 0;

  return Number((0.35 * linearTerm + 0.3 * snrTerm + 0.2 * coverageTerm + 0.15 * stabilityTerm).toFixed(3));
}

export function rankCandidates(list: CandidateObject[]): RankedCandidate[] {
  return list
    .map((candidate) => {
      const hasPipeline = typeof candidate.mlScore === 'number';
      return {
        candidate,
        score: hasPipeline ? (candidate.mlScore as number) : baselineScore(candidate),
        source: (hasPipeline ? 'pipeline' : 'baseline') as RankedCandidate['source'],
        rank: 0,
      };
    })
    .sort((a, b) => {
      // Real validated detections keep their published rank order
      const ra = a.candidate.validationData?.baselineRank ?? Infinity;
      const rb = b.candidate.validationData?.baselineRank ?? Infinity;
      if (ra !== rb) return ra - rb;
      return b.score - a.score;
    })
    .map((r, i) => ({ ...r, rank: r.candidate.validationData?.baselineRank ?? i + 1 }));
}

export interface PriorityColorDef {
  border: string;
  fill: string;
  text: string;
  badgeBg: string;
  label: string;
}

/**
 * Returns priority-graded red colors.
 * Priority 1 gets the deepest intense crimson red, progressively fading to lighter reds for lower priority.
 */
export function getPriorityColors(rank: number): PriorityColorDef {
  switch (rank) {
    case 1:
      return {
        border: '#ef4444', // Intense Crimson Red
        fill: 'rgba(239, 68, 68, 0.45)',
        text: '#fee2e2',
        badgeBg: '#dc2626',
        label: 'Priority 1 (Highest Confidence)',
      };
    case 2:
      return {
        border: '#f87171', // Bright Red
        fill: 'rgba(248, 113, 113, 0.35)',
        text: '#fee2e2',
        badgeBg: '#ef4444',
        label: 'Priority 2',
      };
    case 3:
      return {
        border: '#fca5a5', // Medium Red
        fill: 'rgba(252, 165, 165, 0.25)',
        text: '#fecaca',
        badgeBg: '#f87171',
        label: 'Priority 3',
      };
    case 4:
      return {
        border: '#fecaca', // Soft Light Red
        fill: 'rgba(254, 202, 202, 0.18)',
        text: '#fca5a5',
        badgeBg: '#fca5a5',
        label: 'Priority 4',
      };
    default:
      return {
        border: 'rgba(254, 226, 226, 0.6)', // Faint Light Red
        fill: 'rgba(254, 226, 226, 0.10)',
        text: '#fecaca',
        badgeBg: '#fecaca',
        label: `Priority ${rank}`,
      };
  }
}

