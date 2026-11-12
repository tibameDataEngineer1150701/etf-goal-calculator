'use strict';
// Browser interaction with mocked GAS/HTTP. Never contacts production.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {setup,fixture,plain,base,root}=require('./gas-harness.cjs');
const out=path.join(root,'verification');
async function main(){
  const options={headless:true};
  if(process.env.TEST_BROWSER_PATH)options.executablePath=process.env.TEST_BROWSER_PATH;
  else options.channel='chrome';
  const browser=await chromium.launch(options);
  let checks=0;const errors=[];
  async function boot({data,failList=false}={}){
    const {app}=setup({data});
    const page=await browser.newPage({viewport:{width:1280,height:1000}});
    page.setDefaultTimeout(10000);
    page.on('pageerror',e=>errors.push(e.message));
    await page.route(/^https?:/,r=>r.abort());
    await page.exposeFunction('calculateLocal',p=>plain(app.calculate(p)));
    await page.exposeFunction('selectLocal',symbol=>plain(app.getEtfSnapshot(symbol)));
    await page.addInitScript(({catalog,failList})=>{
      window.testState={delay:0,fail:false,version:null,selectDelay:{},failSelected:null};
      function runner(success,failure){return {
        withSuccessHandler(fn){return runner(fn,failure);},withFailureHandler(fn){return runner(success,fn);},
        listChoices(){setTimeout(()=>{if(failList)failure({message:'模擬清單 API 失敗'});else success(catalog);},0);},
        getEtfSnapshot(symbol){
          const delay=window.testState.selectDelay[symbol]||0,fail=window.testState.failSelected===symbol;
          setTimeout(async()=>{try{
            if(fail)throw Error('模擬單檔 API 失敗');success(await window.selectLocal(symbol));
          }catch(e){failure({message:e.message});}},delay);
        },
        calculate(p){const state={...window.testState};setTimeout(async()=>{try{
          if(state.fail)throw Error('模擬試算 API 失敗');const r=await window.calculateLocal(p);
          if(state.version)r.version=state.version;success(r);
        }catch(e){failure({message:e.message});}},state.delay);}
      };}
      window.google={script:{run:runner()}};
    },{catalog:plain(app.listChoices()),failList});
    await page.goto(pathToFileURL(path.join(root,'Index.html')).href);
    if(!failList)await page.waitForFunction(()=>!document.getElementById('fields').disabled);
    return {page,app};
  }
  async function test(name,fn){await fn();checks++;console.log('PASS '+name);}
  try{
    const {page}=await boot();
    const text=id=>page.locator('#'+id).innerText();
    async function ready(symbol){await page.waitForFunction(s=>selectedReady()&&selectedData.symbol===s,symbol);}
    async function calc(){await page.locator('#submit').click();await page.waitForFunction(()=>document.getElementById('status').textContent.startsWith('試算完成：'));}
    async function choose(symbol){await page.locator('#etf').selectOption(symbol);await ready(symbol);}
    await ready('0050');
    await test('Database list shows 8 symbols / 4 eligible, disabled rows have reasons',async()=>{
      assert.equal(await page.locator('#etf option').count(),8);assert.equal(await page.locator('#etf option:disabled').count(),4);
      assert.match(await text('etfHelp'),/8 檔.*4 檔/);
      assert.match(await page.locator('#unavailableEtfs').textContent(),/尚無價格.*期間不足|尚無價格/);
      assert.match(await text('etfSource'),/0050.*歷史 CAGR/);
    });
    await test('Zero-rate baseline and rounded displays preserve v3 values',async()=>{
      await calc();assert.equal(await text('assetsValue'),'2,400,000 元');assert.equal(await text('targetValue'),'2,472,198 元');
      assert.equal(await text('differenceValue'),'72,198 元');assert.equal(await text('neededValue'),'20,602 元');
      assert.equal(await text('outcomeTitle'),'頭期款不足');
      assert.equal(await page.locator('#results > :last-child').getAttribute('id'),'sourceDetails');
      assert.equal(await page.locator('#sourceDetails').getAttribute('open'),null);
    });
    await test('Fourth ETF selection loads its own source period and historical rate',async()=>{
      await choose('00900');assert.match(await text('etfSource'),/2024-11-09.*2026-11-09.*10%/);
      assert.equal(await page.locator('#results').getAttribute('data-stale'),'true');
      await page.locator('#returnMode').selectOption('historical');await calc();
      assert.match(await text('returnValue'),/10%.*歷史延伸/);assert.match(await text('selectionSummary'),/00900/);
      assert.match(await page.locator('#sourceSummary').textContent(),/2024-11-09～2026-11-09/);
      await page.locator('#returnMode').selectOption('custom');await page.locator('#annualReturnPercent').fill('0');await calc();
      assert.equal(await text('assetsValue'),'2,400,000 元');
    });
    await test('Late ETF response cannot overwrite a more recent selection',async()=>{
      await page.evaluate(()=>{testState.selectDelay={'0050':350};});
      await page.locator('#etf').selectOption('0050');assert.ok(await page.locator('#submit').isDisabled());
      await page.locator('#etf').selectOption('00900');await ready('00900');await page.waitForTimeout(450);
      assert.equal(await page.evaluate(()=>selectedData.symbol),'00900');assert.match(await text('etfSource'),/00900/);
      await page.evaluate(()=>{testState.selectDelay={};});
    });
    await test('Selected-data failure disables calculation even after editing other fields; retry recovers',async()=>{
      await page.evaluate(()=>{testState.failSelected='0056';});await page.locator('#etf').selectOption('0056');
      await page.waitForFunction(()=>!document.getElementById('error').hidden);
      await page.locator('#monthly').fill('21000');assert.ok(await page.locator('#submit').isDisabled());
      assert.match(await text('status'),/尚未成功載入/);
      assert.equal(await page.evaluate(()=>selectedData),null);
      await page.evaluate(()=>{testState.failSelected=null;});await page.locator('#reloadEtf').click();await ready('0056');
    });
    await test('Reset invalidates pending calculation and reloads default selection',async()=>{
      await page.evaluate(()=>{testState.delay=350;});await page.locator('#submit').click();await page.locator('#reset').click();
      await ready('0050');await page.waitForTimeout(450);assert.ok(await page.locator('#results').isHidden());
      await page.evaluate(()=>{testState.delay=0;});await calc();
    });
    await test('Rounding, negative return, zero investment, ratio and chart regression',async()=>{
      const cases=[
        {monthly:21000,rate:0,ratio:40,assets:'2,520,000 元',gap:'2,424,395 元',needed:'41,204 元'},
        {monthly:0,rate:0,ratio:40,assets:'0 元',gap:'4,944,395 元',needed:'41,204 元'},
        {monthly:21000,rate:-5,ratio:40,assets:'1,975,591 元',gap:'2,968,804 元',needed:'52,558 元'},
        {monthly:21000,rate:0,ratio:20,assets:'2,520,000 元',gap:'47,802 元',needed:'20,602 元'}
      ];
      for(const c of cases){
        await page.locator('#monthly').fill(String(c.monthly));await page.locator('#annualReturnPercent').fill(String(c.rate));
        await page.locator('#downPaymentPercent').fill(String(c.ratio));await calc();
        assert.equal(await text('assetsValue'),c.assets);assert.equal(await text('differenceValue'),c.gap);assert.equal(await text('neededValue'),c.needed);
      }
      assert.equal(await text('outcomeTitle'),'試算達標');assert.equal(await page.locator('#chart svg polyline').count(),3);
      assert.equal(await page.locator('#yearRows tr').count(),11);
      await page.locator('#years').fill('0');await page.locator('#submit').click();assert.ok(await page.evaluate(()=>document.getElementById('years').validity.rangeUnderflow));
      await page.locator('#years').fill('31');await page.locator('#submit').click();assert.ok(await page.evaluate(()=>document.getElementById('years').validity.rangeOverflow));
      await page.locator('#years').fill('10');
    });
    await test('Calculation failure and mismatched versions never render new success',async()=>{
      await page.evaluate(()=>{testState.fail=true;});await page.locator('#submit').click();
      await page.waitForFunction(()=>!document.getElementById('error').hidden);assert.match(await text('error'),/模擬試算/);
      assert.equal(await page.locator('#results').getAttribute('data-stale'),'true');
      await page.evaluate(()=>{testState.fail=false;testState.version='old';});await page.locator('#submit').click();
      await page.waitForFunction(()=>document.getElementById('error').textContent.includes('版本不一致'));
      assert.ok(await page.locator('#results').isHidden());await page.evaluate(()=>{testState.version=null;});
    });
    await test('Source disclosure is keyboard-accessible; responsive widths do not overflow',async()=>{
      await choose('00900');await calc();
      const summary=page.locator('#sourceDetails > summary');await summary.focus();await page.keyboard.press('Enter');
      assert.ok(await page.locator('#sourceSummary').isVisible());await page.keyboard.press('Space');
      assert.ok(!await page.locator('#sourceSummary').isVisible());
      await page.evaluate(()=>{document.getElementById('dataBanner').textContent='本機模擬測試｜非正式資料庫、非已發布網站';});
      for(const width of [320,390,768,1280]){
        await page.setViewportSize({width,height:1000});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow '+width);
        if(width===390)await page.screenshot({path:path.join(out,'v4-mobile.png'),fullPage:true});
      }
      await page.screenshot({path:path.join(out,'v4-desktop.png'),fullPage:true});
    });
    await test('All unavailable and empty catalogues stay disabled without fake defaults',async()=>{
      for(const empty of [false,true]){
        const data=plain(fixture);data.catalog.items=empty?[]:data.catalog.items.filter(r=>!r.eligible);
        data.catalog.total=data.catalog.items.length;data.catalog.eligibleCount=0;
        const other=await boot({data});assert.ok(await other.page.locator('#submit').isDisabled());
        assert.equal(await other.page.locator('#etf').inputValue(),'');assert.match(await other.page.locator('#status').innerText(),/尚無可用/);
        await other.page.close();
      }
    });
    await test('Whole-catalogue failure and missing GAS environment are explicit',async()=>{
      const failed=await boot({failList:true});await failed.page.waitForFunction(()=>!document.getElementById('error').hidden);
      // Playwright's isDisabled() does not classify fieldset itself as a form control.
      // Check native state plus the actual controls the user must not operate.
      assert.ok(await failed.page.evaluate(()=>document.getElementById('fields').disabled));
      for(const id of ['etf','monthly','submit','reset','reloadEtf'])assert.ok(await failed.page.locator('#'+id).isDisabled());
      assert.equal(await failed.page.evaluate(()=>selectedData),null);
      assert.ok(await failed.page.locator('#results').isHidden());await failed.page.close();
      const offline=await browser.newPage();await offline.goto(pathToFileURL(path.join(root,'Index.html')).href);
      assert.match(await offline.locator('#error').innerText(),/直接開本機 HTML 無法呼叫 GAS/);await offline.close();
    });
    assert.deepEqual(errors,[]);
    const report={checksPassed:checks,browser:await browser.version(),mode:'LOCAL browser with mocked GAS/HTTP, synthetic inputs, no live cloud verification',errors,generatedAt:new Date().toISOString()};
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
