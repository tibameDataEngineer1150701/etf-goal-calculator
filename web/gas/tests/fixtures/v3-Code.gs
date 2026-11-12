/**
 * 雲端唯讀串接 v3；計算沿用 v2，取得資料失敗時明確停止。
 * API_BASE_URL 與 API_TOKEN 僅設於 GAS 指令碼屬性，不放入 HTML。
 */
var CALC_VERSION_ = 'gas-live-v3.0-2026-11-04';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index').setTitle('ETF 購屋試算｜雲端資料 v3');
}

// 同一批選項與計算綁定內容版本；快取最長 5 分鐘，沒有靜默備援。
function loadSnapshot_(expectedId) {
  var cache = CacheService.getScriptCache();
  var cacheKey = expectedId ? 'live3:' + expectedId : null;
  if (cacheKey) {
    var cached = cache.get(cacheKey);
    if (cached) {
      var existing = JSON.parse(cached);
      validateLiveSnapshot_(existing);
      if (existing.id !== expectedId) throw new Error('快取版本不一致，請重新整理頁面。');
      return existing;
    }
  }
  var props = PropertiesService.getScriptProperties();
  var base = String(props.getProperty('API_BASE_URL') || '').replace(/\/$/, '');
  var token = String(props.getProperty('API_TOKEN') || '');
  if (!/^https:\/\/[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::443)?$/.test(base) || token.length < 32)
    throw new Error('尚未設定有效 HTTPS API_BASE_URL 或 API_TOKEN；請由專案管理員設定指令碼屬性。');
  var response;
  try {
    response = UrlFetchApp.fetch(base + '/v1/snapshot', {
      method:'get', headers:{Authorization:'Bearer ' + token},
      followRedirects:false, validateHttpsCertificates:true, muteHttpExceptions:true
    });
  } catch (err) { throw new Error('無法連接雲端 API；未切換成範例資料。'); }
  if (response.getResponseCode() !== 200)
    throw new Error('雲端資料讀取失敗（HTTP ' + response.getResponseCode() + '），請確認服務及授權。');
  var body = response.getContentText();
  if (body.length > 90000) throw new Error('資料量超過此版上限，請由管理員檢查。');
  var envelope;
  try { envelope = JSON.parse(body); } catch (err) { throw new Error('API 回傳格式無效。'); }
  if (!envelope || envelope.mode !== 'LIVE') throw new Error('API 資料模式錯誤。');
  var s = envelope.snapshot;
  validateLiveSnapshot_(s);
  if (expectedId && s.id !== expectedId) throw new Error('來源資料已更新，請重新整理頁面取得同一批選項與資料。');
  cache.put('live3:' + s.id, JSON.stringify(s), 300);
  return s;
}

function validateLiveSnapshot_(s) {
  validateSnapshot_(s);
  if (s.schemaVersion !== 1 || !/^mysql-[a-f0-9]{24}$/.test(s.id || ''))
    throw new Error('雲端資料契約版本無效。');
  var queried = Date.parse(s.queriedAt);
  if (!Number.isFinite(queried) || queried > Date.now()+300000 || Date.now()-queried > 420000)
    throw new Error('雲端讀取時間過期或無效，請重新整理；不會使用過期資料。');
  s.etfs.forEach(function(r) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.priceStart || '') || !/^\d{4}-\d{2}-\d{2}$/.test(r.priceEnd || ''))
      throw new Error('缺少各 ETF 的實際來源日期。');
    var start = Date.parse(r.priceStart+'T00:00:00Z'), end = Date.parse(r.priceEnd+'T00:00:00Z');
    if (!Number.isFinite(start) || !Number.isFinite(end) || end-start < 365*86400000 ||
        new Date(start).toISOString().slice(0,10)!==r.priceStart ||
        new Date(end).toISOString().slice(0,10)!==r.priceEnd ||
        r.priceEnd>s.capturedDate || r.priceStart<s.priceStart || r.priceEnd>s.priceEnd)
      throw new Error('ETF 日期無效或超出資料範圍。');
  });
}

