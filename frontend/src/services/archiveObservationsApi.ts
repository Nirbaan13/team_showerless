/** Federated archive metadata and explicitly selected native downloads. */
const API = (import.meta.env.VITE_BACKEND_URL as string) || '/backend';
export interface ArchiveSelection { provider: string; from: string; through: string }
export const DEFAULT_ARCHIVE: ArchiveSelection = { provider: 'irsa-spherex', from: '', through: '' };
export const isArchiveBrowse = (selection: ArchiveSelection) => selection.provider !== 'irsa-spherex' || !!selection.from || !!selection.through;
export interface ArchiveInventory {
  id: string;
  capabilities: { product_kinds: string[]; original: boolean; cutout: boolean; availability: string; time_filter: string; restrictions: string[] };
}
export interface ArchiveFailure { code: string; message: string; retryable?: boolean }
export interface ArchiveObservation {
  id: string; frame_id: string; provider: string; collection: string; native_id: string;
  product_kind: string; mission?: string; instrument?: string; original: boolean; cutout: boolean;
  analysisEligible: boolean; is_available: boolean; observation_date?: string;
  time: { start_utc?: string; end_utc?: string; quality: string; reference_epoch?: string };
  provenance: Record<string, string>;
}
export interface ProviderOutcome {
  provider: string; status: string; record_count: number; completeness: string;
  warnings: string[]; error?: ArchiveFailure; has_continuation: boolean;
}
export interface ArchiveSearchResult { observations: ArchiveObservation[]; outcomes: ProviderOutcome[]; returned_count: number }
export interface ArchiveQuery extends ArchiveSelection { ra: number; dec: number; fovArcmin: number }
export interface ArchiveDownload {
  id: string; status: string; status_url: string; events_url: string; observations: ArchiveObservation[];
  chunks: { id: string; frame_id: string; status: string; preview_status: string; image_url: string; fits_cutout_url: string; error?: ArchiveFailure }[];
  progress: { discovery_complete: boolean; total_chunks: number; ready_chunks: number; failed_chunks: number; unavailable_chunks: number };
  errors: ArchiveFailure[];
  assets: { record_id: string; status: string; asset?: { id: string; artifact_url: string; analysisEligible: boolean }; error?: ArchiveFailure }[];
}

export function observationBounds(selection: Pick<ArchiveSelection, 'from' | 'through'>) {
  const parse = (value: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Enter an observation date as YYYY-MM-DD');
    const date = new Date(`${value}T00:00:00.000Z`);
    if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) throw new Error('Enter a valid observation date');
    return date;
  };
  const start = selection.from ? parse(selection.from) : undefined;
  const end = selection.through ? parse(selection.through) : undefined;
  if (start && end && start > end) throw new Error('Observed from must be on or before Observed through');
  if (end) end.setUTCDate(end.getUTCDate() + 1);
  return { observed_after: start?.toISOString(), observed_before: end?.toISOString() };
}

/** Circumradius of the requested square TAN field, in degrees. */
export function fieldRadiusDegrees(widthArcmin: number) {
  if (!Number.isFinite(widthArcmin) || widthArcmin <= 0) throw new Error('Invalid field of view');
  return Math.atan(Math.SQRT2 * Math.tan(widthArcmin * Math.PI / (180 * 120))) * 180 / Math.PI;
}

/** Follow API links without losing the configured proxy prefix or leaving its origin. */
export function archiveResourceUrl(link: string): string {
  const base = new URL(API, window.location.origin);
  const url = new URL(link, base.origin);
  if (url.origin !== base.origin || url.username || url.password || url.hash) throw new Error('invalid_response: Invalid archive resource link');
  const prefix = base.pathname.replace(/\/$/, '');
  if (prefix && url.pathname.startsWith(`${prefix}/api/`)) return `${url.origin}${url.pathname}${url.search}`;
  if (!url.pathname.startsWith('/api/')) throw new Error('invalid_response: Expected a server API resource link');
  return `${base.origin}${prefix}${url.pathname}${url.search}`;
}

async function json<T>(link: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(archiveResourceUrl(link), { signal, headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { method: 'POST', body: JSON.stringify(body) } : {}) });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error(`invalid_response: Archive API returned non-JSON (HTTP ${response.status})`);
  const value = await response.json();
  signal?.throwIfAborted();
  if (!response.ok) throw new Error(`${value.code ?? 'archive_request_failed'}: ${value.message ?? `HTTP ${response.status}`}`);
  return value as T;
}
export async function listArchives(signal?: AbortSignal): Promise<ArchiveInventory[]> {
  const data = await json<ArchiveInventory[]>('/api/archives', signal);
  if (!Array.isArray(data) || data.some(item => typeof item.id !== 'string' || !Array.isArray(item.capabilities?.product_kinds))) throw new Error('invalid_response: Invalid archive inventory');
  return data;
}
export async function searchArchive(query: ArchiveQuery, signal?: AbortSignal): Promise<ArchiveSearchResult> {
  const bounds = observationBounds(query);
  const params = new URLSearchParams({ right_ascension_deg: String(query.ra), declination_deg: String(query.dec),
    radius_degrees: String(fieldRadiusDegrees(query.fovArcmin)), providers: query.provider, product_kinds: 'image', limit_per_provider: '100' });
  if (bounds.observed_after) params.set('observed_after', bounds.observed_after);
  if (bounds.observed_before) params.set('observed_before', bounds.observed_before);
  const result = await json<ArchiveSearchResult>(`/api/observations-search?${params}`, signal);
  if (!Array.isArray(result.observations) || !Array.isArray(result.outcomes) || result.observations.some(o => typeof o.id !== 'string' || !o.time || typeof o.analysisEligible !== 'boolean')) throw new Error('invalid_response: Invalid archive search result');
  return result;
}
function validateDownload(job: ArchiveDownload) {
  if (!job || typeof job.id !== 'string' || typeof job.status_url !== 'string' || !Array.isArray(job.chunks) || !job.progress || !['queued', 'preparing', 'completed', 'completed_with_errors', 'failed'].includes(job.status)) throw new Error('invalid_response: Invalid archive download manifest');
  archiveResourceUrl(job.status_url);
  return job;
}
export async function downloadObservations(ids: string[], signal?: AbortSignal) {
  if (!ids.length) throw new Error('Select at least one observation');
  return validateDownload(await json<ArchiveDownload>('/api/observations-download', signal, { observation_ids: ids, delivery: { mode: 'original' } }));
}
export async function getArchiveDownload(statusUrl: string, signal?: AbortSignal) {
  return validateDownload(await json<ArchiveDownload>(statusUrl, signal));
}
export async function waitForArchivePoll(signal: AbortSignal) {
  signal.throwIfAborted();
  await new Promise<void>((resolve, reject) => {
    const done = () => { signal.removeEventListener('abort', abort); resolve(); };
    const timer = setTimeout(done, 1000);
    const abort = () => { clearTimeout(timer); reject(signal.reason ?? new DOMException('Aborted', 'AbortError')); };
    signal.addEventListener('abort', abort, { once: true });
  });
}
