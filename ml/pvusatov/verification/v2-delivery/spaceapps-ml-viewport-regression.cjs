const assert=require('node:assert/strict');
const fs=require('node:fs');
const {firefox}=require('/home/usatovpavel/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core');
(async()=>{
  const browser=await firefox.launch({headless:true});
  const results=[];
  try{
    for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
      const page=await browser.newPage({viewport});
      const url=(process.env.PROBE_BASE||'http://146.103.122.246:8080')+'/?analysis=1&id='+(process.env.PROBE_JOB||'f5a4bcc9-fbce-4291-88dd-945182ea8de5');
      await page.goto(url);
      await page.getByRole('heading',{name:'10 candidate tracks · 4 exposures',exact:true}).waitFor();
      const bounds=await page.locator('.inference-page').evaluate(el=>({top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom,viewport:innerHeight,clientHeight:el.clientHeight}));
      assert.ok(bounds.bottom<=bounds.viewport+1,JSON.stringify({viewport,bounds}));
      await page.locator('.inference-page').evaluate(el=>{el.scrollTop=el.scrollHeight});
      const last=await page.locator('.inference-limitations').last().boundingBox();
      assert.ok(last.y+last.height<=viewport.height+1,'The provenance controls are clipped below the viewport');
      if(viewport.width>1000){
        await page.getByRole('button',{name:'Homepage',exact:true}).click();
        assert.equal(await page.locator('.inference-page').count(),0,'Global navigation must leave inference');
      }
      results.push({viewport,bounds,provenance_bottom:last.y+last.height});
      await page.close();
    }
    console.log(JSON.stringify(results,null,2));
    fs.writeFileSync(process.env.PROBE_PROOF||'/tmp/spaceapps-ml-viewport-proof.json',JSON.stringify(results,null,2));
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
