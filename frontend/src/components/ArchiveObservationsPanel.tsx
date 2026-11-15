import { useState } from 'react';
import type { useArchiveObservations } from '../hooks/useArchiveObservations';
import { archiveResourceUrl, type ArchiveObservation } from '../services/archiveObservationsApi';

type ArchiveState = ReturnType<typeof useArchiveObservations>;
const timestamp = (record: ArchiveObservation) => record.observation_date ?? record.time.start_utc;
function link(value?: string) { try { return value ? archiveResourceUrl(value) : undefined; } catch { return undefined; } }
function Preview({ url, id }: { url: string; id: string }) {
  const [failed, setFailed] = useState(false);
  return failed ? <p role="alert">Image preview could not be loaded. FITS availability does not establish preview availability.</p>
    : <img src={url} alt={`Archive preview ${id}`} onError={() => setFailed(true)} className="max-h-96 max-w-full object-contain" />;
}
export function ArchiveObservationsPanel({ archive }: { archive: ArchiveState }) {
  const { query, result, searching, selectedIds, downloading, job, error } = archive;
  return <section aria-label="Archive observations" className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 text-sm bg-paper-950 text-paper-200">
    <h2 className="text-lg font-bold">Archive observations</h2>
    {query ? <p className="font-mono text-xs">{query.provider} · {query.ra.toFixed(6)}°, {query.dec.toFixed(6)}° · square field {query.fovArcmin}′<br />
      Observed: {query.from || 'unbounded'} through {query.through || 'unbounded'} (UTC; end date inclusive)</p>
      : <p>Choose an archive and observation dates, then press Update Field.</p>}
    {searching && <p role="status">Searching archive metadata. No image files are being downloaded.</p>}
    {error && <p role="alert" className="text-red-300 break-words">{error}</p>}
    {result && <>
      <div aria-label="Archive provider outcomes" className="space-y-2">
        {result.outcomes.map(outcome => <div key={outcome.provider} role="status" className="p-2 border border-paper-700 rounded">
          <strong>{outcome.provider}: {outcome.status}</strong> · {outcome.record_count} records · {outcome.completeness}
          {outcome.completeness !== 'complete' && <p className="text-amber-300">Results are incomplete ({outcome.completeness}). Narrow the region or period; more observations may exist.</p>}
          {outcome.has_continuation && <p>Additional results are available from this provider.</p>}
          {outcome.error && <p className="text-red-300">{outcome.error.code}: {outcome.error.message}</p>}
          {outcome.warnings.map((warning, i) => <p key={i} className="text-amber-300">{warning}</p>)}
        </div>)}
      </div>
      <p>{result.returned_count} observations returned. Discovery does not mean images have been downloaded.</p>
      {!result.observations.length && <p role="status">{result.outcomes.some(o => !['success', 'empty'].includes(o.status))
        ? 'No observations returned; inspect provider failures or unsupported filters above.' : 'No observations found for this region and period.'}</p>}
      {result.observations.length > 0 && <>
        <div className="flex gap-3 items-center flex-wrap">
          <button type="button" onClick={() => void archive.download()} disabled={!selectedIds.length || downloading}
            className="bg-emerald-400 text-gray-950 rounded px-3 py-2 font-bold disabled:opacity-40 disabled:cursor-not-allowed">
            {downloading ? 'Downloading selected observations…' : `Download selected (${selectedIds.length})`}
          </button>
          <span>Original native files. No reprojection or ML is implied.</span>
        </div>
        <div className="overflow-x-auto max-h-96 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead><tr><th>Select</th><th>Observation / instrument</th><th>Observation time (UTC)</th><th>Products and analysis</th></tr></thead>
            <tbody>{result.observations.map(record => <tr key={record.id} className="border-t border-paper-800">
              <td className="p-2"><input type="checkbox" aria-label={`Select observation ${record.native_id}`} checked={selectedIds.includes(record.id)}
                disabled={downloading || !record.is_available || !record.original || record.product_kind !== 'image'} onChange={() => archive.toggle(record.id)} /></td>
              <td className="p-2 max-w-xs break-all"><strong>{record.collection} · {record.instrument ?? 'Instrument unspecified'}</strong><br />
                <span>{record.native_id}</span><details><summary>Server observation ID</summary>{record.id}</details></td>
              <td className="p-2 whitespace-nowrap">{timestamp(record) ? <time dateTime={timestamp(record)}>{timestamp(record)}</time> : 'Observation date unavailable'}<br />
                <span className="text-paper-400">Time quality: {record.time.quality}</span></td>
              <td className="p-2">{record.original ? 'Original available for resolution' : 'Original delivery unavailable'}<br />
                {record.analysisEligible ? 'Analysis eligible · not run' : 'ML unavailable: instrument/product is not qualified'}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
    </>}
    {job && <section aria-label="Archive download progress" className="border border-paper-700 rounded p-3 space-y-2">
      <h3 className="font-bold">Download: {job.status}</h3>
      <p role="status">{job.progress.ready_chunks} / {job.progress.total_chunks} native files ready · {job.progress.failed_chunks} failed · {job.progress.unavailable_chunks} unavailable</p>
      {job.errors?.map((failure, i) => <p role="alert" key={i}>{failure.code}: {failure.message}</p>)}
      {job.chunks.map(chunk => {
        const record = job.observations?.find(o => o.id === chunk.frame_id) ?? result?.observations.find(o => o.id === chunk.frame_id);
        const asset = job.assets?.find(a => a.record_id === chunk.frame_id)?.asset;
        const nativeLink = chunk.status === 'ready' ? link(chunk.fits_cutout_url || asset?.artifact_url) : undefined;
        const preview = chunk.status === 'ready' && chunk.preview_status === 'ready' ? link(chunk.image_url) : undefined;
        return <article key={chunk.id} className="border-t border-paper-800 pt-2 space-y-1 break-words">
          <p>{record?.native_id ?? chunk.frame_id} · {chunk.status}</p>
          {record && <p>Observed UTC: {timestamp(record) ?? 'unavailable'}</p>}
          {nativeLink && <a href={nativeLink} className="text-emerald-300 underline" download>Download native file · {record?.native_id ?? chunk.frame_id}</a>}
          {chunk.error && <p role="alert">{chunk.error.code}: {chunk.error.message}</p>}
          {preview ? <Preview key={`${job.id}:${preview}`} url={preview} id={record?.native_id ?? chunk.frame_id} />
            : <p>Preview {chunk.preview_status === 'pending' ? 'pending' : 'unavailable'}: a native FITS file requires a supported image-rendering/preparation endpoint.</p>}
          <p>{asset?.analysisEligible === true && record?.analysisEligible === true
            ? 'Analysis eligible · no analysis has been requested' : 'ML unavailable for this product; no analysis was started.'}</p>
        </article>;
      })}
    </section>}
  </section>;
}
