import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'vite';
import { createHash } from 'node:crypto';

let server, api, reviews, verification, ranking;
const savedFetch = globalThis.fetch;
before(async () => {
  process.env.VITE_DEMO_REAL_ONLY = 'true';
  server = await createServer({ configFile: false, root: new URL('..', import.meta.url).pathname, server: { middlewareMode: true }, appType: 'custom' });
  const fixtures = JSON.parse(await readFile(new URL('../public/motion/review.json', import.meta.url), 'utf8'));
  globalThis.fetch = async () => ({ ok: true, json: async () => fixtures });
  reviews = await server.ssrLoadModule('/src/services/motionReviewService.ts');
  await reviews.loadPrecomputedMotionReviews();
  api = await server.ssrLoadModule('/src/services/mockSpherexApi.ts');
  verification = await server.ssrLoadModule('/src/services/verificationService.ts');
  ranking = await server.ssrLoadModule('/src/services/mlRanking.ts');
});
after(async () => { globalThis.fetch = savedFetch; await server?.close(); });

test('real-only star presets never expose unverified PNGs or invented candidates', () => {
  for (const [id, detector] of [['barnards-star', 2], ['wise-0855', 5], ['epsilon-indi-b', 3], ['rw-aurigae', 4], ['r-draconis', 6]]) {
    assert.equal(api.getMockEpochFrames(id, detector).length, 0);
    assert.equal(api.getMockCandidates(id, detector).length, 0);
  }
  assert.deepEqual(api.getMock102BandSpectrum('3I/ATLAS'), []);
});

test('real review conversion preserves measured positions and SNR without inventing measurements', () => {
  const review = reviews.getPrecomputedReviewById('december-d6');
  assert.ok(review);
  const sparse = { ...review, bloom_tracks: [], tracks: [{ ...review.tracks[0], known_match: false, snr: null, epochs: [0, 2], positions_xy: [[10, 20], [12, 22]], sky_deg: [[166, 5], [167, 6]] }] };
  const [candidate] = reviews.convertReviewToCandidates(sparse);
  assert.equal(candidate.epochPositions.length, 2);
  assert.equal(candidate.epochPositions[0].flux, undefined);
  assert.equal(candidate.epochPositions[0].snr, undefined);
  assert.equal(candidate.confidence, 'unavailable');
  assert.equal(candidate.classification, 'unreviewed');
  assert.equal(candidate.mlScore, undefined);
  assert.equal(reviews.convertReviewToEpochFrames(sparse)[0].cosmicRayHits, undefined);
  assert.equal(ranking.rankCandidates([candidate])[0].source, 'unavailable');
  assert.equal(ranking.rankCandidates([candidate])[0].score, null);
  const actual = reviews.convertReviewToCandidates(review).find(item => item.detectionMethod === 'heuristic_leave_one_out');
  assert.equal(actual.epochPositions[0].snr, review.tracks[0].snr[0]);
  assert.equal(actual.fixedStackDataUrl, review.tracks[0].fixed_stack);
});

test('empty real verification response stays empty, including offline fallback', async () => {
  globalThis.fetch = async () => ({ ok: true, json: async () => [] });
  assert.deepEqual(await verification.fetchVerifications(), []);
  globalThis.fetch = async () => { throw new Error('offline'); };
  assert.deepEqual(await verification.fetchVerifications(), []);
});


test('real-only observation metadata never supplies invented counts, SNR or a synthetic render URL', async () => {
  const backend = await server.ssrLoadModule('/src/services/spherexBackendApi.ts');
  assert.deepEqual(backend.generateFallbackObservations({ right_ascension_deg: 250, declination_deg: 10 }), []);
  const [frame] = backend.convertObservationsToEpochFrames([{ frame_id: 'NASA-observation', observation_date: '2025-12-01', detector_array: 6, release: 'DR1', is_available: true }], 6, 250, 10);
  assert.equal(frame.imageDataUrl, undefined);
  assert.equal(frame.cosmicRayHits, undefined);
  assert.equal(frame.headerMetadata.snrEstimated, undefined);
  assert.equal(frame.headerMetadata.exposureTimeSec, undefined);
});

test('external reporting never invents photometry or successful transmissions in real-only mode', async () => {
  const external = await server.ssrLoadModule('/src/services/externalSubmissionService.ts');
  const candidate = { id: 'measured-track', ra: 1, dec: 2, snr: 12, speed_arcsec_hr: 1, fit_rms_px: 0.2, candidate_type: 'moving_object', epoch_count: 3 };
  for (const generate of [external.generateAdesXml, external.generateAdesPsv, external.generateTnsJson, external.generateVsxPayload]) assert.match(generate(candidate), /^Unavailable:/);
  await assert.rejects(external.dispatchExternalSubmission(candidate.id, 'MPC', ''), /No transmission has occurred/);
});

