
/** Poll the Scala-owned download and return only measured pipeline results. */
export async function fetchSpectrum(base, parameters, signal) {
  const timeout=AbortSignal.timeout(300_000);
  const abort=signal ? AbortSignal.any([signal,timeout]) : timeout;
  const params=new URLSearchParams(parameters);
  while (true) {
    abort.throwIfAborted();
    const response=await fetch(`${base}/api/spectrum?${params}`,{signal:abort});
    const result=await response.json();
    if (response.status===202) {
      if (typeof result.download_id!=='string' || !/^[A-Za-z0-9-]{1,128}$/.test(result.download_id)) {
        throw new Error('The backend returned an invalid spectrum download.');
      }
      params.set('download_id',result.download_id);
      const retry=Number(response.headers.get('Retry-After') ?? '2');
      await new Promise((resolve,reject)=>{
        const cancel=()=>{clearTimeout(timer);reject(abort.reason);};
        const timer=setTimeout(()=>{abort.removeEventListener('abort',cancel);resolve();},Math.max(100,Math.min(5000,Number.isFinite(retry)?retry*1000:2000)));
        abort.addEventListener('abort',cancel,{once:true});
        if (abort.aborted) {abort.removeEventListener('abort',cancel);cancel();}
      });
      continue;
    }
    if (!response.ok) throw new Error(typeof result.message==='string'?result.message:`Spectrum request failed (${response.status}).`);
    if (result.quality!=='experimental_visualization_photometry' || result.scientifically_calibrated!==false ||
      !Array.isArray(result.spectrum) || !result.spectrum.length || result.total_channels!==result.spectrum.length) {
      throw new Error('The backend returned an invalid measured spectrum.');
    }
    return result;
  }
}
