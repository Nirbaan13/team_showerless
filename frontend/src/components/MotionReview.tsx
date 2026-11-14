import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Crosshair, Download, ExternalLink, Pause, Play } from 'lucide-react';

type TrackMatch = { rank: number; exposures: number; max_offset_px: number };
type Candidate = {
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
type Frame = { id: string; time: string; coverage: number; aligned: string; residual: string; bloom?: string; archive_url?: string; release?: string };
type SearchResult = { candidates: number; match: TrackMatch | null };
type Review = {
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
  frames: Frame[];
  tracks: Candidate[];
  bloom_tracks: Candidate[];
  comparison: { shared_median: SearchResult; leave_one_out: SearchResult; outliers_masked: SearchResult; random_forest: SearchResult | null; bloom: SearchResult | null };
  live_search?: {
    archive_exposures: number;
    archive_visits: number;
    attempted_exposures: number;
    skipped: { observation_id: string; reason: string }[];
    result_limit_per_method: number;
  };
};
type Ranking = 'heuristic' | 'forest' | 'bloom';
type Layer = 'aligned' | 'residual' | 'bloom';

const toggleStyle = 'rounded-md border px-3 py-1.5 text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-300';
const inactive = 'border-paper-700 text-paper-300 hover:border-paper-400';
const active = 'border-emerald-400/60 bg-emerald-400/10 text-emerald-200';

function utc(time: string) {
  return `${time.slice(11, 19)} UTC`;
}

function exportCandidate(review: Review, candidate: Candidate) {
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
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${review.id}-${candidate.id}.json`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function MotionField({ review }: { review: Review }) {
  const [ranking, setRanking] = useState<Ranking>(review.bloom_tracks.length ? 'bloom' : 'heuristic');
  const [frameIndex, setFrameIndex] = useState(0);
  const [trackIndex, setTrackIndex] = useState(0);
  const [layer, setLayer] = useState<Layer>(review.bloom_tracks.length ? 'bloom' : 'aligned');
  const [playing, setPlaying] = useState(false);
  const [showTrack, setShowTrack] = useState(true);
  const ranked = ranking === 'bloom' ? review.bloom_tracks : ranking === 'forest'
    ? [...review.tracks].sort((a, b) => (a.random_forest_rank ?? a.rank) - (b.random_forest_rank ?? b.rank))
    : review.tracks;
  const candidate = ranked[trackIndex];
  const totalTracks = (ranking === 'bloom' ? review.comparison.bloom : review.comparison.leave_one_out)?.candidates ?? 0;
  const frame = review.frames[frameIndex];
  const detection = candidate?.epochs.indexOf(frameIndex) ?? -1;
  const position = candidate?.positions_xy[detection];
  const frameOffset = candidate?.ephemeris_offsets_px?.[detection];
  const multiDay = review.frames[0].time.slice(0, 10) !== review.frames.at(-1)?.time.slice(0, 10);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => setFrameIndex(index => (index + 1) % review.frames.length), 800);
    return () => window.clearInterval(timer);
  }, [playing, review.frames.length]);

  function selectCandidate(index: number) {
    setTrackIndex(index);
    setFrameIndex(ranked[index].epochs[0]);
    setPlaying(false);
  }

  function selectRanking(mode: Ranking) {
    setRanking(mode);
    setTrackIndex(0);
    setFrameIndex(0);
    setPlaying(false);
    if (mode === 'bloom') setLayer('bloom');
    else if (layer === 'bloom') setLayer('residual');
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem] items-start">
      <section className="space-y-3 min-w-0" aria-label="Exposure viewer">
        <div className="flex flex-wrap gap-2 items-center">
          <button type="button" className={`${toggleStyle} ${layer === 'aligned' ? active : inactive}`} aria-pressed={layer === 'aligned'} onClick={() => setLayer('aligned')}>Aligned frame</button>
          <button type="button" className={`${toggleStyle} ${layer === 'residual' ? active : inactive}`} aria-pressed={layer === 'residual'} onClick={() => setLayer('residual')}>Difference image</button>
          {frame.bloom && <button type="button" className={`${toggleStyle} ${layer === 'bloom' ? active : inactive}`} aria-pressed={layer === 'bloom'} onClick={() => setLayer('bloom')}>BLOOM mask</button>}
          <button type="button" className={`${toggleStyle} ${showTrack ? active : inactive} inline-flex items-center gap-1.5`} aria-pressed={showTrack} onClick={() => setShowTrack(!showTrack)}><Crosshair size={14} /> Track overlay</button>
        </div>
        <div className="relative overflow-hidden rounded-xl border border-paper-800 bg-[#0a0a0a]">
          <img className="block w-full" width={review.width} height={review.height} src={frame[layer]} alt={`SPHEREx exposure at ${utc(frame.time)}, ${layer === 'aligned' ? 'aligned to the sky' : layer === 'bloom' ? 'BLOOM quality mask' : 'after reference subtraction'}`} />
          {showTrack && candidate && (
            <svg className="absolute inset-0 h-full w-full pointer-events-none text-emerald-300" viewBox={`0 0 ${review.width} ${review.height}`} aria-hidden="true">
              <polyline points={candidate.positions_xy.map(([x, y]) => `${x + .5},${y + .5}`).join(' ')} stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 5" fill="none" opacity=".7" vectorEffect="non-scaling-stroke" />
              {position && <circle cx={position[0] + .5} cy={position[1] + .5} r={Math.max(4, review.width / 31)} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
            </svg>
          )}
        </div>
        <div className="flex flex-wrap gap-2 items-center" aria-label="Observation times">
          <button type="button" className={`${toggleStyle} ${playing ? active : inactive} inline-flex items-center gap-1.5`} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? 'Pause' : 'Play'}</button>
          {review.frames.map((item, index) => (
            <button key={item.id} type="button" aria-pressed={index === frameIndex} className={`${toggleStyle} ${index === frameIndex ? active : inactive} font-mono tabular-nums`} onClick={() => { setFrameIndex(index); setPlaying(false); }}>{multiDay && `${item.time.slice(5, 10)} · `}{utc(item.time)}</button>
          ))}
        </div>
        <div className="flex flex-wrap justify-between gap-2 text-xs text-paper-400 font-mono break-all">
          {frame.archive_url ? <a className="hover:underline" href={frame.archive_url} target="_blank" rel="noreferrer">{frame.id} · {frame.release} FITS</a> : <span>{frame.id}</span>}
          <span>{(frame.coverage * 100).toFixed(1)}% valid pixels</span>
        </div>
        {candidate && (
          <section className="rounded-xl border border-paper-800 bg-paper-900 p-4 space-y-3" aria-labelledby="motion-stack-label">
            <div className="flex flex-wrap justify-between gap-2">
              <h3 id="motion-stack-label" className="font-semibold">Stack the evidence</h3>
              <span className="text-xs text-paper-400">{candidate.stack_contributing_exposures} exposures contribute at the center</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {([{ title: 'Fixed sky position', image: candidate.fixed_stack }, { title: 'Following the fitted track', image: candidate.motion_stack }]).map(view => (
                <figure key={view.title} className="min-w-0">
                  <img src={view.image} width={29} height={29} alt={view.title} className="w-full max-w-[10rem] aspect-square rounded-md border border-paper-800 [image-rendering:pixelated]" />
                  <figcaption className="text-xs text-paper-300 mt-1.5">{view.title}</figcaption>
                </figure>
              ))}
            </div>
            <p className="text-xs text-paper-400">{ranking === 'bloom' ? 'Both views stack the detector’s BLOOM masks. Bright pixels show where masks overlap.' : 'Both views stack the same difference images with the same contrast.'} The moving stack follows a fitted straight line.</p>
          </section>
        )}
      </section>

      <aside className="space-y-4" aria-label="Candidate evidence">
        <section className="rounded-xl border border-paper-800 bg-paper-900 p-4 space-y-3">
          <h3 className="font-semibold">Ranked candidates <span className="text-paper-400 text-xs font-mono">{ranked.length}{totalTracks > ranked.length && ` of ${totalTracks}`}</span></h3>
          <div className="flex flex-wrap gap-1.5" aria-label="Ranking method">
            <button type="button" className={`${toggleStyle} ${ranking === 'heuristic' ? active : inactive}`} aria-pressed={ranking === 'heuristic'} onClick={() => selectRanking('heuristic')}>Heuristic</button>
            {review.comparison.random_forest && <button type="button" className={`${toggleStyle} ${ranking === 'forest' ? active : inactive}`} aria-pressed={ranking === 'forest'} onClick={() => selectRanking('forest')}>Random Forest</button>}
            {review.comparison.bloom && <button type="button" className={`${toggleStyle} ${ranking === 'bloom' ? active : inactive}`} aria-pressed={ranking === 'bloom'} onClick={() => selectRanking('bloom')}>BLOOM centers</button>}
          </div>
          <p className="text-xs text-paper-400">{ranking === 'bloom' ? 'Bright sources can leave a flagged core. This search links the centers of those flagged regions.' : ranking === 'forest' ? `Reranks the same residual tracks using a model trained on ${review.simulated_training_fields} simulated fields.` : 'Rank favors tracks with more detections, stronger residuals, and a tighter fit.'}</p>
          {candidate ? (
            <label className="block text-xs text-paper-400">
              Candidate
              <select value={trackIndex} onChange={event => selectCandidate(Number(event.target.value))} className="mt-1.5 block w-full rounded-md bg-paper-950 border border-paper-700 px-2.5 py-2 text-sm text-paper-100">
                {ranked.map((item, index) => <option key={item.id} value={index}>#{ranking === 'forest' ? item.random_forest_rank : item.rank} · {item.known_match ? `Matches ${review.target ?? 'ephemeris'}` : 'Unreviewed track'} · {item.epochs.length} frames</option>)}
              </select>
            </label>
          ) : <p className="text-sm text-paper-400">No tracks passed the current thresholds.</p>}
          {candidate && <>
            <dl className="grid grid-cols-2 gap-y-3 gap-x-2 text-xs">
              <div><dt className="text-paper-400">Track fit RMS</dt><dd className="mt-1 font-mono">{candidate.fit_rms_px.toFixed(2)} px</dd></div>
              <div><dt className="text-paper-400">Sky speed</dt><dd className="mt-1 font-mono">{(candidate.speed_px_per_time * review.pixel_scale_arcsec).toFixed(1)}″/h</dd></div>
              {candidate.max_offset_px !== null && <div><dt className="text-paper-400">Max ephemeris offset</dt><dd className="mt-1 font-mono">{candidate.max_offset_px.toFixed(2)} px</dd></div>}
              <div><dt className="text-paper-400">Linked exposures</dt><dd className="mt-1 font-mono">{candidate.epochs.length}/{review.frames.length}</dd></div>
            </dl>
            {detection >= 0 ? (
              <div className="border-t border-paper-800 pt-3 text-xs space-y-1.5">
                <p className="font-mono text-paper-300">RA {candidate.sky_deg[detection][0].toFixed(5)}° · Dec {candidate.sky_deg[detection][1].toFixed(5)}°</p>
                {candidate.snr && candidate.filter_support && <p className="text-paper-400">Residual S/N {candidate.snr[detection].toFixed(1)} · filter coverage {(candidate.filter_support[detection] * 100).toFixed(0)}%</p>}
                {candidate.bloom_area_px && <p className="text-amber-300">BLOOM mask · {candidate.bloom_area_px[detection]} flagged pixels</p>}
                {frameOffset !== undefined && <p className="text-paper-400">Offset from ephemeris {frameOffset.toFixed(2)} px</p>}
                {candidate.outlier_at_position[detection] && <p className="text-amber-300">OUTLIER flag near this detection</p>}
              </div>
            ) : <p className="text-xs text-paper-400">No linked detection in this frame.</p>}
            <button type="button" className={`${toggleStyle} ${inactive} inline-flex items-center gap-2`} onClick={() => exportCandidate(review, candidate)}><Download size={14} /> Export candidate JSON</button>
          </>}
        </section>
        <section className="rounded-xl border border-paper-800 bg-paper-900 p-4 space-y-3">
          <h3 className="font-semibold">{review.has_ephemeris ? 'Recovery check' : 'Detector comparison'}</h3>
          <dl className="space-y-2 text-xs">
            {([
              { label: 'Shared median', result: review.comparison.shared_median },
              { label: 'Per-frame reference / heuristic', result: review.comparison.leave_one_out },
              { label: 'Same tracks / Random Forest', result: review.comparison.random_forest },
              { label: 'Per-frame reference, OUTLIER masked', result: review.comparison.outliers_masked },
              { label: 'BLOOM centers', result: review.comparison.bloom },
            ]).map(({ label, result }) => result && (
              <div key={label} className="flex justify-between gap-3">
                <dt className="text-paper-300">{label}</dt>
                <dd className="font-mono text-right shrink-0">{result.match ? `#${result.match.rank} of ${result.candidates}` : `${result.candidates} tracks${review.has_ephemeris ? ' · no match' : ''}`}</dd>
              </div>
            ))}
          </dl>
          <p className="text-xs leading-relaxed text-paper-400">{review.has_ephemeris ? 'Published positions label matches after ranking.' : 'Ephemeris unavailable for this series.'} {review.retains_outliers ? 'OUTLIER pixels were retained in this run.' : 'OUTLIER pixels were masked in this run.'}</p>
          {review.omitted_frame_checks.length > 0 && <p className="text-xs leading-relaxed text-paper-300">
            Ranked first in {review.omitted_frame_checks.filter(check => check.match?.rank === 1).length}/{review.omitted_frame_checks.length} runs with one exposure omitted.
          </p>}
        </section>
      </aside>
    </div>
  );
}