test('genuine offline user notes survive while legacy mock storage stays isolated', async () => {
  const values = new Map([['spherex_community_comments', JSON.stringify([{ id: 'fictional-old-note' }])]]);
  globalThis.window = { dispatchEvent() {} };
  globalThis.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  globalThis.fetch = async () => { throw new Error('offline'); };
  try {
    assert.deepEqual(await verification.fetchVerifications(), []);
    const comment = { id: 'user-1', author: 'Actual reviewer', role: 'Volunteer', timestamp: 'Just now', candidateId: '3I/ATLAS', message: 'I would like another epoch before classifying this track.', vote: 'investigate', upvotes: 1 };
    await verification.createVerification(comment);
    assert.deepEqual(await verification.fetchVerifications(), [comment]);
    assert.ok(values.has('spherex_real_community_comments'));
  } finally {
    delete globalThis.window;
    delete globalThis.localStorage;
  }
});

async function rawPreviewFixture() {
  const review = JSON.parse(await readFile(new URL('../public/motion/review.json', import.meta.url), 'utf8'))[0];
  const png = Buffer.from(review.frames[0].aligned.split(',')[1], 'base64');
  const observation = { frame_id: 'actual-fixture-frame', observation_date: '2025-12-14T11:01:45.688', detector: 3, release: 'QR2', preview_url: '/demo/previews/actual-fixture-frame.png', fits_url: '/demo/fits/actual-fixture-frame.fits', source_url: 'https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/level2/actual-fixture-frame.fits?center=331.044146,-56.782844&size=0.2', source_sha256: 'a'.repeat(64), preview_sha256: createHash('sha256').update(png).digest('hex'), image_width: 256, image_height: 144, flagged_pixel_percentage: 99 };
  const manifest = { schema_version: 1, dataset_kind: 'real_archive', targets: [{ id: 'epsilon-indi-b', name: 'Epsilon Indi B', ra_deg: 331.044146, dec_deg: -56.782844, recommended_detector: 3, coordinate_note: 'Reference center only; target identification unassessed.', observations: [observation] }] };
  return { manifest, png, field: { ra: 331.044146, dec: -56.782844, detector: 3, fovArcmin: 12 } };
}

test('packaged manifest rejects unknown fields, detectors, synthetic kinds and invalid scientific metadata', async () => {
  const { selectPackagedTarget, loadPackagedArchivePreviews } = await server.ssrLoadModule('/src/services/packagedArchivePreviews.ts');
  const { manifest, field } = await rawPreviewFixture();
  assert.equal(selectPackagedTarget(manifest, field).observations.length, 1);
  assert.equal(selectPackagedTarget(manifest, { ...field, ra: field.ra + 0.0001 }), null);
  assert.equal(selectPackagedTarget(manifest, { ...field, detector: 6 }), null);
  assert.equal(selectPackagedTarget(manifest, { ...field, fovArcmin: 3 }), null);
  assert.equal(selectPackagedTarget({ ...manifest, dataset_kind: 'mock' }, field), null);
  for (const change of [{ source_url: 'https://example.com/fake.fits' }, { release: 'SIMULATED' }, { observation_date: '2025-02-30T00:00:00Z' }, { image_height: 0 }, { preview_sha256: 'unknown' }, { preview_url: '/demo/previews/../fake.png' }]) {
    const bad = structuredClone(manifest);
    Object.assign(bad.targets[0].observations[0], change);
    assert.equal(selectPackagedTarget(bad, field), null);
  }
  let fetches = 0;
  globalThis.fetch = async () => { fetches++; throw new Error('must not request a nearby cache'); };
  assert.equal(await loadPackagedArchivePreviews({ ...field, ra: field.ra + 1 }), null);
  assert.equal(fetches, 0);
});

test('actual PNG geometry preserves valid raw frames when another packaged preview is invalid', async () => {
  const { loadPackagedArchivePreviews } = await server.ssrLoadModule('/src/services/packagedArchivePreviews.ts');
  const { manifest, png, field } = await rawPreviewFixture();
  manifest.targets[0].observations.push({ ...manifest.targets[0].observations[0], frame_id: 'bad-geometry', preview_url: '/demo/previews/bad-geometry.png', image_height: 117 });
  globalThis.fetch = async url => url === '/demo/preview-manifest.json'
    ? { ok: true, json: async () => manifest }
    : { ok: true, arrayBuffer: async () => png.buffer.slice(png.byteOffset, png.byteOffset + png.byteLength) };
  const result = await loadPackagedArchivePreviews(field);
  assert.equal(result.frames.length, 1);
  assert.equal(result.unavailableCount, 1);
  const [frame] = result.frames;
  assert.equal(frame.imageWidth, 256);
  assert.equal(frame.imageHeight, 144);
  assert.equal(frame.observationDate, '2025-12-14T11:01:45.688');
  assert.equal(frame.residualDataUrl, undefined);
  assert.equal(frame.bloomDataUrl, undefined);
  assert.equal(frame.cosmicRayHits, undefined);
  assert.equal(frame.flaggedPixelPercentage, undefined);
  assert.equal(frame.headerMetadata.flagsNonzeroPercentage, 99);
  assert.match(frame.headerMetadata.flagsNote, /informational SOURCE/);
});
