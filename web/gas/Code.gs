/**
 * 六都頭期款試算網頁。
 * 部署：Apps Script → 專案設定 → 指令碼內容，新增
 *   MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD
 * 帳號用 etfgoal。部署 → 新增部署 → 網頁應用程式，
 * 執行身分選自己，存取權選任何人。
 */

var CONSERVATIVE_RETURN = 0.07;

function doGet() {
  return HtmlService.createHtmlOutputFromFile("Index")
    .setTitle("ETF 頭期款試算")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function listChoices() {
  var conn = openConn_("etf");
  try {
    var etfs = query_(conn, "SELECT stock_id, ROUND(cagr * 100, 2) AS cagr_pct FROM etf_cagr ORDER BY stock_id");
    var cities = loadCities_(conn);
    return { etfs: etfs, cities: cities.map(function (row) { return row.city; }) };
  } finally {
    conn.close();
  }
}

function calculate(input) {
  var etf = String(input.etf || "0050");
  var city = String(input.city || "");
  var years = Number(input.years || 10);
  var monthly = Number(input.monthly || 0);
  if (!city) {
    throw new Error("請選擇城市");
  }
  if (!(years > 0)) {
    throw new Error("年數要大於 0");
  }

  var conn = openConn_("etf");
  try {
    var returns = query_(conn, "SELECT cagr FROM etf_cagr WHERE stock_id = ?", [etf]);
    if (!returns.length) {
      throw new Error("找不到這檔 ETF 的年化報酬：" + etf);
    }
    var annual = Number(returns[0].cagr);
    var cities = loadCities_(conn);
    var match = cities.filter(function (row) { return row.city === city; })[0];
    if (!match) {
      throw new Error("找不到這個城市的房價：" + city);
    }
    var target = Number(match.down_payment);
    return {
      city: city,
      etf: etf,
      period: match.period,
      source: match.source,
      housePriceWan: Number(match.house_price_wan),
      downPayment: target,
      cagrPct: Math.round(annual * 10000) / 100,
      years: years,
      monthlyNeeded: Math.round(monthlyNeeded_(target, annual, years)),
      monthlyNeededConservative: Math.round(monthlyNeeded_(target, CONSERVATIVE_RETURN, years)),
      accumulated: monthly > 0 ? Math.round(futureValue_(monthly, annual, years)) : 0,
      accumulatedConservative: monthly > 0 ? Math.round(futureValue_(monthly, CONSERVATIVE_RETURN, years)) : 0
    };
  } finally {
    conn.close();
  }
}

function loadCities_(conn) {
  var housing = openConn_("housing");
  try {
    var fromTarget = query_(housing,
      "SELECT CASE region WHEN '臺北市' THEN '台北市' WHEN '臺中市' THEN '台中市' WHEN '臺南市' THEN '台南市' ELSE region END AS city, " +
      "ROUND(house_price / 10000) AS house_price_wan, ROUND(down_payment_target) AS down_payment, " +
      "house_price_period AS period, 'down_pmt_target' AS source " +
      "FROM down_pmt_target WHERE transaction_type = ? AND scenario = ?",
      ["成屋買賣", "中性"]);
    if (fromTarget.length) {
      return fromTarget;
    }
    return query_(housing,
      "SELECT city, median_total_wan AS house_price_wan, ROUND(median_total_wan * 10000 * 0.2) AS down_payment, " +
      "period, 'city_house_price' AS source FROM city_house_price");
  } finally {
    housing.close();
  }
}

function openConn_(database) {
  var props = PropertiesService.getScriptProperties();
  var host = props.getProperty("MYSQL_HOST");
  var port = props.getProperty("MYSQL_PORT") || "3306";
  var user = props.getProperty("MYSQL_USER") || "etfgoal";
  var password = props.getProperty("MYSQL_PASSWORD");
  if (!host || !password) {
    throw new Error("尚未設定 MYSQL_HOST 和 MYSQL_PASSWORD。VM 的外部 IP 確定後，填到指令碼內容。");
  }
  var url = "jdbc:mysql://" + host + ":" + port + "/" + database + "?useSSL=false&characterEncoding=UTF-8";
  return Jdbc.getConnection(url, user, password);
}

function query_(conn, sql, params) {
  var stmt = params && params.length ? conn.prepareStatement(sql) : conn.createStatement();
  if (params && params.length) {
    params.forEach(function (value, index) {
      stmt.setString(index + 1, String(value));
    });
  }
  var rs = params && params.length ? stmt.executeQuery() : stmt.executeQuery(sql);
  var meta = rs.getMetaData();
  var count = meta.getColumnCount();
  var rows = [];
  while (rs.next()) {
    var row = {};
    for (var i = 1; i <= count; i++) {
      row[meta.getColumnLabel(i)] = rs.getString(i);
    }
    rows.push(row);
  }
  rs.close();
  stmt.close();
  return rows;
}

function monthlyNeeded_(target, annualReturn, years) {
  var i = annualReturn / 12;
  var n = years * 12;
  if (i === 0) {
    return target / n;
  }
  return target * i / (Math.pow(1 + i, n) - 1);
}

function futureValue_(monthly, annualReturn, years) {
  var i = annualReturn / 12;
  var n = years * 12;
  if (i === 0) {
    return monthly * n;
  }
  return monthly * ((Math.pow(1 + i, n) - 1) / i);
}
