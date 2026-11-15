const assert=require('node:assert/strict');
const fs=require('node:fs');
const {firefox}=require('/home/usatovpavel/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core');
(async()=>{
  const browser=await firefox.launch({headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(String(e)));
    const loaded=page.waitForResponse(r=>r.url()==='http://144.124.238.101:8080/backend/openapi.json');
    await page.goto('http://144.124.238.101:8080/backend/docs');
    const response=await loaded;assert.equal(response.status(),200);
    const spec=await response.json();assert.equal(Object.keys(spec.paths).length,20);
    const operation=page.locator('.opblock').filter({has:page.locator('.opblock-summary-path').filter({hasText:'/api/analyses/models'})});
    await operation.locator('.opblock-summary').click();
    await operation.getByRole('button',{name:'Try it out',exact:true}).click();
    const executed=page.waitForResponse(r=>r.url()==='http://144.124.238.101:8080/api/analyses/models'&&r.request().method()==='GET');
    await operation.getByRole('button',{name:'Execute',exact:true}).click();
    const actual=await executed;assert.equal(actual.status(),200);
    assert.equal((await actual.json()).models[0].model_id,'spherex-track-rf-v2');
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'/tmp/spaceapps-ml-swagger-v2-prod.png',fullPage:true});
    const proof={frontend_proxy_spec_loaded:true,openapi_paths:20,swagger_try_it_out:true,model:'spherex-track-rf-v2',javascript_errors:errors};
    fs.writeFileSync('/tmp/spaceapps-ml-swagger-prod-proof.json',JSON.stringify(proof,null,2));
    console.log(JSON.stringify(proof,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
