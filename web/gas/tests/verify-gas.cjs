'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {setup,fixture,plain,base,root,source}=require('./gas-harness.cjs');
let checks=0,combinations=0;
function test(name,fn){fn();checks++;console.log('PASS '+name);}
function near(a,b){assert.ok(Math.abs(a-b)<1e-5,`${a} != ${b}`);}
test('Dynamic list includes a fourth ETF and disabled reasons; no fixed default requirement',()=>{
  const {app}=setup();const choices=app.listChoices();assert.equal(choices.total,8);assert.equal(choices.eligibleCount,4);
  assert.ok(choices.etfs.find(r=>r.symbol==='00900').eligible);assert.equal(choices.etfs.find(r=>r.symbol==='00901').eligible,false);
  const data=plain(fixture);data.catalog.items=data.catalog.items.filter(r=>r.symbol==='00900');data.catalog.total=data.catalog.eligibleCount=1;
  assert.equal(setup({data}).app.listChoices().defaults.etf,'00900');
});
test('Selected ETF query uses its own dates and historic CAGR; custom rate stays independent',()=>{
  const {app,calls}=setup(), c=app.listChoices(), selected=app.getEtfSnapshot('00900');
  const p={...base,etf:'00900',snapshotId:selected.snapshotId};
  const r=app.calculate({...p,returnMode:'historical'});
  near(r.annualReturn,Math.pow(121/100,365/730)-1);near(r.annualReturn,.1);
  assert.equal(app.calculate(p).assets,2400000);assert.equal(app.calculate(p).annualReturn,0);
  assert.equal(calls.length,2);assert.ok(calls[1].request.endsWith('symbol=00900'));
  assert.equal(calls[1].config.followRedirects,false);assert.equal(calls[1].config.validateHttpsCertificates,true);
  assert.equal(calls[1].config.headers.Authorization,'Bearer '+'t'.repeat(48));
});
test('All catalogue pages are complete and belong to one version',()=>{
  const data=plain(fixture),template=data.catalog.items[0];
  data.catalog.items=Array.from({length:205},(_,i)=>({...template,symbol:String(10000+i)}));data.catalog.total=data.catalog.eligibleCount=205;
  const {app,calls}=setup({data});assert.equal(app.listChoices().etfs.length,205);assert.equal(calls.length,3);
  assert.ok(calls[1].request.includes('catalog_id=catalog2-'));
  for(const mutate of [
    (b,u)=>{if(u.searchParams.get('offset')!=='0')b.catalog.catalogId='catalog2-'+'f'.repeat(24);},
    b=>{b.catalog.nextOffset=0;}, b=>{b.catalog.total=2001;},
    b=>{b.catalog.items[1].symbol=b.catalog.items[0].symbol;},
    b=>{b.catalog.eligibleCount=0;},b=>{b.catalog.items[0].eligible='true';}
  ]) assert.throws(()=>setup({data,mutate}).app.listChoices());
});
test('Empty and all-unavailable lists do not manufacture default ETF',()=>{
  for(const empty of [true,false]) {
    const data=plain(fixture);data.catalog.items=empty?[]:data.catalog.items.filter(r=>!r.eligible);
    data.catalog.total=data.catalog.items.length;data.catalog.eligibleCount=0;
    const {app}=setup({data});assert.equal(app.listChoices().defaults.etf,'');assert.throws(()=>app.runLiveChecks(),/沒有/);
  }
});
test('Auth, HTTPS, redirects, errors and malformed responses have no fallback',()=>{
  for(const options of [{url:'http://api.example.com'},{token:'short'},{status:301},{status:401},{status:409},{status:503},{offline:true},{raw:'bad json'},{raw:' '.repeat(90001)},
    {mutate:b=>{b.mode='SNAPSHOT';}},{mutate:b=>{b.catalog.queriedAt='2026-11-01T00:00:00+08:00';}}])
    assert.throws(()=>setup(options).app.listChoices());
  const {app}=setup();assert.throws(()=>app.getEtfSnapshot('00901'));assert.throws(()=>app.getEtfSnapshot('00900&symbol=0050'));
});
test('Symbol mixing, stale cache, old API schema and source changes are rejected',()=>{
  let h=setup(),s=h.app.getEtfSnapshot('0050');
  assert.throws(()=>h.app.calculate({...base,etf:'00900',snapshotId:s.snapshotId}),/不一致/);
  assert.throws(()=>h.app.calculate({...base,snapshotId:'mysql2-'+'f'.repeat(24)}),/已更新/);
  h.clock.now+=500000;
  assert.throws(()=>h.app.calculate({...base,snapshotId:s.snapshotId}),/過期/);
  for(const mutate of [s=>s.schemaVersion=1,s=>s.eligibility.eligible=false,s=>s.etfs.push(s.etfs[0]),s=>s.etfs[0].priceStart='2024-02-30',s=>s.houses.pop()]){
    h=setup({mutate:(b,u)=>{if(u.pathname.includes('snapshot'))mutate(b.snapshot);}});
    assert.throws(()=>h.app.getEtfSnapshot('0050'));
  }
});
test('Independent monthly accumulation for zero, negative and effective positive annual returns',()=>{
  const {app}=setup();for(const annual of [-.5,-.05,0,.06,.12])for(const years of [1,10,30]){
    let value=0;for(let m=0;m<years*12;m++)value=value*(1+annual)**(1/12)+20000;
    near(app.futureValue_(20000,annual,years),value);
  }
  near((1+Math.expm1(Math.log1p(.12)/12))**12-1,.12);
});
test('432 combinations preserve v3 financial formulas and housing logic',()=>{
  const oldData=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/v3-contract.json'),'utf8'));
  const old=vm.createContext({console,Date:class extends Date {static now(){return Date.parse(oldData.snapshot.queriedAt)+30000;}},
    PropertiesService:{getScriptProperties:()=>({getProperty:k=>k==='API_BASE_URL'?'https://api.example.com':'t'.repeat(48)})},
    CacheService:{getScriptCache:()=>({get:()=>null,put:()=>{}})},UrlFetchApp:{fetch:()=>({getResponseCode:()=>200,getContentText:()=>JSON.stringify(oldData)})}});
  new vm.Script(fs.readFileSync(path.join(root,'tests/fixtures/v3-Code.gs'),'utf8')).runInContext(old);
  const {app}=setup(), choices=app.listChoices();
  for(const city of choices.cities)for(const etf of oldData.snapshot.etfs)for(const transactionType of choices.transactionTypes)
  for(const years of [5,10,20])for(const downPaymentRatio of [.2,.4])for(const returnMode of ['custom','historical']){
    const p={...base,city,etf:etf.symbol,transactionType,years,downPaymentRatio,returnMode};
    const a=app.calculate({...p,snapshotId:app.getEtfSnapshot(etf.symbol).snapshotId});
    const b=old.calculate({...p,snapshotId:oldData.snapshot.id});
    for(const k of ['assets','downPaymentTarget','monthlyNeeded','gap','surplus'])near(a[k],b[k]);combinations++;
  }
});
test('Input boundaries and local self-check',()=>{
  const {app}=setup(),s=app.getEtfSnapshot('0050'),p={...base,snapshotId:s.snapshotId};
  for(const bad of [{years:0},{years:31},{years:1.5},{monthly:-1},{downPaymentRatio:.9},{annualReturnPercent:-100},{returnMode:'guess'}])assert.throws(()=>app.calculate({...p,...bad}));
  assert.equal(app.calculate({...p,monthly:0}).assets,0);assert.equal(app.runLiveChecks().checksPassed,3);
  const html=fs.readFileSync(path.join(root,'Index.html'),'utf8');new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
  assert.ok(!/API_TOKEN|Authorization:|Jdbc\./.test(html));assert.ok(!source.includes("etf:'0050'"));
});
const report={checksPassed:checks,calculationCombinations:combinations,mode:'LOCAL MOCK ONLY: no real MySQL, GCP or GAS execution',generatedAt:new Date().toISOString()};
fs.writeFileSync(path.join(root,'verification/gas-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
