-- 被動式 ETF 資料庫結構（對應課程 15~20：DDL / DML / PyMySQL）
-- 用法：
--   CREATE DATABASE IF NOT EXISTS etf DEFAULT CHARACTER SET utf8mb4;
--   USE etf;
--   SOURCE schema.sql;

-- 1) 每日還原收盤價（團隊定案欄位：date, stock_id, adj_close）
--    註：date 是保留字，用反引號 `date` 包起來
CREATE TABLE IF NOT EXISTS etf_price (
    `date`     DATE         NOT NULL,             -- 交易日
    stock_id   VARCHAR(16)  NOT NULL,             -- ETF 代號，如 0050
    adj_close  DECIMAL(12,4),                     -- 還原收盤（分割+除權息）→ 算長期報酬用
    PRIMARY KEY (stock_id, `date`)                -- 同一檔同一天只會有一筆（避免重複）
);

-- 2) 除權息紀錄（輔助表）
CREATE TABLE IF NOT EXISTS etf_dividend (
    stock_id  VARCHAR(16)   NOT NULL,
    ex_date   DATE          NOT NULL,             -- 除息日
    amount    DECIMAL(12,6) NOT NULL,             -- 每股配發金額
    PRIMARY KEY (stock_id, ex_date)
);

-- 3) 分割紀錄（輔助表；台股 ETF 常已還原，可能沒有資料）
CREATE TABLE IF NOT EXISTS etf_split (
    stock_id     VARCHAR(16) NOT NULL,
    split_date   DATE        NOT NULL,
    numerator    DECIMAL(12,4),                   -- 分割比例分子
    denominator  DECIMAL(12,4),                   -- 分割比例分母
    ratio        VARCHAR(16),                     -- 如 "4:1"
    PRIMARY KEY (stock_id, split_date)
);

-- ── 以下為 goal_calculator.py 的輸出表（給 Redash 畫 dashboard 用）──

-- 4) 各 ETF 含息年化報酬(CAGR)
CREATE TABLE IF NOT EXISTS etf_cagr (
    stock_id     VARCHAR(16)  NOT NULL,
    cagr         DECIMAL(8,5),                    -- 年化報酬，例如 0.21800 = 21.8%
    computed_at  DATETIME,                        -- 計算時間
    PRIMARY KEY (stock_id)
);

-- 5) 六都頭期款試算結果
CREATE TABLE IF NOT EXISTS goal_down_payment (
    city                         VARCHAR(16) NOT NULL,   -- 城市
    house_price_wan              INT,                    -- 房價(萬元)
    down_payment                 BIGINT,                 -- 頭期款(元)
    primary_etf                  VARCHAR(16),            -- 試算用的 ETF
    primary_return               DECIMAL(8,5),           -- 該 ETF 年化報酬
    monthly_needed_primary       BIGINT,                 -- 每月需投入(主要報酬率)
    monthly_needed_conservative  BIGINT,                 -- 每月需投入(保守報酬率)
    computed_at                  DATETIME,
    PRIMARY KEY (city)
);