export function MotionReview({ ra, dec, detector }: { ra: number; dec: number; detector: number | 'all' }) {
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [selected, setSelected] = useState(0);
  const [status, setStatus] = useState<'loading' | 'failed'>('loading');
  const [live, setLive] = useState<Review | null>(null);
  const [mode, setMode] = useState<'live' | 'saved'>('saved');
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => {
    request.current?.abort();
    request.current = null;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}motion/review.json`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Review[]>;
      })
      .then(data => {
        if (!Array.isArray(data) || data.length === 0 || data.some(review => !review.frames?.length)) {
          throw new Error('No observations in dataset');
        }
        setReviews(data);
      })
      .catch(() => { if (!controller.signal.aborted) setStatus('failed'); });
    return () => controller.abort();
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
          ra_deg: Number(values.get('ra')), dec_deg: Number(values.get('dec')),
          detector: Number(values.get('detector')), size_arcmin: Number(values.get('size')),
          start_date: values.get('start'), end_date: values.get('end'),
          retain_outliers: values.get('outliers') === 'on',
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.live_search || !data?.frames?.length) {
        throw new Error(typeof data?.detail === 'string' ? data.detail : 'Motion service unavailable or invalid search parameters.');
      }
      if (request.current === controller) setLive(data as Review);
    } catch (err) {
      if (request.current !== controller) return;
      if (controller.signal.reason === 'timeout') setError('The archive search timed out. Try a smaller date range or field.');
      else if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Motion search failed.');
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller && (!controller.signal.aborted || controller.signal.reason === 'timeout')) {
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
  const inputStyle = 'mt-1 block w-full rounded-md border border-paper-700 bg-paper-950 p-2 text-paper-100';
  return (
    <main className="flex-1 min-h-0 overflow-y-auto bg-paper-950" aria-labelledby="motion-review-title">
      <div className="mx-auto max-w-7xl px-4 sm:px-8 py-6 sm:py-8 space-y-5">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 id="motion-review-title" className="text-3xl sm:text-4xl font-semibold tracking-tight">Motion Review</h1>
            {review && <p className="mt-1.5 text-sm text-paper-400">{review.target ?? review.id} · SPHEREx · {review.frames[0].time.slice(0, 10)}{review.frames.at(-1)?.time.slice(0, 10) !== review.frames[0].time.slice(0, 10) && ` to ${review.frames.at(-1)?.time.slice(0, 10)}`}</p>}
          </div>
          {review?.source && <a href={review.source} target="_blank" rel="noreferrer" className="inline-flex gap-1.5 items-center text-xs text-emerald-200 hover:underline">NASA/IPAC IRSA observations <ExternalLink size={13} /></a>}
        </header>
        <div className="flex flex-wrap gap-2" aria-label="Data source">
          <button type="button" className={`${toggleStyle} ${mode === 'live' ? active : inactive}`} aria-pressed={mode === 'live'} onClick={() => setMode('live')}>Live archive search</button>
          <button type="button" className={`${toggleStyle} ${mode === 'saved' ? active : inactive}`} aria-pressed={mode === 'saved'} onClick={() => setMode('saved')}>Saved observations</button>
        </div>
        <section hidden={mode !== 'live'} aria-label="Search SPHEREx" className="rounded-xl border border-paper-800 p-4 space-y-3">
          <form className="space-y-3" onSubmit={search}>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs text-paper-300">
              <label>RA (degrees)<input className={inputStyle} name="ra" type="number" required min="0" max="359.999999999" step="any" defaultValue={ra} /></label>
              <label>Dec (degrees)<input className={inputStyle} name="dec" type="number" required min="-89.999999999" max="89.999999999" step="any" defaultValue={dec} /></label>
              <label>Detector<select className={inputStyle} name="detector" defaultValue={detector === 'all' ? 6 : detector}>{[1, 2, 3, 4, 5, 6].map(value => <option key={value} value={value}>D{value}</option>)}</select></label>
              <label>Field size (arcmin)<input className={inputStyle} name="size" type="number" required min="2" max="30" step="any" defaultValue={15} /></label>
              <label>Start date (UTC)<input className={inputStyle} name="start" type="date" required /></label>
              <label>End date (UTC)<input className={inputStyle} name="end" type="date" required /></label>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button className={`${toggleStyle} ${active} disabled:opacity-50`} disabled={searching}>Find moving objects</button>
              {searching && <button type="button" className={`${toggleStyle} ${inactive}`} onClick={cancelSearch}>Cancel</button>}
              <label className="inline-flex items-center gap-2 text-xs text-paper-300"><input type="checkbox" name="outliers" defaultChecked /> Retain OUTLIER pixels</label>
              <p className="text-xs text-paper-400">Search up to 7 days using one detector. Candidates need detections in at least 3 visits.</p>
            </div>
          </form>
          {searching && <p role="status" className="text-sm text-paper-300">Searching IRSA and aligning exposures. This can take a few minutes.</p>}
          {error && <p role="alert" className="text-sm text-amber-300">{error}</p>}
          {live?.live_search && <p role="status" className="text-sm text-paper-300">Aligned {live.frames.length} of {live.live_search.archive_visits ?? live.live_search.archive_exposures} archive visits. {live.live_search.skipped.length > 0 && `${live.live_search.skipped.length} of ${live.live_search.attempted_exposures} exposure attempts were skipped.`}</p>}
          {live?.live_search && live.live_search.skipped.length > 0 && <details className="text-xs text-paper-400">
            <summary>Skipped exposures</summary>
            <ul className="mt-2 space-y-1">{live.live_search.skipped.map(item => <li key={item.observation_id}>{item.observation_id} · {item.reason}</li>)}</ul>
          </details>}
        </section>
        {mode === 'saved' && !review && <p role={status === 'failed' ? 'alert' : 'status'} className="text-sm text-paper-400">{status === 'failed' ? 'Unavailable: the observation bundle could not be loaded.' : 'Loading SPHEREx observations…'}</p>}
        {mode === 'saved' && review && (
          <div className="flex gap-2 flex-wrap" aria-label="Observation series">
            {reviews?.map((item, index) => <button type="button" className={`${toggleStyle} ${selected === index ? active : inactive}`} aria-pressed={selected === index} key={item.id} onClick={() => setSelected(index)}>{item.target ?? item.id} · {item.detector ?? 'SPHEREx'} · {item.frames.length} exposures</button>)}
          </div>
        )}
        {review && <MotionField key={review.id} review={review} />}
      </div>
    </main>
  );
}
