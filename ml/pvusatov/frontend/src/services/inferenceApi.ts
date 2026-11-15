export interface InferenceModel {
  model_id: string;
  release_name?: string;
  sha256: string;
  status?: string;
  score_kind: string;
  score_description?: string;
  model_family?: 'RandomForestClassifier' | 'ExtraTreesClassifier' | 'HistGradientBoostingClassifier' | 'RankNetTreeBoost' | 'ListNetTreeBoost';
  detector_profile?: Record<string, unknown>;
  algorithm_version_proposal?: string;
}
export interface InferencePreset {
  id: string;
  title: string;
  description: string;
  source_url: string;
}
export interface InferenceDetection {
  frame_index: number;
  frame_id: string;
  midpoint_utc: string;
  x: number;
  y: number;
  right_ascension_deg: number;
  declination_deg: number;
  residual_snr: number | null;
  warnings: string[];
}
export interface InferenceCandidate {
  id: string;
  rank: number;
  method: string;
  score: number | null;
  score_kind: string;
  baseline_score: number | null;
  baseline_rank: number;
  right_ascension_deg: number;
  declination_deg: number;
  coordinate_epoch_utc: string;
  speed_arcsec_per_hour: number;
  fit_rms_px: number;
  detections: InferenceDetection[];
  warnings: string[];
  moving_stack_url?: string;
  stationary_stack_url?: string;
}
export interface InferenceFrame {
  frame_id: string;
  observation_id: string;
  midpoint_utc: string;
  width: number;
  height: number;
  image_url: string;
  difference_url: string;
  bloom_url?: string;
  coverage_fraction: number;
  outlier_fraction: number;
  access_url?: string;
  detector?: number;
  release?: string;
}
export interface InferenceResult {
  schema_version: number;
  analysis_id: string;
  model: InferenceModel;
  frames: InferenceFrame[];
  candidates: InferenceCandidate[];
  warnings: string[];
  settings: Record<string, unknown>;
  provenance: unknown;
}
export interface InferenceJob {
  id: string;
  status: string;
  download_id?: string;
  status_url: string;
  events_url: string;
  result?: InferenceResult;
  error?: { code: string; message: string; retryable?: boolean };
}
export interface InferenceOptions {
  min_snr?: number;
  min_speed_arcsec_per_hour?: number;
  max_speed_arcsec_per_hour?: number;
  mask_policy?: 'motion' | 'science';
}
export interface ArchiveRegion {
  right_ascension_deg: number;
  declination_deg: number;
  width_arcmin: number;
  height_arcmin: number;
  detector_array: number;
  observed_after?: string;
  observed_before?: string;
}
const base = ((import.meta.env.VITE_BACKEND_URL as string | undefined) || '/backend').replace(/\/$/, '');

async function json<T>(path: string, signal?: AbortSignal, body?: unknown): Promise<T> {
  const response = await fetch(base + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.message || `The API returned HTTP ${response.status}.`);
  if (data === null) throw new Error('The API returned an invalid response.');
  return data as T;
}
export const inferenceModels = (signal?: AbortSignal) => json<{ models: InferenceModel[] }>('/api/analyses/models', signal);
export const inferencePresets = (signal?: AbortSignal) => json<{ presets: InferencePreset[] }>('/api/analyses/presets', signal);
export const getInference = (id: string, signal?: AbortSignal) => json<InferenceJob>(`/api/analyses/${encodeURIComponent(id)}`, signal);
export const getInferenceDownload = (id: string, signal?: AbortSignal) =>
  json<{ chunks: { frame_id: string; status: string; fits_cutout_url: string }[] }>(`/api/downloads/${encodeURIComponent(id)}`, signal);
export const startInference = (source: { preset: string } | { download_id: string }, options: InferenceOptions, signal?: AbortSignal) =>
  json<InferenceJob>('/api/analyses/motion', signal, { ...source, options });
export const prepareRegion = (region: ArchiveRegion, signal?: AbortSignal) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(region)) if (value !== undefined && value !== '') params.set(key, String(value));
  return json<{ id: string }>(`/api/observations/default?${params}`, signal);
};
export function inferenceResource(url: string | undefined, id: string): string | undefined {
  if (!url) return undefined;
  if (url.startsWith(`/api/analyses/${encodeURIComponent(id)}/resources/`)) return base + url;
  if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(url)) return `${base}/api/analyses/${encodeURIComponent(id)}/resources/${encodeURIComponent(url)}`;
  return undefined;
}
export function nativeDataResource(url: string | undefined): string | undefined {
  return url && /^\/api\/chunks\/[A-Za-z0-9-]+$/.test(url) ? base + url : undefined;
}
