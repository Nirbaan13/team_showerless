import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { fetchSpectrum } from '../src/services/spectrumClient.mjs';

async function server(handler, run) {
  const s=createServer(handler);
  await new Promise(resolve=>s.listen(0,'127.0.0.1',resolve));
  try { await run(`http://127.0.0.1:${s.address().port}`); }
  finally { s.closeAllConnections(); await new Promise(resolve=>s.close(resolve)); }
}

test('waits for the Scala download before returning the measured spectrum',async()=>{
  let requests=0;
  await server((req,res)=>{
    requests++;
    res.setHeader('Content-Type','application/json');
    if(requests===1){
      res.writeHead(202,{'Retry-After':'0'});
      res.end(JSON.stringify({download_id:'job-real',status:'preparing'}));
    } else {
      assert.equal(new URL(req.url,'http://localhost').searchParams.get('download_id'),'job-real');
      res.end(JSON.stringify({quality:'experimental_visualization_photometry',scientifically_calibrated:false,total_channels:1,
        spectrum:[{frame_id:'frame-real',wavelength_um:.9,flux_mjy:2.23}]}));
    }
  },async base=>{
    const result=await fetchSpectrum(base,new URLSearchParams({ra:'120',dec:'-20'}));
    assert.equal(result.spectrum[0].frame_id,'frame-real');
    assert.equal(requests,2);
  });
});

test('archive failures remain errors instead of returning a fabricated spectrum',async()=>{
  await server((req,res)=>{res.writeHead(404);res.end(JSON.stringify({code:'no_measurements',message:'No usable aperture'}));},
    async base=>assert.rejects(fetchSpectrum(base,new URLSearchParams({ra:'120',dec:'-20'})),/No usable aperture/));
});

test('leaving a pending spectrum cancels polling',async()=>{
  const controller=new AbortController();
  await server((req,res)=>{res.writeHead(202);res.end(JSON.stringify({download_id:'job-real'}));controller.abort();},
    async base=>assert.rejects(fetchSpectrum(base,new URLSearchParams(),controller.signal),{name:'AbortError'}));
});
