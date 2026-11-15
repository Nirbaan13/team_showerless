import { DEMO_REAL_ONLY } from '../lib/demoMode';
import { NASA_TEST_PRESETS } from './mockSpherexApi';
import type { DetectorArrayId, SpherexEpochFrame } from '../types/spherex';

type Observation = {
  frame_id: string;
  observation_date: string;
  detector: DetectorArrayId;
  release: 'DR1' | 'QR2' | 'QR3';
  preview_url: string;
  fits_url: string;
  source_url: string;
  source_sha256: string;
  preview_sha256: string;
  image_width: number;
  image_height: number;
  flagged_pixel_percentage?: number;
  proper_motion_note?: string;
};
type Target = {
  id: string; name: string; ra_deg: number; dec_deg: number;
  recommended_detector: DetectorArrayId;
  coordinate_note: string;
  proper_motion_note?: string;
  observations: Observation[];
};
type Field = { ra: number; dec: number; detector: DetectorArrayId; fovArcmin: number };
const RANGES: Record<DetectorArrayId, [number, number]> = { 1: [0.75, 1.11], 2: [1.11, 1.64], 3: [1.64, 2.42], 4: [2.42, 3.82], 5: [3.82, 4.42], 6: [4.42, 5.0] };
const SHA256 = /^[a-f0-9]{64}$/i;
const STELLAR_PRESETS = new Set(['barnards-star', 'wise-0855', 'epsilon-indi-b', 'rw-aurigae', 'r-draconis']);
const sameCoordinate = (a: number, b: number) => Number.isFinite(a) && Math.abs(a - b) <= 0.00001;

/** Only the five published stellar fields are eligible; proximity is not a cache match. */
export function matchingPackagedPreset(ra: number, dec: number, detector?: number) {
  return NASA_TEST_PRESETS.find(preset => STELLAR_PRESETS.has(preset.id) && sameCoordinate(ra, preset.raDeg)
    && sameCoordinate(dec, preset.decDeg) && (detector === undefined || detector === preset.recommendedArray)) ?? null;
}

function localArtifact(value: unknown, prefix: string, extension: string): value is string {
  if (typeof value !== 'string' || !value.startsWith(prefix)) return false;
  try {
    const url = new URL(value, 'https://demo.invalid');
    return url.origin === 'https://demo.invalid' && !url.search && !url.hash && url.pathname.endsWith(extension)
      && value.split('/').every(part => !['.', '..'].includes(decodeURIComponent(part)));
  } catch { return false; }
}

function validObservationDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?$/.test(value)) return false;
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  return Number.isFinite(date.valueOf()) && date.toISOString().slice(0, 19) === value.slice(0, 19);
}

function validObservation(value: unknown): value is Observation {
  if (!value || typeof value !== 'object') return false;
  const obs = value as Observation;
  let source: URL;
  try { source = new URL(obs.source_url); } catch { return false; }
  return typeof obs.frame_id === 'string' && obs.frame_id.length > 0
    && validObservationDate(obs.observation_date)
    && (obs.proper_motion_note === undefined || typeof obs.proper_motion_note === 'string')
    && Number.isInteger(obs.detector) && obs.detector >= 1 && obs.detector <= 6
    && ['DR1', 'QR2', 'QR3'].includes(obs.release)
    && localArtifact(obs.preview_url, '/demo/previews/', '.png') && localArtifact(obs.fits_url, '/demo/', '.fits')
    && source.protocol === 'https:' && source.hostname === 'irsa.ipac.caltech.edu' && !source.username && !source.password && source.pathname.includes('/spherex/') && source.pathname.endsWith('.fits')
    && typeof obs.source_sha256 === 'string' && SHA256.test(obs.source_sha256) && typeof obs.preview_sha256 === 'string' && SHA256.test(obs.preview_sha256)
    && Number.isInteger(obs.image_width) && obs.image_width > 0 && Number.isInteger(obs.image_height) && obs.image_height > 0
    && (obs.flagged_pixel_percentage === undefined || Number.isFinite(obs.flagged_pixel_percentage) && obs.flagged_pixel_percentage >= 0 && obs.flagged_pixel_percentage <= 100);
}

