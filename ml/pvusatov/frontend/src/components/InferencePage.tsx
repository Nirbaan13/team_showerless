import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowLeft, Download, Play, Pause, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import {
  getInference, getInferenceDownload, inferenceModels, inferencePresets, inferenceResource, nativeDataResource, prepareRegion, startInference,
} from '../services/inferenceApi';
import type { InferenceCandidate, InferenceJob, InferenceModel, InferencePreset } from '../services/inferenceApi';
import './InferencePage.css';

const terminal = (job: InferenceJob) => job.status === 'completed' || job.status === 'failed';
const title: Record<string, string> = { 'comet-d6': '3I/ATLAS · detector 6', 'comet-d2': '3I/ATLAS · detector 2', 'vesta-d6': 'Vesta · detector 6', 'vesta-d3': 'Vesta · detector 3' };
const warningText: Record<string, string> = {
  experimental_synthetic_trained_ranking: 'The experimental ranker was trained on simulated fields. Its score is not a discovery probability.',
  passband_variation_not_corrected: 'Wavelength coverage may differ between exposures; brightness changes need further review.',
  psf_matching_not_applied: 'Point-spread functions have not been matched between exposures.',
  short_linear_arc_model: 'Tracks assume approximately constant velocity over the selected dates.',
  uncalibrated_residual_snr: 'Residual S/N is an empirical detection measure, not formal statistical significance.',
  peak_cap_reached_search_incomplete: 'The detection limit was reached. This search is incomplete; use a smaller region or stricter threshold.',
  candidate_cap_reached_search_incomplete: 'The candidate limit was reached. This list is incomplete.',
  flagged_bloom_omitted_by_candidate_limit: 'Some saturated-source evidence is outside the review limit. It has no model score.',
  no_candidates_above_thresholds: 'No tracks met the selected thresholds. This does not establish that the field contains no moving sources.',
};
const message = (error: unknown) => error instanceof Error ? error.message : 'The analysis could not complete.';
const number = (value: number | null | undefined, digits = 3) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : 'Unavailable';

