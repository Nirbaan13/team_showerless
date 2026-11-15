const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {firefox} = require('/home/usatovpavel/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core');
const base = process.env.PROBE_FRONTEND || 'http://144.124.238.101:8080';
const api = process.env.PROBE_HTTP || 'http://144.124.238.101';
const sha = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35';
(async () => {
  const browser = await firefox.launch({headless:true});
  const errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror', e => errors.push(String(e)));
    await page.goto(base + '/?analysis=1');
    await page.getByRole('heading',{name:'Motion analysis',exact:true}).waitFor();
    await page.getByText('spherex-pairwise-v4',{exact:true}).waitFor();
    await page.getByText('Detection settings',{exact:true}).click();
    await page.getByLabel('Minimum residual S/N',{exact:true}).fill('4.26374819');
    const accepted = page.waitForResponse(r => r.url().endsWith('/api/analyses/motion') && r.request().method()==='POST');
    await page.getByRole('button',{name:'Run analysis',exact:true}).click();
    const admission = await (await accepted).json();
    await page.getByRole('heading',{name:/candidate tracks · 4 exposures/}).waitFor({timeout:120000});
    const job = await (await page.request.get(api + '/api/analyses/' + admission.id)).json();
    assert.equal(job.status,'completed');
    assert.equal(job.result.model.sha256,sha);
    assert.equal(job.result.model.model_family,'RankNetTreeBoost');
    assert.equal(await page.locator('.inference-candidate').count(),job.result.candidates.length);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('.inference-image img')).every(i=>i.complete && i.naturalWidth>0));
    assert.ok(await page.locator('.inference-image svg circle').count());
    await page.locator('.inference-candidate-list select').selectOption('baseline');
    assert.match(await page.locator('.inference-candidate').first().innerText(),/heuristic #1/);
    await page.getByLabel('Minimum residual S/N',{exact:true}).fill('100');
    await page.getByRole('button',{name:'Run analysis',exact:true}).click();
    await page.getByRole('heading',{name:'0 candidate tracks · 4 exposures',exact:true}).waitFor({timeout:120000});
    await page.locator('form select').first().selectOption('download');
    await page.getByLabel('Download ID',{exact:true}).fill('v4-browser-missing-download');
    await page.getByRole('button',{name:'Run analysis',exact:true}).click();
    await page.getByRole('alert').waitFor();
    assert.match(await page.getByRole('alert').innerText(),/not found/i);
    const viewports=[];
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
      const view = await browser.newPage({viewport});
      view.on('pageerror',e=>errors.push(String(e)));
      await view.goto(base+'/?analysis=1&id='+job.id);
      await view.getByRole('heading',{name:`${job.result.candidates.length} candidate tracks · 4 exposures`,exact:true}).waitFor();
      const bounds=await view.locator('.inference-page').evaluate(el=>({top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,viewport:innerHeight}));
      assert.ok(bounds.bottom<=viewport.height+1,JSON.stringify(bounds));
      await view.locator('.inference-page').evaluate(el=>{el.scrollTop=el.scrollHeight});
      const provenance=await view.locator('.inference-limitations').last().boundingBox();
      assert.ok(provenance.y+provenance.height<=viewport.height+1);
      assert.ok(await view.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      if(viewport.width>1000) {
        await view.getByRole('button',{name:'Homepage',exact:true}).click();
        assert.equal(await view.locator('.inference-page').count(),0);
      }
      viewports.push({viewport,bounds,provenance_bottom:provenance.y+provenance.height});
      await view.close();
    }
    assert.deepEqual(errors,[]);
    const proof={checked_at_utc:new Date().toISOString(),frontend_base:base,api_base:api,analysis_id:job.id,model_sha256:sha,frames:job.result.frames.length,candidates:job.result.candidates.length,real_png_loaded:true,trajectory_overlay:true,heuristic_comparison:true,empty:true,missing_download_error:true,viewports,javascript_errors:errors};
    fs.writeFileSync(process.env.PROBE_OUTPUT||path.join(__dirname,'browser-proof.json'),JSON.stringify(proof,null,2));
    console.log(JSON.stringify(proof,null,2));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1});
