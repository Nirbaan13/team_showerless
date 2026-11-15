const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.PROBE_FRONTEND||'http://146.103.122.246:8080';
const {firefox}=require('/home/usatovpavel/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core');
(async()=>{
  const browser=await firefox.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    const loaded=page.waitForResponse(r=>r.url()===base+'/backend/openapi.json');
    await page.goto(base+'/backend/docs');
    const response=await loaded;assert.equal(response.status(),200);
    const spec=await response.json();assert.ok(Object.keys(spec.paths).length>=20);
    const operation=page.locator('.opblock').filter({has:page.locator('.opblock-summary-path').filter({hasText:'/api/analyses/models'})});
    await operation.locator('.opblock-summary').click();
    await operation.getByRole('button',{name:'Try it out',exact:true}).click();
    const executed=page.waitForResponse(r=>r.url()===base+'/api/analyses/models'&&r.request().method()==='GET');
    await operation.getByRole('button',{name:'Execute',exact:true}).click();
    const actual=await executed;assert.equal(actual.status(),200);
    assert.equal((await actual.json()).models[0].model_id,'spherex-v4-development-fc3378f486961a8c');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/tmp/spaceapps-ml-relocation-swagger.png',fullPage:true});
    const proof={frontend_base:base,checked_at_utc:new Date().toISOString(),frontend_proxy_spec_loaded:true,openapi_paths:Object.keys(spec.paths).length,swagger_try_it_out:true,model:'spherex-v4-development-fc3378f486961a8c',javascript_errors:errors};
    fs.writeFileSync(process.env.PROBE_OUTPUT||path.join(__dirname,'swagger-proof.json'),JSON.stringify(proof,null,2));
    console.log(JSON.stringify(proof,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