export function InferencePage() {
  const [presets, setPresets] = useState<InferencePreset[]>([]);
  const [model, setModel] = useState<InferenceModel>();
  const [mode, setMode] = useState<'preset' | 'live' | 'download'>('preset');
  const [preset, setPreset] = useState('comet-d6');
  const [downloadId, setDownloadId] = useState('');
  const [job, setJob] = useState<InferenceJob>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [nativeLinks, setNativeLinks] = useState<Record<string, string>>({});
  const [activeId, setActiveId] = useState('');
  const [frameIndex, setFrameIndex] = useState(0);
  const [layer, setLayer] = useState<'image_url' | 'difference_url' | 'bloom_url'>('image_url');
  const [playing, setPlaying] = useState(false);
  const [order, setOrder] = useState<'model' | 'baseline'>('model');
  const [mask, setMask] = useState<'motion' | 'science'>('motion');
  const [minSnr, setMinSnr] = useState('4');
  const [minSpeed, setMinSpeed] = useState('3.075');
  const [maxSpeed, setMaxSpeed] = useState('369');
  const [region, setRegion] = useState({ ra: '127.69444', dec: '-39.17760', width: '3', height: '3', detector: '1', after: '2025-04-29T00:00:00Z', before: '2025-05-01T00:00:00Z' });
  const activeRequest = useRef<AbortController | null>(null);
  const result = job?.result;

  useEffect(() => {
    const controller = new AbortController();
    activeRequest.current = controller;
    Promise.all([inferencePresets(controller.signal), inferenceModels(controller.signal)])
      .then(([p, m]) => { setPresets(p.presets); setModel(m.models[0]); })
      .catch(e => { if (!controller.signal.aborted) setError(message(e)); });
    const id = new URLSearchParams(window.location.search).get('id');
    if (id) getInference(id, controller.signal).then(next => { if (!controller.signal.aborted) setJob(next); }).catch(e => { if (!controller.signal.aborted) setError(message(e)); });
    return () => { controller.abort(); activeRequest.current?.abort(); };
  }, []);

  useEffect(() => {
    if (!job || terminal(job)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      getInference(job.id, controller.signal).then(next => { if (!controller.signal.aborted) { setJob(next); setError(''); } })
        .catch(e => { if (!controller.signal.aborted) { setError(message(e)); setBusy(false); } });
    }, 1000);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [job]);

  useEffect(() => {
    if (!job?.download_id || !result) return;
    const controller = new AbortController();
    getInferenceDownload(job.download_id, controller.signal).then(download => {
      if (!controller.signal.aborted) setNativeLinks(Object.fromEntries(download.chunks.filter(c => c.status === 'ready').map(c => [c.frame_id, c.fits_cutout_url])));
    }).catch(() => { /* Original-source provenance remains available when cached bytes have been evicted. */ });
    return () => controller.abort();
  }, [job?.download_id, result]);

  useEffect(() => {
    if (!playing || !result?.frames.length) return;
    const timer = window.setInterval(() => setFrameIndex(i => (i + 1) % result.frames.length), 700);
    return () => window.clearInterval(timer);
  }, [playing, result]);

  const candidates = useMemo(() => {
    const list = [...(result?.candidates || [])];
    if (order === 'baseline') list.sort((a, b) => (a.method === 'bloom_track' ? 1 : 0) - (b.method === 'bloom_track' ? 1 : 0) || a.baseline_rank - b.baseline_rank);
    return list;
  }, [result, order]);
  const selected = candidates.find(c => c.id === activeId) || candidates[0];
  const frame = result?.frames[frameIndex] || result?.frames[0];
  const point = selected?.detections.find(p => p.frame_id === frame?.frame_id);
  const selectedPreset = presets.find(p => p.id === preset);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    activeRequest.current?.abort();
    const controller = new AbortController(); activeRequest.current = controller;
    setBusy(true); setError(''); setJob(undefined); setNativeLinks({}); setPlaying(false); setFrameIndex(0); setActiveId('');
    try {
      let source: { preset: string } | { download_id: string };
      if (mode === 'preset') source = { preset };
      else if (mode === 'download') source = { download_id: downloadId.trim() };
      else {
        const prepared = await prepareRegion({ right_ascension_deg: Number(region.ra), declination_deg: Number(region.dec), width_arcmin: Number(region.width), height_arcmin: Number(region.height), detector_array: Number(region.detector), observed_after: region.after || undefined, observed_before: region.before || undefined }, controller.signal);
        source = { download_id: prepared.id };
      }
      const accepted = await startInference(source, { min_snr: Number(minSnr), min_speed_arcsec_per_hour: Number(minSpeed), max_speed_arcsec_per_hour: Number(maxSpeed), mask_policy: mask }, controller.signal);
      if (!controller.signal.aborted) {
        setJob(accepted); window.history.replaceState(null, '', `?analysis=1&id=${encodeURIComponent(accepted.id)}`);
      }
    } catch (e) { if (!controller.signal.aborted) setError(message(e)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };

  const exportResult = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `spherex-analysis-${job?.id}.json`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const sourceUrl = (url?: string) => inferenceResource(url, job?.id || '');
  const pending = busy || (!!job && !terminal(job));
  const persistedProvenance = result?.provenance && typeof result.provenance === 'object' ? result.provenance as Record<string, unknown> : undefined;
  const persistedPresetId = typeof persistedProvenance?.preset_id === 'string' ? persistedProvenance.preset_id : undefined;
  const persistedPreset = presets.find(p => p.id === persistedPresetId);

  return <main className="inference-page">
    <header className="inference-heading">
      <a href="./" className="inference-back"><ArrowLeft size={17} /> SPHEREx Blink</a>
      <div><h1>Motion analysis</h1><p>Run the server pipeline on real SPHEREx observations, then inspect the evidence.</p></div>
      <a href="/backend/docs" target="_blank" rel="noreferrer">API documentation</a>
    </header>
    <div className="inference-layout">
      <aside className="inference-controls">
        <h2 className="inference-controls-title">New analysis inputs</h2>
        <form onSubmit={submit}>
          <label>Input data<select value={mode} onChange={e => setMode(e.target.value as typeof mode)} disabled={pending}>
            <option value="preset">Real archived examples</option><option value="live">Live IRSA region</option><option value="download">Existing download job</option>
          </select></label>
          {mode === 'preset' && <>
            <label>Observation sequence<select value={preset} onChange={e => setPreset(e.target.value)} disabled={pending || !presets.length}>
              {presets.map(p => <option key={p.id} value={p.id}>{title[p.id] || p.title}</option>)}
            </select></label>
            <p className="inference-hint">Selected observations of known objects. Detection and model ranking run when you submit; these are recovery examples, not a survey precision test.</p>
            {selectedPreset && <a href={selectedPreset.source_url} target="_blank" rel="noreferrer">Original data and provenance ↗</a>}
          </>}
          {mode === 'download' && <label>Download ID<input required value={downloadId} onChange={e => setDownloadId(e.target.value)} placeholder="ID returned by an observations endpoint" disabled={pending} /></label>}
          {mode === 'live' && <>
            <div className="inference-pair"><label>Right ascension (°)<input type="number" required min="0" max="359.999999" step="any" value={region.ra} onChange={e => setRegion({ ...region, ra: e.target.value })} /></label><label>Declination (°)<input type="number" required min="-89.999999" max="89.999999" step="any" value={region.dec} onChange={e => setRegion({ ...region, dec: e.target.value })} /></label></div>
            <div className="inference-pair"><label>Width (arcmin)<input type="number" required min="0.1" max="52" step="any" value={region.width} onChange={e => setRegion({ ...region, width: e.target.value })} /></label><label>Height (arcmin)<input type="number" required min="0.1" max="52" step="any" value={region.height} onChange={e => setRegion({ ...region, height: e.target.value })} /></label></div>
            <label>Detector<select value={region.detector} onChange={e => setRegion({ ...region, detector: e.target.value })}>{[1, 2, 3, 4, 5, 6].map(d => <option key={d} value={d}>Detector {d}</option>)}</select></label>
            <label>Observed from (UTC)<input value={region.after} onChange={e => setRegion({ ...region, after: e.target.value })} placeholder="2025-04-29T00:00:00Z" /></label>
            <label>Observed until (UTC)<input value={region.before} onChange={e => setRegion({ ...region, before: e.target.value })} placeholder="2025-05-01T00:00:00Z" /></label>
            <p className="inference-hint">Requires at least three independent usable observations. Missing coverage and limits produce an explicit response. Native FITS downloads may be large.</p>
          </>}
          <details className="inference-options"><summary>Detection settings</summary>
            <label>Minimum residual S/N<input type="number" min="0.1" step="any" value={minSnr} onChange={e => setMinSnr(e.target.value)} required /></label>
            <div className="inference-pair"><label>Min speed (arcsec/h)<input type="number" min="0.000001" step="any" value={minSpeed} onChange={e => setMinSpeed(e.target.value)} required /></label><label>Max speed (arcsec/h)<input type="number" min="0.000001" step="any" value={maxSpeed} onChange={e => setMaxSpeed(e.target.value)} required /></label></div>
            <label>Pixel-mask policy<select value={mask} onChange={e => setMask(e.target.value as typeof mask)}><option value="motion">Motion: retain flagged OUTLIER evidence</option><option value="science">Science: mask OUTLIER pixels</option></select></label>
            <p className="inference-hint">Retained outlier detections are flagged for review. Saturated measurements are never treated as valid flux.</p>
          </details>
          <button className="inference-primary" disabled={pending || !model || (mode === 'preset' && !presets.length)} type="submit">{pending ? 'Analysis running…' : 'Run analysis'}</button>
        </form>
        {model && <div className="inference-model"><strong>{model.model_id}</strong><span>Frozen {model.model_family === 'ExtraTreesClassifier' ? 'ExtraTrees' : model.model_family === 'RandomForestClassifier' ? 'Random Forest' : 'tree ensemble'} · experimental ranking</span><code title={model.sha256}>SHA-256 {model.sha256.slice(0, 16)}…</code></div>}
      </aside>
      <section className="inference-results">
        {error && <div role="alert" className="inference-error">{error}</div>}
        {job && <div className="inference-job" role="status"><strong>{job.status.replaceAll('_', ' ')}</strong><code>{job.id}</code>{!terminal(job) && <span>The accepted task continues if you leave this page.</span>}{job.download_id && <span>Download: {job.download_id}</span>}</div>}
        {job?.error && <div role="alert" className="inference-error"><strong>{job.error.code}</strong><p>{job.error.message}</p></div>}
        {error && job && !terminal(job) && <button className="inference-secondary" onClick={() => getInference(job.id).then(next => { setJob(next); setError(''); }).catch(e => setError(message(e)))}><RefreshCw size={15} /> Reconnect to task</button>}
        {!job && !busy && <div className="inference-empty"><h2>Inspect computed candidates</h2><p>Choose a real example or request a sky region. The server prepares the observations, finds tracks and loads the saved model to rank them.</p><p>Coordinates, dates, masks and real pixel evidence accompany every result. No simulated stars are substituted when an analysis fails.</p></div>}
        {result && <>
          <div className="inference-result-header"><h2>{result.candidates.length} candidate tracks · {result.frames.length} exposures</h2><button className="inference-secondary" onClick={exportResult}><Download size={15} /> Export result JSON</button></div>
          <p className="inference-result-source">Result input: <strong>{persistedPresetId ? title[persistedPresetId] || persistedPresetId : 'Retrieved native FITS observations'}</strong>
            {' · '}S/N threshold {String(result.settings.min_snr)}{' · '}Mask policy {String(result.settings.mask_policy)}
            {persistedPreset && <> · <a href={persistedPreset.source_url} target="_blank" rel="noreferrer">Result source and provenance ↗</a></>}
          </p>
          <div className="inference-review">
            <div className="inference-viewer">
              {frame && <>
                <div className="inference-layer"><label>Image layer<select value={layer} onChange={e => setLayer(e.target.value as typeof layer)}><option value="image_url">Prepared image</option><option value="difference_url">Residual evidence</option><option value="bloom_url" disabled={!frame.bloom_url}>Saturated-source mask</option></select></label><span>{frameIndex + 1} / {result.frames.length}</span></div>
                <div className="inference-image" style={{ aspectRatio: `${frame.width} / ${frame.height}` }}>
                  {sourceUrl(frame[layer]) ? <img src={sourceUrl(frame[layer])} alt={`SPHEREx observation ${frame.observation_id} at ${frame.midpoint_utc}`} /> : <div className="inference-empty">This layer is unavailable for this exposure.</div>}
                  <svg viewBox={`-0.5 -0.5 ${frame.width} ${frame.height}`} aria-label="Selected candidate trajectory">
                    {selected && <polyline points={selected.detections.map(p => `${p.x},${p.y}`).join(' ')} fill="none" stroke="#6ee7b7" strokeWidth={Math.max(0.5, frame.width / 600)} opacity="0.65" />}
                    {point && <><circle cx={point.x} cy={point.y} r={Math.max(3, frame.width / 45)} fill="none" stroke="#6ee7b7" strokeWidth={Math.max(0.8, frame.width / 400)} /><circle cx={point.x} cy={point.y} r={Math.max(0.5, frame.width / 300)} fill="#6ee7b7" /></>}
                  </svg>
                </div>
                <div className="inference-player"><button aria-label="Previous exposure" onClick={() => setFrameIndex(i => (i - 1 + result.frames.length) % result.frames.length)}><ChevronLeft size={19} /></button><button aria-label={playing ? 'Pause exposures' : 'Play exposures'} onClick={() => setPlaying(p => !p)}>{playing ? <Pause size={18} /> : <Play size={18} />}</button><button aria-label="Next exposure" onClick={() => setFrameIndex(i => (i + 1) % result.frames.length)}><ChevronRight size={19} /></button><input aria-label="Exposure index" type="range" min="0" max={result.frames.length - 1} value={frameIndex} onChange={e => setFrameIndex(Number(e.target.value))} /></div>
                <time>{frame.midpoint_utc}</time><code className="inference-frame-id">{frame.observation_id}</code>
                {nativeDataResource(nativeLinks[frame.frame_id]) && <a className="inference-native-link" href={nativeDataResource(nativeLinks[frame.frame_id])}>Download cached native FITS</a>}
                <p className="inference-hint">Usable coverage {number(frame.coverage_fraction * 100, 1)}% · OUTLIER pixels {number(frame.outlier_fraction * 100, 1)}%</p>
                {selected && <CandidateEvidence candidate={selected} frameId={frame.frame_id} sourceUrl={sourceUrl} />}
              </>}
            </div>
            <div className="inference-candidate-list"><label>Rank candidates<select value={order} onChange={e => setOrder(e.target.value as typeof order)}><option value="model">Model ranking</option><option value="baseline">Heuristic comparison</option></select></label>
              <p className="inference-hint">The score orders candidates for review. Compare several candidates with the heuristic order: the model can move a real source down the list. Scores are not discovery probabilities.</p>
              {!candidates.length && <p>No candidate met the selected detection and motion thresholds.</p>}
              {candidates.map(c => <button key={c.id} className={`inference-candidate ${selected?.id === c.id ? 'selected' : ''}`} onClick={() => setActiveId(c.id)}><strong>{c.id} <span>{c.method === 'bloom_track' ? 'Flagged source' : `Model #${c.rank}`}</span></strong><span>RA {number(c.right_ascension_deg, 6)}° · Dec {number(c.declination_deg, 6)}°</span><span>{c.detections.length} detections · {number(c.speed_arcsec_per_hour)} arcsec/h</span><span>{c.score === null ? 'No model score: saturated-source evidence' : `Model score ${number(c.score)} · heuristic #${c.baseline_rank}`}</span></button>)}
            </div>
          </div>
          <details className="inference-limitations" open><summary>Quality and interpretation</summary><ul>{result.warnings.map(w => <li key={w}>{warningText[w] || w.replaceAll('_', ' ')}</li>)}</ul></details>
          <details className="inference-limitations"><summary>Input provenance and reproducibility</summary><p>Model: {result.model.model_id}</p><code className="inference-digest">SHA-256 {result.model.sha256}</code><pre>{JSON.stringify({ settings: result.settings, provenance: result.provenance }, null, 2)}</pre></details>
        </>}
      </section>
    </div>
  </main>;
}

function CandidateEvidence({ candidate, frameId, sourceUrl }: { candidate: InferenceCandidate; frameId: string; sourceUrl: (url?: string) => string | undefined }) {
  const point = candidate.detections.find(p => p.frame_id === frameId);
  return <section className="inference-evidence"><h3>{candidate.id}</h3><dl><div><dt>Motion-fit RMS</dt><dd>{number(candidate.fit_rms_px)} px</dd></div><div><dt>Residual S/N in this exposure</dt><dd>{point ? number(point.residual_snr) : 'No linked detection'}</dd></div><div><dt>Heuristic rank</dt><dd>#{candidate.baseline_rank}</dd></div></dl>
    {!!candidate.warnings.length && <p className="inference-hint">{candidate.warnings.map(w => w.replaceAll('_', ' ')).join(' · ')}</p>}
    {point?.warnings.length ? <p className="inference-hint">This detection: {point.warnings.map(w => w.replaceAll('_', ' ')).join(' · ')}</p> : null}
    {(candidate.moving_stack_url || candidate.stationary_stack_url) && <div className="inference-stacks"><figure>{sourceUrl(candidate.stationary_stack_url) && <img src={sourceUrl(candidate.stationary_stack_url)} alt="Evidence stacked at fixed sky coordinates" />}<figcaption>Fixed-position evidence</figcaption></figure><figure>{sourceUrl(candidate.moving_stack_url) && <img src={sourceUrl(candidate.moving_stack_url)} alt="Evidence stacked along the fitted trajectory" />}<figcaption>Motion-aligned evidence</figcaption></figure></div>}
  </section>;
}
