import { waitForArchivePoll, type ArchiveDownload, type ArchiveObservation, type ArchiveQuery } from './archiveObservationsApi';
import type { MotionReviewDataset } from './motionReviewService';

export interface HistoricalGrid {
  kind: 'sky'; width: number; height: number; ra_degrees: number; dec_degrees: number; pixel_scale_arcsec: 2.75;
}
export function historicalGrid(query: ArchiveQuery): HistoricalGrid {
  if (!Number.isFinite(query.fovArcmin) || query.fovArcmin <= 0 || !Number.isFinite(query.ra) || query.ra < 0 || query.ra >= 360 ||
      !Number.isFinite(query.dec) || query.dec <= -90 || query.dec >= 90) throw new Error('Invalid historical sky field');
  // ArchiveQuery uses the viewer's square field width, never the search circle's radius.
  const width = Math.min(512, Math.max(1, Math.ceil(query.fovArcmin * 60 / 2.75)));
  return { kind: 'sky', width, height: width, ra_degrees: query.ra, dec_degrees: query.dec, pixel_scale_arcsec: 2.75 };
}

export function historicalSelection(records: ArchiveObservation[], selectedIds: string[], job: ArchiveDownload | null): { assetIds: string[]; reason: string } {
  const rejected = (reason: string) => ({ assetIds: [], reason });
  if (selectedIds.length < 3) return rejected('Select at least three distinct qualified unWISE neo11 W2 epochs, then download them.');
  const selected = selectedIds.map(id => records.find(record => record.id === id));
  const tiles = new Set<string>(), epochs = new Set<string>();
  for (const record of selected) {
    const native = record?.native;
    const start = Date.parse(record?.time.start_utc ?? ''), end = Date.parse(record?.time.end_utc ?? '');
    if (!record || record.provider !== 'unwise-neo11' || record.collection !== 'neo11' || !record.analysisEligible || !record.is_available ||
        record.product_kind !== 'image' || !record.original || native?.release !== 'neo11' || native.band !== '2' || native.FILTER !== 'W2' ||
        native.pixel_scale_arcsec !== '2.75' || !/^\d{4}[pm]\d{3}$/.test(native.coadd_id ?? '') || !/^\d{1,3}$/.test(native.epoch ?? '') ||
        !Number.isFinite(start) || !Number.isFinite(end) || end < start || record.time.quality !== 'verified') {
      return rejected('Historical motion requires qualified unWISE neo11 W2 image records with verified actual observation times. CADC and SPHEREx are unsupported here.');
    }
    tiles.add(native.coadd_id); epochs.add(String(Number(native.epoch)));
  }
  if (tiles.size !== 1 || epochs.size !== selectedIds.length || new Set(selectedIds).size !== selectedIds.length) {
    return rejected('Select distinct epochs of the same unWISE neo11 W2 tile.');
  }
  if (!job || job.status !== 'completed' || !job.progress.discovery_complete || job.progress.failed_chunks || job.progress.unavailable_chunks || job.errors?.length) {
    return rejected('Complete the selected observations download, including associated products, before preparing motion.');
  }
  const assetIds: string[] = [];
  for (const id of selectedIds) {
    const science = job.assets?.filter(outcome => outcome.record_id === id && outcome.provenance?.asset_role === '#this' &&
      outcome.status === 'ready' && outcome.asset?.id);
    if (science?.length !== 1) return rejected('Every selected observation needs one completed, qualified science asset from the download job.');
    assetIds.push(science[0].asset!.id);
    for (const role of ['#inverse-variance', '#coverage', '#contributors']) {
      const associated = job.assets?.filter(outcome => outcome.record_id === id && outcome.provenance?.asset_role === role &&
        outcome.status === 'ready' && outcome.asset?.id);
      if (associated?.length !== 1) return rejected(`Every selected observation needs one completed ${role.slice(1)} product before preparation can check qualification.`);
    }
  }
  if (new Set(assetIds).size !== selectedIds.length) return rejected('Downloaded science asset identities must be distinct.');
  return { assetIds, reason: '' };
}

