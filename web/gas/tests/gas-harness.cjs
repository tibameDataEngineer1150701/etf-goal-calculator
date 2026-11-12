'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'Code.gs'),'utf8');
const fixture=JSON.parse(fs.readFileSync(path.join(root,'verification/local-fixtures.json'),'utf8'));
const plain=value=>JSON.parse(JSON.stringify(value));
const base={city:'臺中市',etf:'0050',transactionType:'成屋買賣',scenario:'hpi10',years:10,monthly:20000,downPaymentRatio:.2,returnMode:'custom',annualReturnPercent:0,houseGrowthPercent:0};
function setup(options={}) {
  const data=plain(options.data||fixture),cache=new Map(),calls=[];
  const clock={now:Date.parse('2026-11-12T04:00:30Z')};
  const app=vm.createContext({console,
    Date:class extends Date {static now(){return clock.now;}},
    CacheService:{getScriptCache:()=>({get:key=>{const c=cache.get(key);return c&&c.expires>clock.now?c.value:null;},put:(key,value,ttl)=>cache.set(key,{value,expires:clock.now+ttl*1000})})},
    PropertiesService:{getScriptProperties:()=>({getProperty:k=>({API_BASE_URL:options.url||'https://api.example.com',API_TOKEN:options.token||'t'.repeat(48)})[k]})},
    UrlFetchApp:{fetch:(request,config)=>{
      calls.push({request,config});
      if(options.offline)throw Error('private connection detail');
      const url=new URL(request);let status=200,body;
      if(url.pathname==='/v2/etfs') {
        const offset=Number(url.searchParams.get('offset')),limit=Number(url.searchParams.get('limit'));
        const c=data.catalog;
        body={mode:'LIVE',catalog:{...c,offset,items:c.items.slice(offset,offset+limit),nextOffset:offset+limit<c.total?offset+limit:null}};
      } else if(url.pathname==='/v2/snapshot') {
        const symbol=url.searchParams.get('symbol');
        body=data.snapshots[symbol];
        if(!body){status=404;body={detail:{code:'ETF_NOT_FOUND'}};}
      } else {throw Error('Unexpected API path '+url.pathname);}
      if(options.mutate) options.mutate(body,url);
      const text=options.raw===undefined?JSON.stringify(body):options.raw;
      return {getResponseCode:()=>options.status||status,getContentText:()=>text};
    }}
  });
  new vm.Script(source).runInContext(app);
  return {app,data,cache,calls,clock};
}
module.exports={setup,fixture,plain,base,root,source};
