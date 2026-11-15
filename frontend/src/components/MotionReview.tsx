import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Compass,
  Crosshair,
  Download,
  ExternalLink,
  Layers,
  Pause,
  Play,
  Sparkles,
  Cpu,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';
import {
  loadPrecomputedMotionReviews,
  type MotionReviewDataset,
  type MotionTrackCandidate,
  type RankingMethod,
} from '../services/motionReviewService';

type Layer = 'aligned' | 'residual' | 'bloom';

const toggleBase =
  'btn-tactile-sm rounded-lg border-2 border-black px-3 py-1.5 font-mono text-xs transition-all cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-300';
const inactiveStyle = 'bg-paper-900 text-paper-300 hover:text-white hover:bg-paper-850';
const activeEmerald = 'bg-emerald-400 text-gray-950 font-bold shadow-[0_0_12px_rgba(16,185,129,0.3)]';
const activeSky = 'bg-sky-400 text-gray-950 font-bold shadow-[0_0_12px_rgba(56,189,248,0.3)]';
const activeAmber = 'bg-amber-400 text-gray-950 font-bold shadow-[0_0_12px_rgba(251,191,36,0.3)]';

function utc(time: string) {
  return `${time.slice(11, 19)} UTC`;
}

function exportCandidate(review: MotionReviewDataset, candidate: MotionTrackCandidate) {
  const isBloom = candidate.method === 'bloom_centroids';
  const payload = {
    dataset: review.id,
    target: review.target,
    detector: review.detector,
    source: review.source,
    ranking: {
      rank: candidate.rank,
      total: (isBloom ? review.comparison.bloom : review.comparison.leave_one_out)?.candidates ?? 0,
      method: candidate.method,
      random_forest_rank: candidate.random_forest_rank ?? null,
      random_forest_simulated_training_fields: isBloom ? null : review.simulated_training_fields,
    },
    status: candidate.known_match ? 'known_ephemeris_match' : 'unreviewed',
    ephemeris_match_tolerance_px: review.ephemeris_match_tolerance_px,
    max_ephemeris_offset_px: candidate.max_offset_px,
    fit_rms_px: candidate.fit_rms_px,
    speed_arcsec_per_hour: candidate.speed_px_per_time * review.pixel_scale_arcsec,
    retains_outlier_pixels: review.retains_outliers,
    detections: candidate.epochs.map((epoch, index) => ({
      observation_id: review.frames[epoch].id,
      archive_url: review.frames[epoch].archive_url,
      release: review.frames[epoch].release,
      utc_midpoint: review.frames[epoch].time,
      x_px: candidate.positions_xy[index][0],
      y_px: candidate.positions_xy[index][1],
      ra_deg: candidate.sky_deg[index][0],
      dec_deg: candidate.sky_deg[index][1],
      residual_snr: candidate.snr?.[index] ?? null,
      filter_support: candidate.filter_support?.[index] ?? null,
      bloom_area_px: candidate.bloom_area_px?.[index] ?? null,
      near_outlier_pixel: candidate.outlier_at_position[index],
      ephemeris_offset_px: candidate.ephemeris_offsets_px?.[index] ?? null,
    })),
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `${review.id}-${candidate.id}.json`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

interface MotionFieldProps {
  review: MotionReviewDataset;
  onOpenInViewer?: (
    review: MotionReviewDataset,
    frameIndex: number,
    layer: Layer,
    candidate?: MotionTrackCandidate
  ) => void;
}

function MotionField({ review, onOpenInViewer }: MotionFieldProps) {
  const [ranking, setRanking] = useState<RankingMethod>(
    review.bloom_tracks.length ? 'bloom' : 'heuristic'
  );
  const [frameIndex, setFrameIndex] = useState(0);
  const [trackIndex, setTrackIndex] = useState(0);
  const [layer, setLayer] = useState<Layer>(review.bloom_tracks.length ? 'bloom' : 'residual');
  const [playing, setPlaying] = useState(false);
  const [showTrack, setShowTrack] = useState(true);

  const ranked =
    ranking === 'bloom'
      ? review.bloom_tracks
      : ranking === 'forest'
      ? [...review.tracks].sort(
          (a, b) => (a.random_forest_rank ?? a.rank) - (b.random_forest_rank ?? b.rank)
        )
      : review.tracks;

  const candidate = ranked[trackIndex];
  const totalTracks =
    (ranking === 'bloom' ? review.comparison.bloom : review.comparison.leave_one_out)?.candidates ??
    0;
  const frame = review.frames[frameIndex] || review.frames[0];
  const detection = candidate?.epochs.indexOf(frameIndex) ?? -1;
  const position = candidate?.positions_xy[detection];
  const frameOffset = candidate?.ephemeris_offsets_px?.[detection];
  const multiDay = review.frames[0].time.slice(0, 10) !== review.frames.at(-1)?.time.slice(0, 10);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(
      () => setFrameIndex((index) => (index + 1) % review.frames.length),
      800
    );
    return () => window.clearInterval(timer);
  }, [playing, review.frames.length]);

  function selectCandidate(index: number) {
    setTrackIndex(index);
    if (ranked[index]) {
      setFrameIndex(ranked[index].epochs[0]);
    }
    setPlaying(false);
  }

  function selectRanking(mode: RankingMethod) {
    setRanking(mode);
    setTrackIndex(0);
    setFrameIndex(0);
    setPlaying(false);
    if (mode === 'bloom') setLayer('bloom');
    else if (layer === 'bloom') setLayer('residual');
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem] items-start">
      {/* Left Column: Exposure Cutout Viewer, Timeline Scrubber & Stack the Evidence */}
      <section className="space-y-4 min-w-0" aria-label="Exposure viewer">
        {/* Layer & Overlay Controls Bar */}
        <div className="p-2.5 sm:p-3 rounded-xl bg-paper-900 border-2 border-black card-tactile flex flex-wrap gap-2 items-center justify-between">
          <div className="flex flex-wrap gap-1.5 sm:gap-2 items-center">
            <button
              type="button"
              className={`${toggleBase} ${layer === 'aligned' ? activeEmerald : inactiveStyle}`}
              aria-pressed={layer === 'aligned'}
              onClick={() => setLayer('aligned')}
            >
              Aligned frame
            </button>
            <button
              type="button"
              className={`${toggleBase} ${layer === 'residual' ? activeSky : inactiveStyle}`}
              aria-pressed={layer === 'residual'}
              onClick={() => setLayer('residual')}
            >
              Difference image
            </button>
            {frame.bloom && (
              <button
                type="button"
                className={`${toggleBase} ${layer === 'bloom' ? activeAmber : inactiveStyle}`}
                aria-pressed={layer === 'bloom'}
                onClick={() => setLayer('bloom')}
              >
                BLOOM mask
              </button>
            )}
            <button
              type="button"
              className={`${toggleBase} ${showTrack ? activeEmerald : inactiveStyle} inline-flex items-center gap-1.5`}
              aria-pressed={showTrack}
              onClick={() => setShowTrack(!showTrack)}
            >
              <Crosshair size={14} />
              <span>Track overlay</span>
            </button>
          </div>

          {onOpenInViewer && (
            <button
              type="button"
              onClick={() => onOpenInViewer(review, frameIndex, layer, candidate)}
              className={`${toggleBase} bg-paper-950 text-emerald-300 hover:bg-emerald-400 hover:text-gray-950 inline-flex items-center gap-1.5`}
              title="Inspect this exposure and track in the interactive Sky Viewer"
            >
              <Compass size={14} />
              <span>Open in Sky Viewer</span>
            </button>
          )}
        </div>

        {/* Main Cutout Frame Display */}
        <div className="relative overflow-hidden rounded-2xl border-2 border-black bg-[#0a0a0c] card-tactile">
          <img
            className="block w-full h-auto max-h-[68vh] object-contain mx-auto [image-rendering:pixelated]"
            width={review.width}
            height={review.height}
            src={frame[layer] || frame.aligned}
            alt={`SPHEREx exposure at ${utc(frame.time)}, ${
              layer === 'aligned'
                ? 'aligned to the sky'
                : layer === 'bloom'
                ? 'BLOOM quality mask'
                : 'after reference subtraction'
            }`}
          />
          {showTrack && candidate && (
            <svg
              className="absolute inset-0 h-full w-full pointer-events-none text-emerald-400"
              viewBox={`0 0 ${review.width} ${review.height}`}
              preserveAspectRatio="xMidYMid meet"
              aria-hidden="true"
            >
              <polyline
                points={candidate.positions_xy.map(([x, y]) => `${x + 0.5},${y + 0.5}`).join(' ')}
                stroke="currentColor"
                strokeWidth="1.75"
                strokeDasharray="3 4"
                fill="none"
                opacity="0.85"
                vectorEffect="non-scaling-stroke"
              />
              {position && (
                <circle
                  cx={position[0] + 0.5}
                  cy={position[1] + 0.5}
                  r={Math.max(4.5, review.width / 30)}
                  fill="rgba(16, 185, 129, 0.18)"
                  stroke="#ef4444"
                  strokeWidth="2.2"
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
          )}

          {/* Top-left HUD badge */}
          <div className="absolute top-2.5 left-2.5 px-2.5 py-1 rounded-lg bg-paper-950/90 border border-paper-800 font-mono text-[10px] sm:text-[11px] text-paper-200 flex items-center gap-2 pointer-events-none">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="font-bold text-white">{review.target ?? review.id}</span>
            <span className="text-paper-400">·</span>
            <span className="text-emerald-300">{review.detector ?? 'SPHEREx'}</span>
            <span className="hidden sm:inline text-paper-400">
              · {review.width}×{review.height} px ({review.pixel_scale_arcsec}″/px)
            </span>
          </div>
        </div>

        {/* Responsive Timeline Scrubber Bar */}
        <div
          className="p-2.5 sm:p-3 rounded-xl bg-paper-900 border-2 border-black card-tactile space-y-2.5"
          aria-label="Observation times"
        >
          <div className="flex flex-wrap gap-1.5 sm:gap-2 items-center">
            <button
              type="button"
              className={`${toggleBase} ${playing ? activeEmerald : inactiveStyle} inline-flex items-center gap-1.5`}
              onClick={() => setPlaying(!playing)}
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
              <span>{playing ? 'Pause' : 'Play'}</span>
            </button>

            <div className="flex flex-wrap gap-1.5 items-center flex-1">
              {review.frames.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={index === frameIndex}
                  className={`${toggleBase} ${
                    index === frameIndex ? activeEmerald : inactiveStyle
                  } font-mono tabular-nums text-[11px] px-2.5 py-1`}
                  onClick={() => {
                    setFrameIndex(index);
                    setPlaying(false);
                  }}
                >
                  <span className="opacity-75 mr-1">E{index + 1}:</span>
                  {multiDay && `${item.time.slice(5, 10)} · `}
                  {utc(item.time)}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap justify-between items-center gap-2 pt-1.5 border-t border-paper-800 text-[11px] text-paper-400 font-mono break-all">
            {frame.archive_url ? (
              <a
                className="text-emerald-300 hover:underline inline-flex items-center gap-1"
                href={frame.archive_url}
                target="_blank"
                rel="noreferrer"
              >
                <span>
                  {frame.id} · {frame.release} FITS
                </span>
                <ExternalLink size={11} />
              </a>
            ) : (
              <span>Observation ID: {frame.id}</span>
            )}
            <span className="px-2 py-0.5 rounded bg-paper-950 border border-paper-800 text-paper-300">
              {(frame.coverage * 100).toFixed(1)}% valid pixels
            </span>
          </div>
        </div>

        {/* Stack the Evidence (Fixed vs Moving Coadd Stamps) */}
        {candidate && (
          <section
            className="rounded-2xl border-2 border-black bg-paper-900 p-4 space-y-3 card-tactile"
            aria-labelledby="motion-stack-label"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-paper-800 pb-2.5">
              <h3
                id="motion-stack-label"
                className="font-mono text-xs sm:text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2"
              >
                <Layers className="w-4 h-4 text-emerald-400" />
                <span>Stack the evidence</span>
              </h3>
              <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                {candidate.stack_contributing_exposures} exposures contribute at the center
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:gap-4">
              {(
                [
                  {
                    title: 'Fixed sky position',
                    subtitle: 'Stationary median center',
                    image: candidate.fixed_stack,
                    accent: 'border-paper-800',
                  },
                  {
                    title: 'Following the fitted track',
                    subtitle: 'Co-moving linear shift',
                    image: candidate.motion_stack,
                    accent: 'border-emerald-500/50',
                  },
                ] as const
              ).map((view) => (
                <figure
                  key={view.title}
                  className={`min-w-0 p-3 rounded-xl bg-paper-950 border-2 ${view.accent} flex flex-col items-center relative`}
                >
                  <div className="relative w-full max-w-[9.5rem] aspect-square">
                    <img
                      src={view.image}
                      width={29}
                      height={29}
                      alt={view.title}
                      className="w-full h-full rounded-lg border-2 border-black bg-black [image-rendering:pixelated]"
                    />
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                      <div
                        className={`w-6 h-6 rounded-full border ${
                          view.title.includes('Following')
                            ? 'border-emerald-400/90'
                            : 'border-dashed border-white/40'
                        }`}
                      />
                    </div>
                  </div>
                  <figcaption className="text-xs font-mono font-bold text-paper-100 mt-2 text-center">
                    {view.title}
                  </figcaption>
                  <span className="text-[10px] font-mono text-paper-400 text-center">
                    {view.subtitle}
                  </span>
                </figure>
              ))}
            </div>

            <div className="flex items-center justify-between text-[10px] font-mono text-paper-400 pt-1 border-t border-paper-800">
              <span>{ranking === 'bloom' ? 'BLOOM Mask Overlap' : 'Difference Image Coadd'}</span>
              <span className="text-emerald-300 font-bold">Fitted Linear Trajectory</span>
            </div>
          </section>
        )}
      </section>

      {/* Right Column: Ranked Candidates, Heuristic vs Random Forest & Recovery Check */}
      <aside className="space-y-4" aria-label="Candidate evidence">
        <section className="rounded-2xl border-2 border-black bg-paper-900 p-4 space-y-3.5 card-tactile">
          <div className="flex items-center justify-between border-b border-paper-800 pb-2.5">
            <h3 className="font-mono text-xs sm:text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span>Ranked candidates</span>
            </h3>
            <span className="text-paper-300 text-[11px] font-mono px-2 py-0.5 rounded bg-paper-950 border border-paper-800">
              {ranked.length}
              {totalTracks > ranked.length && ` of ${totalTracks}`}
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5" aria-label="Ranking method">
            <button
              type="button"
              className={`${toggleBase} ${ranking === 'heuristic' ? activeEmerald : inactiveStyle}`}
              aria-pressed={ranking === 'heuristic'}
              onClick={() => selectRanking('heuristic')}
            >
              Heuristic
            </button>
            {review.comparison.random_forest && (
              <button
                type="button"
                className={`${toggleBase} ${ranking === 'forest' ? activeSky : inactiveStyle}`}
                aria-pressed={ranking === 'forest'}
                onClick={() => selectRanking('forest')}
              >
                Random Forest
              </button>
            )}
            {review.comparison.bloom && (
              <button
                type="button"
                className={`${toggleBase} ${ranking === 'bloom' ? activeAmber : inactiveStyle}`}
                aria-pressed={ranking === 'bloom'}
                onClick={() => selectRanking('bloom')}
              >
                BLOOM centers
              </button>
            )}
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-paper-400">
            <span>Algorithm:</span>
            <span className="text-emerald-300 font-bold">
              {ranking === 'bloom'
                ? 'BLOOM Centroids'
                : ranking === 'forest'
                ? `${review.simulated_training_fields} Sim Fields RF`
                : 'Leave-One-Out (LOO)'}
            </span>
          </div>

          {candidate ? (
            <label className="block text-[11px] font-mono uppercase tracking-wider text-paper-400 font-bold">
              Candidate Track
              <select
                value={trackIndex}
                onChange={(event) => selectCandidate(Number(event.target.value))}
                className="mt-1.5 block w-full rounded-xl bg-paper-950 border-2 border-black px-3 py-2 text-xs font-mono text-paper-100 focus:outline-none focus:border-emerald-400 cursor-pointer"
              >
                {ranked.map((item, index) => (
                  <option key={item.id} value={index}>
                    #{ranking === 'forest' ? item.random_forest_rank : item.rank} ·{' '}
                    {item.known_match ? `Matches ${review.target ?? 'ephemeris'}` : 'Unreviewed track'}{' '}
                    · {item.epochs.length} frames
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="text-sm text-paper-400 font-mono">
              No tracks passed the current thresholds.
            </p>
          )}

          {candidate && (
            <>
              <dl className="grid grid-cols-2 gap-2.5 text-xs">
                <div className="p-2.5 rounded-xl bg-paper-950 border border-paper-800">
                  <dt className="text-[10px] font-mono text-paper-400 uppercase">Track fit RMS</dt>
                  <dd className="mt-1 font-mono font-bold text-paper-100">
                    {candidate.fit_rms_px.toFixed(2)} px
                  </dd>
                </div>
                <div className="p-2.5 rounded-xl bg-paper-950 border border-paper-800">
                  <dt className="text-[10px] font-mono text-paper-400 uppercase">Sky speed</dt>
                  <dd className="mt-1 font-mono font-bold text-emerald-300">
                    {(candidate.speed_px_per_time * review.pixel_scale_arcsec).toFixed(1)}″/h
                  </dd>
                </div>
                {candidate.max_offset_px !== null && (
                  <div className="p-2.5 rounded-xl bg-paper-950 border border-emerald-800/50">
                    <dt className="text-[10px] font-mono text-paper-400 uppercase">
                      Max ephemeris offset
                    </dt>
                    <dd className="mt-1 font-mono font-bold text-emerald-400">
                      {candidate.max_offset_px.toFixed(2)} px
                    </dd>
                  </div>
                )}
                <div className="p-2.5 rounded-xl bg-paper-950 border border-paper-800">
                  <dt className="text-[10px] font-mono text-paper-400 uppercase">Linked exposures</dt>
                  <dd className="mt-1 font-mono font-bold text-paper-100">
                    {candidate.epochs.length}/{review.frames.length}
                  </dd>
                </div>
              </dl>

              {detection >= 0 ? (
                <div className="rounded-xl bg-paper-950 border border-paper-800 p-3 text-xs font-mono space-y-1.5">
                  <p className="text-emerald-300 font-bold">
                    RA {candidate.sky_deg[detection][0].toFixed(5)}° · Dec{' '}
                    {candidate.sky_deg[detection][1].toFixed(5)}°
                  </p>
                  {candidate.snr && candidate.filter_support && (
                    <p className="text-paper-300">
                      Residual S/N {candidate.snr[detection].toFixed(1)} · filter coverage{' '}
                      {(candidate.filter_support[detection] * 100).toFixed(0)}%
                    </p>
                  )}
                  {candidate.bloom_area_px && (
                    <p className="text-amber-300">
                      BLOOM mask · {candidate.bloom_area_px[detection]} flagged pixels
                    </p>
                  )}
                  {frameOffset !== undefined && (
                    <p className="text-paper-400">
                      Offset from ephemeris {frameOffset.toFixed(2)} px
                    </p>
                  )}
                  {candidate.outlier_at_position[detection] && (
                    <p className="text-amber-300">OUTLIER flag near this detection</p>
                  )}
                </div>
              ) : (
                <p className="text-xs font-mono text-paper-400">
                  No linked detection in this frame.
                </p>
              )}

              <button
                type="button"
                className={`${toggleBase} ${inactiveStyle} w-full inline-flex items-center justify-center gap-2 py-2`}
                onClick={() => exportCandidate(review, candidate)}
              >
                <Download size={14} className="text-emerald-400" />
                <span>Export candidate JSON</span>
              </button>
            </>
          )}
        </section>

        <section className="rounded-2xl border-2 border-black bg-paper-900 p-4 space-y-3 card-tactile">
          <h3 className="font-mono text-xs sm:text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2 border-b border-paper-800 pb-2">
            <Sparkles className="w-4 h-4 text-sky-400" />
            <span>{review.has_ephemeris ? 'Recovery check' : 'Detector comparison'}</span>
          </h3>

          <dl className="space-y-2 text-xs font-mono">
            {(
              [
                { label: 'Shared median', result: review.comparison.shared_median },
                { label: 'Per-frame reference / heuristic', result: review.comparison.leave_one_out },
                { label: 'Same tracks / Random Forest', result: review.comparison.random_forest },
                {
                  label: 'Per-frame reference, OUTLIER masked',
                  result: review.comparison.outliers_masked,
                },
                { label: 'BLOOM centers', result: review.comparison.bloom },
              ] as const
            ).map(
              ({ label, result }) =>
                result && (
                  <div
                    key={label}
                    className="flex justify-between items-center gap-3 p-2 rounded-lg bg-paper-950 border border-paper-800"
                  >
                    <dt className="text-paper-300 text-[11px]">{label}</dt>
                    <dd
                      className={`font-mono text-[11px] font-bold text-right shrink-0 ${
                        result.match ? 'text-emerald-400' : 'text-paper-400'
                      }`}
                    >
                      {result.match
                        ? `#${result.match.rank} of ${result.candidates}`
                        : `${result.candidates} tracks${review.has_ephemeris ? ' · no match' : ''}`}
                    </dd>
                  </div>
                )
            )}
          </dl>

          <div className="flex items-center justify-between text-[10px] font-mono text-paper-400 pt-1 border-t border-paper-800">
            <span>{review.has_ephemeris ? 'Ephemeris Verified' : 'Catalog Free'}</span>
            <span className="text-paper-300">
              {review.retains_outliers ? 'Outliers Retained' : 'Outliers Masked'}
            </span>
          </div>

          {review.omitted_frame_checks.length > 0 && (
            <div className="p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-800/50 text-xs font-mono text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>
                Ranked first in{' '}
                {review.omitted_frame_checks.filter((check) => check.match?.rank === 1).length}/
                {review.omitted_frame_checks.length} runs with one exposure omitted.
              </span>
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

export interface MotionReviewProps {
  ra: number;
  dec: number;
  detector: number | 'all';
  onOpenInViewer?: (
    review: MotionReviewDataset,
    frameIndex: number,
    layer: Layer,
    candidate?: MotionTrackCandidate
  ) => void;
}

export function MotionReview({ ra, dec, detector, onOpenInViewer }: MotionReviewProps) {
  const [reviews, setReviews] = useState<MotionReviewDataset[] | null>(null);
  const [selected, setSelected] = useState(0);
  const [status, setStatus] = useState<'loading' | 'failed'>('loading');
  const [live, setLive] = useState<MotionReviewDataset | null>(null);
  const [mode, setMode] = useState<'live' | 'saved'>('saved');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      request.current?.abort();
      request.current = null;
    },
    []
  );

  useEffect(() => {
    let active = true;
    loadPrecomputedMotionReviews()
      .then((data) => {
        if (!active) return;
        setReviews(data);
      })
      .catch(() => {
        if (active) setStatus('failed');
      });
    return () => {
      active = false;
    };
  }, []);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setLive(null);
    setSearching(true);
    setError(null);
    const timeout = window.setTimeout(() => controller.abort('timeout'), 290000);
    try {
      const response = await fetch('/api/motion/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          ra_deg: Number(values.get('ra')),
          dec_deg: Number(values.get('dec')),
          detector: Number(values.get('detector')),
          size_arcmin: Number(values.get('size')),
          start_date: values.get('start'),
          end_date: values.get('end'),
          retain_outliers: values.get('outliers') === 'on',
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.live_search || !data?.frames?.length) {
        throw new Error(
          typeof data?.detail === 'string'
            ? data.detail
            : 'Motion service unavailable or invalid search parameters.'
        );
      }
      if (request.current === controller) setLive(data as MotionReviewDataset);
    } catch (err) {
      if (request.current !== controller) return;
      if (controller.signal.reason === 'timeout') {
        setError('The archive search timed out. Try a smaller date range or field.');
      } else if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Motion search failed.');
      }
    } finally {
      window.clearTimeout(timeout);
      if (
        request.current === controller &&
        (!controller.signal.aborted || controller.signal.reason === 'timeout')
      ) {
        request.current = null;
        setSearching(false);
      }
    }
  }

  function cancelSearch() {
    request.current?.abort();
    request.current = null;
    setSearching(false);
  }

  const review = mode === 'live' ? live : reviews?.[selected];
  const inputStyle =
    'mt-1 block w-full rounded-xl border-2 border-black bg-paper-950 px-3 py-2 font-mono text-xs text-paper-100 focus:outline-none focus:border-emerald-400';

  return (
    <main
      className="flex-1 min-h-0 overflow-y-auto bg-paper-950 pb-20 sm:pb-10"
      aria-labelledby="motion-review-title"
    >
      <div className="mx-auto max-w-7xl px-3 sm:px-6 lg:px-8 py-5 sm:py-8 space-y-5">
        {/* Top Page Header */}
        <header className="flex flex-wrap items-end justify-between gap-3 pb-4 border-b border-paper-800">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="px-2 py-0.5 rounded bg-emerald-400/15 border border-emerald-400/40 text-emerald-300 font-mono text-[10px] font-bold uppercase">
                SPHEREx Track Pipeline
              </span>
              {review?.detector && (
                <span className="px-2 py-0.5 rounded bg-sky-400/15 border border-sky-400/40 text-sky-300 font-mono text-[10px] font-bold">
                  Band {review.detector}
                </span>
              )}
            </div>
            <h1
              id="motion-review-title"
              className="mt-1.5 text-2xl sm:text-3xl font-bold font-mono tracking-tight text-white"
            >
              Motion Review
            </h1>
            {review && (
              <p className="mt-1 text-xs sm:text-sm font-mono text-paper-400">
                {review.target ?? review.id} · SPHEREx · {review.frames[0].time.slice(0, 10)}
                {review.frames.at(-1)?.time.slice(0, 10) !== review.frames[0].time.slice(0, 10) &&
                  ` to ${review.frames.at(-1)?.time.slice(0, 10)}`}
              </p>
            )}
          </div>

          {review?.source && (
            <a
              href={review.source}
              target="_blank"
              rel="noreferrer"
              className="btn-tactile-sm px-3 py-1.5 rounded-xl border-2 border-black bg-paper-900 hover:bg-paper-850 inline-flex gap-1.5 items-center font-mono text-xs text-emerald-300"
            >
              <span>NASA/IPAC IRSA observations</span>
              <ExternalLink size={13} />
            </a>
          )}
        </header>

        {/* Data Source Mode Switcher */}
        <div className="flex flex-wrap gap-2 items-center" aria-label="Data source">
          <button
            type="button"
            className={`${toggleBase} ${mode === 'saved' ? activeEmerald : inactiveStyle}`}
            aria-pressed={mode === 'saved'}
            onClick={() => setMode('saved')}
          >
            Saved observations
          </button>
          <button
            type="button"
            className={`${toggleBase} ${mode === 'live' ? activeSky : inactiveStyle}`}
            aria-pressed={mode === 'live'}
            onClick={() => setMode('live')}
          >
            Live archive search
          </button>
        </div>

        {/* Live Archive Search Form */}
        <section
          hidden={mode !== 'live'}
          aria-label="Search SPHEREx"
          className="rounded-2xl border-2 border-black bg-paper-900 p-4 sm:p-5 space-y-3.5 card-tactile"
        >
          <form className="space-y-3.5" onSubmit={search}>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono text-paper-300">
              <label>
                RA (degrees)
                <input
                  className={inputStyle}
                  name="ra"
                  type="number"
                  required
                  min="0"
                  max="359.999999999"
                  step="any"
                  defaultValue={ra}
                />
              </label>
              <label>
                Dec (degrees)
                <input
                  className={inputStyle}
                  name="dec"
                  type="number"
                  required
                  min="-89.999999999"
                  max="89.999999999"
                  step="any"
                  defaultValue={dec}
                />
              </label>
              <label>
                Detector
                <select
                  className={inputStyle}
                  name="detector"
                  defaultValue={detector === 'all' ? 6 : detector}
                >
                  {[1, 2, 3, 4, 5, 6].map((value) => (
                    <option key={value} value={value}>
                      D{value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Field size (arcmin)
                <input
                  className={inputStyle}
                  name="size"
                  type="number"
                  required
                  min="2"
                  max="30"
                  step="any"
                  defaultValue={15}
                />
              </label>
              <label>
                Start date (UTC)
                <input
                  className={inputStyle}
                  name="start"
                  type="date"
                  required
                  defaultValue="2025-12-12"
                />
              </label>
              <label>
                End date (UTC)
                <input
                  className={inputStyle}
                  name="end"
                  type="date"
                  required
                  defaultValue="2025-12-16"
                />
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                className={`${toggleBase} ${activeEmerald} disabled:opacity-50`}
                disabled={searching}
              >
                Find moving objects
              </button>
              {searching && (
                <button
                  type="button"
                  className={`${toggleBase} ${inactiveStyle}`}
                  onClick={cancelSearch}
                >
                  Cancel
                </button>
              )}
              <label className="inline-flex items-center gap-2 text-xs font-mono text-paper-300 cursor-pointer">
                <input
                  type="checkbox"
                  name="outliers"
                  defaultChecked
                  className="accent-emerald-400 rounded"
                />
                <span>Retain OUTLIER pixels</span>
              </label>
              <span className="text-[11px] text-paper-400 font-mono">
                1–7 days · 1 detector · ≥3 visits
              </span>
            </div>
          </form>

          {searching && (
            <p role="status" className="text-sm font-mono text-emerald-300">
              Searching IRSA and aligning exposures. This can take a few minutes.
            </p>
          )}
          {error && (
            <div
              role="alert"
              className="p-3 rounded-xl bg-amber-950/40 border border-amber-500/50 text-xs font-mono text-amber-200 flex flex-wrap items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                <span>{error}</span>
              </div>
              {reviews && reviews.length > 0 && (
                <button
                  type="button"
                  onClick={() => setMode('saved')}
                  className="btn-tactile-sm px-2.5 py-1 rounded-lg border-2 border-black bg-emerald-400 text-gray-950 font-mono text-[11px] font-bold cursor-pointer"
                >
                  View Saved Precomputed Cases →
                </button>
              )}
            </div>
          )}
          {live?.live_search && (
            <p role="status" className="text-sm font-mono text-paper-300">
              Aligned {live.frames.length} of{' '}
              {live.live_search.archive_visits ?? live.live_search.archive_exposures} archive
              visits.{' '}
              {live.live_search.skipped.length > 0 &&
                `${live.live_search.skipped.length} of ${live.live_search.attempted_exposures} exposure attempts were skipped.`}
            </p>
          )}
          {live?.live_search && live.live_search.skipped.length > 0 && (
            <details className="text-xs font-mono text-paper-400">
              <summary className="cursor-pointer hover:text-paper-200">Skipped exposures</summary>
              <ul className="mt-2 space-y-1">
                {live.live_search.skipped.map((item) => (
                  <li key={item.observation_id}>
                    {item.observation_id} · {item.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>

        {/* Precomputed Saved Series Selector */}
        {mode === 'saved' && !review && (
          <p
            role={status === 'failed' ? 'alert' : 'status'}
            className="text-sm font-mono text-paper-400"
          >
            {status === 'failed'
              ? 'Unavailable: the observation bundle could not be loaded.'
              : 'Loading SPHEREx observations…'}
          </p>
        )}

        {mode === 'saved' && review && (
          <div className="flex gap-2 flex-wrap" aria-label="Observation series">
            {reviews?.map((item, index) => (
              <button
                type="button"
                className={`${toggleBase} ${selected === index ? activeEmerald : inactiveStyle}`}
                aria-pressed={selected === index}
                key={item.id}
                onClick={() => setSelected(index)}
              >
                {item.target ?? item.id} · {item.detector ?? 'SPHEREx'} · {item.frames.length}{' '}
                exposures
              </button>
            ))}
          </div>
        )}

        {review && (
          <MotionField key={review.id} review={review} onOpenInViewer={onOpenInViewer} />
        )}
      </div>
    </main>
  );
}