/** Historical operations always use the same-origin Scala proxy, including server polling links. */
function resource(link: string) {
  const url = new URL(link, window.location.origin);
  if (url.origin !== window.location.origin || url.username || url.password || url.hash) throw new Error('Invalid historical API resource link');
  const path = url.pathname.startsWith('/backend/api/') ? url.pathname : url.pathname.startsWith('/api/') ? `/backend${url.pathname}` : '';
  if (!path) throw new Error('Invalid historical API resource path');
  return `${path}${url.search}`;
}
async function json<T>(link: string, signal: AbortSignal, body?: unknown): Promise<T> {
  signal.throwIfAborted();
  const response = await fetch(resource(link), { signal, headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { method: 'POST', body: JSON.stringify(body) } : {}) });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error(`Historical API returned non-JSON (HTTP ${response.status})`);
  const data = await response.json(); signal.throwIfAborted();
  if (!response.ok) throw new Error(`${data.code ?? 'historical_request_failed'}: ${data.message ?? (typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`)}`);
  return data as T;
}
interface Preparation { id: string; status: string; status_url: string; error?: { code: string; message: string } }
function preparation(value: Preparation) {
  if (!value || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(value.id) ||
      !['queued', 'preparing', 'running', 'completed', 'failed'].includes(value.status) || typeof value.status_url !== 'string') {
    throw new Error('Invalid image preparation response');
  }
  resource(value.status_url);
  return value;
}
export async function runHistoricalMotion(assetIds: string[], grid: HistoricalGrid, signal: AbortSignal,
  progress: (message: string) => void): Promise<MotionReviewDataset> {
  progress('Preparing downloaded unWISE W2 observations on the common sky grid…');
  let job = preparation(await json<Preparation>('/api/image-unifications', signal, {
    inputs: assetIds.map(id => ({ kind: 'archive_asset', id })), grid, options: { normalization: 'none', mask_policy: 'science' },
  }));
  const id = job.id;
  while (!['completed', 'failed'].includes(job.status)) {
    progress(`Image preparation: ${job.status}. Associated variance and coverage are resolved by the server.`);
    await waitForArchivePoll(signal);
    job = preparation(await json<Preparation>(job.status_url, signal));
    if (job.id !== id) throw new Error('Image preparation identity changed');
  }
  if (job.status === 'failed') throw new Error(`${job.error?.code ?? 'preparation_failed'}: ${job.error?.message ?? 'Historical image preparation failed'}`);
  progress('Finding stellar proper motion with Ivan’s heuristic review (0.1–30 arcsec/year)…');
  const review = await json<MotionReviewDataset>('/api/motion/search', signal, { unification_id: id, profile: 'stellar_proper_motion' });
  if (review?.id !== id || review.unification_id !== id || review.profile !== 'stellar_proper_motion' || review.detector !== null ||
      review.pixel_scale_arcsec !== 2.75 || !Array.isArray(review.frames) || review.frames.length < 3 ||
      !Array.isArray(review.tracks) || !Array.isArray(review.bloom_tracks) || !review.comparison ||
      !review.comparison.shared_median || !review.comparison.leave_one_out || review.comparison.outliers_masked !== null ||
      !Array.isArray(review.omitted_frame_checks) || review.frames.some(frame => !Number.isFinite(Date.parse(frame.time)) ||
        !frame.aligned?.startsWith('data:image/png;base64,') || !frame.residual?.startsWith('data:image/png;base64,')) ||
      review.tracks.some(track => track.outlier_at_position !== null || !Number.isFinite(track.proper_motion_arcsec_per_year))) {
    throw new Error('Invalid historical motion review response');
  }
  signal.throwIfAborted();
  return review;
}