function listChoices() {
  var s = loadSnapshot_();
  return {
    mode:'LIVE', version:CALC_VERSION_, snapshotId:s.id, queriedAt:s.queriedAt,
    cities:s.houses.map(function (r) {return r.city;}),
    etfs:s.etfs.map(function (r) {return {symbol:r.symbol, name:r.name, annualReturn:etfCagr_(r,s)};}),
    transactionTypes:['成屋買賣','預售屋買賣'],
    scenarios:[{id:'hpi10',label:'近 10 年 HPI 歷史延伸'},{id:'hpi5',label:'近 5 年 HPI 歷史延伸'},{id:'custom',label:'自訂房價年成長率'}],
    defaults:{city:'臺中市',etf:'0050',transactionType:'成屋買賣',scenario:'hpi10',years:10,monthly:20000,downPaymentPercent:20,returnMode:'custom',annualReturnPercent:0,houseGrowthPercent:0},
    warning:'雲端讀取時間 '+s.queriedAt+'（最長約 6 分鐘快取）。讀取時間不等於上游資料更新時間；歷史報酬不是未來預測。'
  };
}

function calculate(input) {
  if (!input || !/^mysql-[a-f0-9]{24}$/.test(input.snapshotId || '')) throw new Error('缺少選項資料版本，請重新整理頁面。');
  var s = loadSnapshot_(input.snapshotId);
  var p = validateInput_(input,s);
  var house = s.houses.filter(function (r) {return r.city===p.city;})[0];
  var etf = s.etfs.filter(function (r) {return r.symbol===p.etf;})[0];
  var historic = etfCagr_(etf,s);
  var annual = p.returnMode==='historical' ? historic : p.annualReturnPercent/100;
  var growth = p.scenario==='custom' ? p.houseGrowthPercent/100 : Math.pow(house.hpi/(p.scenario==='hpi5'?house.hpi5:house.hpi10),1/(p.scenario==='hpi5'?5:10))-1;
  var unitPrice = p.transactionType==='成屋買賣' ? house.existing : house.presale;
  var count = p.transactionType==='成屋買賣' ? house.existingCount : house.presaleCount;
  var base = unitPrice*30*3.3058;
  var timeline = [];
  for (var y=0;y<=p.years;y++) {
    timeline.push({year:y,principal:p.monthly*12*y,assets:futureValue_(p.monthly,annual,y),downPaymentTarget:base*Math.pow(1+growth,y)*p.downPaymentRatio});
  }
  var final = timeline[timeline.length-1];
  var needed = Math.ceil(final.downPaymentTarget/futureValue_(1,annual,p.years));
  var delta = final.assets-final.downPaymentTarget;
  var warnings = [
    '資料經 HTTPS API 自團隊 MySQL 取得；讀取時間 '+s.queriedAt+'，可能使用短暫快取。來源內容尚未與官方逐筆資料交叉驗證。',
    '原上游程式只依房地交易標的篩選；主要用途是否住宅、車位拆價與排除特殊交易仍待確認。30 坪金額是單價換算參考，不是實際 30 坪住宅成交中位總價。',
    'ETF 歷史 CAGR 僅描述這段期間；使用固定歷史高報酬推估未來可能過度樂觀，請同時測試零報酬與負報酬。',
    '本版不使用未定案的「樂觀加 2 個百分點」，也不把 5 年／10 年歷史成長率稱為保守或樂觀。'
  ];
  var age = Math.floor((Date.now()-Date.parse(s.capturedDate+'T00:00:00+08:00'))/86400000);
  if(age>0) warnings.unshift('取得資料的日期較早，請重新整理；來源期間請見下方。');
  var result = {
    mode:'LIVE', version:CALC_VERSION_, snapshotId:s.id, queriedAt:s.queriedAt, params:p, propertyAreaPing:30,
    annualReturn:annual, historicalAnnualReturn:historic, houseAnnualGrowth:growth,
    baseHousePrice:base, futureHousePrice:base*Math.pow(1+growth,p.years),
    currentDownPaymentTarget:base*p.downPaymentRatio, downPaymentTarget:final.downPaymentTarget,
    assets:final.assets, principal:final.principal, gap:Math.max(0,-delta), surplus:Math.max(0,delta),
    achieved:delta>=0, monthlyNeeded:needed, additionalMonthlyNeeded:Math.max(0,needed-p.monthly), timeline:timeline,
    warnings:warnings,
    sourceSummary:'房地交易 '+s.housePeriod+'／'+count+' 筆；HPI '+s.hpiPeriod+'；ETF '+etf.priceStart+'～'+etf.priceEnd+'／'+etf.observations+' 筆。',
    assumptions:[
      '房價基準＝每平方公尺中位單價 '+unitPrice+' 元 × 30 坪 × 3.3058；面積口徑沿用上游設定。',
      '房價 CAGR＝HPI 期末／期初的 1／年數 次方 − 1；選擇自訂時則使用輸入值。房價與投資使用相同的未來年限。',
      'ETF 端點='+etf.first+' → '+etf.last+'；歷史 CAGR 按實際日數／365 重算，不沿用舊 etf_cagr。',
      '有效月報酬率＝(1＋有效年報酬率)^(1/12)−1；初始資產 0，每月底投入，非每月初投入。',
      '未來頭期款＝基準價格 × (1＋房價年成長率)^年限 × 使用者頭期款比例。',
      '每月所需投入向上取整元；計算過程保留精度，差額與表格只在顯示時取整。',
      '全部為名目金額；不混用 real_hpi 與名目 ETF 報酬，也未額外計入 CPI。',
      '未另計交易稅費、買賣手續費、購屋附帶費、貸款資格或月供；adjusted close 的配息調整口徑仍需團隊確認，不另加一次股息。',
      '固定報酬不包含市場波動、順序風險或達標機率；0% 預設只是測試起點，不是報酬預測。'
    ]
  };
  [result.assets,result.futureHousePrice,result.downPaymentTarget,result.monthlyNeeded].forEach(function (n) {if(!Number.isFinite(n)||Math.abs(n)>Number.MAX_SAFE_INTEGER) throw new Error('計算超出可可靠顯示整元的範圍，請降低年限或報酬假設。');});
  return result;
}