export function selectPackagedTarget(manifest: unknown, field: Field): Target | null {
  const preset = matchingPackagedPreset(field.ra, field.dec, field.detector);
  if (!Number.isFinite(field.fovArcmin) || Math.abs(field.fovArcmin - 12) > 0.000001 || !preset || !manifest || typeof manifest !== 'object') return null;
  const data = manifest as { schema_version?: number; dataset_kind?: string; targets?: Target[] };
  if (data.schema_version !== 1 || data.dataset_kind !== 'real_archive' || !Array.isArray(data.targets)) return null;
  const target = data.targets.find(item => item?.id === preset.id);
  if (!target || typeof target.name !== 'string' || !target.name || typeof target.coordinate_note !== 'string'
    || target.proper_motion_note !== undefined && typeof target.proper_motion_note !== 'string'
    || !sameCoordinate(target.ra_deg, preset.raDeg) || !sameCoordinate(target.dec_deg, preset.decDeg)
    || target.recommended_detector !== field.detector || !Array.isArray(target.observations) || !target.observations.length
    || !target.observations.every(validObservation)) return null;
  const observations = target.observations.filter(obs => obs.detector === field.detector);
  if (!observations.length || new Set(observations.map(obs => obs.frame_id)).size !== observations.length) return null;
  return { ...target, observations };
}

/** Read actual PNG geometry; manifest dimensions alone are not image evidence. */
function pngMatchesGeometry(bytes: ArrayBuffer, observation: Observation): boolean {
  if (bytes.byteLength < 24) return false;
  const header = new Uint8Array(bytes, 0, 24);
  if (![137, 80, 78, 71, 13, 10, 26, 10].every((byte, i) => header[i] === byte)
    || String.fromCharCode(...header.slice(12, 16)) !== 'IHDR') return false;
  const view = new DataView(bytes);
  return view.getUint32(16) === observation.image_width && view.getUint32(20) === observation.image_height;
}

export async function loadPackagedArchivePreviews(field: Field, signal?: AbortSignal): Promise<{ name: string; frames: SpherexEpochFrame[]; unavailableCount: number; coordinateNote: string } | null> {
  if (!DEMO_REAL_ONLY || !Number.isFinite(field.fovArcmin) || Math.abs(field.fovArcmin - 12) > 0.000001 || !matchingPackagedPreset(field.ra, field.dec, field.detector)) return null;
  try {
    const response = await fetch('/demo/preview-manifest.json', { signal, headers: { Accept: 'application/json' } });
    if (!response.ok) return null;
    const target = selectPackagedTarget(await response.json(), field);
    if (!target) return null;
    const coordinateNote = [...new Set([target.coordinate_note, target.proper_motion_note].filter(Boolean))].join(' ');
    const frames = await Promise.all(target.observations.map(async (obs): Promise<SpherexEpochFrame | null> => {
      try {
        const preview = await fetch(obs.preview_url, { signal });
        if (!preview.ok) return null;
        const bytes = await preview.arrayBuffer();
        if (!pngMatchesGeometry(bytes, obs)) return null;
        // Web Crypto is available on HTTPS/localhost. Plain HTTP deployments still
        // check actual PNG geometry and retain the declared digests as provenance.
        if (globalThis.crypto?.subtle) {
          const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
          const actual = Array.from(hash, value => value.toString(16).padStart(2, '0')).join('');
          if (actual !== obs.preview_sha256.toLowerCase()) return null;
        }
        return {
          frameId: obs.frame_id, epochIndex: 0, observationDate: obs.observation_date, detectorArray: obs.detector,
          wavelengthMinUm: RANGES[obs.detector][0], wavelengthMaxUm: RANGES[obs.detector][1],
          isAvailable: true, imageDataUrl: obs.preview_url, imageWidth: obs.image_width, imageHeight: obs.image_height,
          archiveUrl: obs.source_url, release: obs.release,
          headerMetadata: { flagsNonzeroPercentage: obs.flagged_pixel_percentage, flagsNote: 'Includes informational SOURCE bits; this is not a bad-pixel percentage.' },
          packagedArchive: { fitsUrl: obs.fits_url, sourceSha256: obs.source_sha256, previewSha256: obs.preview_sha256, coordinateNote: [...new Set([coordinateNote, obs.proper_motion_note].filter(Boolean))].join(' ') },
        };
      } catch { return null; }
    }));
    signal?.throwIfAborted();
    const available = frames.filter((frame): frame is SpherexEpochFrame => frame !== null)
      .sort((a, b) => Date.parse(a.observationDate.endsWith('Z') ? a.observationDate : `${a.observationDate}Z`) - Date.parse(b.observationDate.endsWith('Z') ? b.observationDate : `${b.observationDate}Z`)).map((frame, epochIndex) => ({ ...frame, epochIndex }));
    return available.length ? { name: target.name, frames: available, unavailableCount: frames.length - available.length, coordinateNote } : null;
  } catch (error) {
    if (signal?.aborted) throw error;
    return null;
  }
}