function validateInput_(v,s) {
  if(!v || typeof v!=='object' || Array.isArray(v)) throw new Error('請提供完整條件。');
  if(!s.houses.some(function(r){return r.city===v.city;})) throw new Error('城市不在已查核快照中。');
  if(!s.etfs.some(function(r){return r.symbol===v.etf;})) throw new Error('ETF 不在已查核快照中。');
  if(['成屋買賣','預售屋買賣'].indexOf(v.transactionType)<0) throw new Error('交易類型無效。');
  if(['hpi5','hpi10','custom'].indexOf(v.scenario)<0) throw new Error('房價情境無效。');
  if(['custom','historical'].indexOf(v.returnMode)<0) throw new Error('請明確選擇報酬假設。');
  return {city:v.city,etf:v.etf,transactionType:v.transactionType,scenario:v.scenario,returnMode:v.returnMode,
    years:numberInput_(v.years,'年限',1,30,true), monthly:numberInput_(v.monthly,'月投入',0,1000000,true),
    downPaymentRatio:numberInput_(v.downPaymentRatio,'頭期款比例',0.1,0.8,false),
    annualReturnPercent:v.returnMode==='custom'?numberInput_(v.annualReturnPercent,'自訂年報酬率',-90,100,false):null,
    houseGrowthPercent:v.scenario==='custom'?numberInput_(v.houseGrowthPercent,'自訂房價年成長率',-50,50,false):null};
}

function numberInput_(value,label,min,max,integer) {
  if(typeof value!=='number' && typeof value!=='string') throw new Error(label+'必須是數字。');
  if(typeof value==='string' && !/^-?(?:\d+\.?\d*|\.\d+)$/.test(value.trim())) throw new Error(label+'必須是有效數字。');
  var n=Number(value);
  if(!Number.isFinite(n)||n<min||n>max||(integer&&!Number.isInteger(n))) throw new Error(label+'超出範圍或格式無效。');
  return n;
}

function etfCagr_(r,s) {
  var days=(Date.parse(r.priceEnd+'T00:00:00Z')-Date.parse(r.priceStart+'T00:00:00Z'))/86400000;
  return Math.pow(r.last/r.first,365/days)-1;
}

function futureValue_(monthly,annual,years) {
  if(!Number.isFinite(monthly)||monthly<0||!Number.isFinite(annual)||annual<=-1||!Number.isFinite(years)||years<0||!Number.isInteger(years*12)) throw new Error('複利參數無效。');
  var n=years*12;
  if(n===0||monthly===0) return 0;
  var logMonth=Math.log1p(annual)/12;
  var rate=Math.expm1(logMonth);
  return rate===0 ? monthly*n : monthly*Math.expm1(n*logMonth)/rate;
}

function validateSnapshot_(s) {
  if(!s || !Array.isArray(s.houses)||!Array.isArray(s.etfs)||s.houses.length!==6||s.etfs.length===0) throw new Error('快照資料不完整；不使用替代假資料。');
  [s.capturedDate,s.priceStart,s.priceEnd].forEach(function(d){if(!/^\d{4}-\d{2}-\d{2}$/.test(d)||!Number.isFinite(Date.parse(d+'T00:00:00Z'))||new Date(d+'T00:00:00Z').toISOString().slice(0,10)!==d) throw new Error('快照日期無效。');});
  if(Date.parse(s.priceEnd)<Date.parse(s.priceStart)+365*86400000 || s.priceEnd>s.capturedDate) throw new Error('ETF 期間不足一年或超過擷取日。');
  [s.housePeriod,s.hpiPeriod,s.hpi5Period,s.hpi10Period].forEach(function(q){if(!/^\d{4}Q[1-4]$/.test(q)) throw new Error('季度格式無效。');});
  if(s.hpi5Period!==String(Number(s.hpiPeriod.slice(0,4))-5)+s.hpiPeriod.slice(4)||s.hpi10Period!==String(Number(s.hpiPeriod.slice(0,4))-10)+s.hpiPeriod.slice(4)) throw new Error('HPI 比較期間不一致。');
  var cities={}, symbols={};
  s.houses.forEach(function(r){
    if(['臺北市','新北市','桃園市','臺中市','臺南市','高雄市'].indexOf(r.city)<0||cities[r.city]) throw new Error('房市城市重複或無效。');
    cities[r.city]=true;
    ['existing','presale','hpi','hpi5','hpi10'].forEach(function(k){if(typeof r[k]!=='number'||!Number.isFinite(r[k])||r[k]<=0) throw new Error('房價或 HPI 缺漏／無效：'+r.city);});
    ['existingCount','presaleCount'].forEach(function(k){if(!Number.isInteger(r[k])||r[k]<=0) throw new Error('成交筆數無效。');});
  });
  s.etfs.forEach(function(r){
    if(typeof r.symbol!=='string'||!/^\d[A-Z0-9]{3,9}$/.test(r.symbol)||symbols[r.symbol]) throw new Error('ETF 代號重複或無效。');
    symbols[r.symbol]=true;
    if(!Number.isFinite(r.first)||r.first<=0||!Number.isFinite(r.last)||r.last<=0||!Number.isInteger(r.observations)||r.observations<240) throw new Error('ETF 價格或筆數無效。');
  });
}

function runLiveChecks() {
  var c = listChoices(), d = c.defaults;
  var p={snapshotId:c.snapshotId,city:d.city,etf:d.etf,transactionType:d.transactionType,scenario:d.scenario,years:d.years,monthly:d.monthly,downPaymentRatio:d.downPaymentPercent/100,returnMode:d.returnMode,annualReturnPercent:d.annualReturnPercent,houseGrowthPercent:d.houseGrowthPercent};
  var a=calculate(p);
  if (a.assets!==2400000 || !(a.downPaymentTarget>0)) throw new Error('基準試算檢查失敗。');
  p.downPaymentRatio=.4;
  if (Math.abs(calculate(p).downPaymentTarget-2*a.downPaymentTarget)>.01) throw new Error('比例連動失敗。');
  if (Math.abs(futureValue_(1000,0,1)-12000)>.000001) throw new Error('零報酬失敗。');
  var report={version:CALC_VERSION_,mode:'LIVE',snapshotId:c.snapshotId,queriedAt:c.queriedAt,checksPassed:3,message:'API 讀取與基本計算成功；仍需核對 SQL 結果與網頁操作。'};
  console.log(JSON.stringify(report)); return report;
}
