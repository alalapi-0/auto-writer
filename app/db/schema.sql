-- 数据库建表语句，覆盖 orchestrator 所需核心表结构
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL,
    work VARCHAR(128) NOT NULL,
    traits TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_character_name_work UNIQUE (name, work)
);

CREATE TABLE IF NOT EXISTS extended_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(128) NOT NULL,
    work VARCHAR(128) NOT NULL,
    traits TEXT NOT NULL,
    source VARCHAR(128),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_extended_character_name_work UNIQUE (name, work)
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword VARCHAR(128) NOT NULL,
    category VARCHAR(64),
    last_used_at TIMESTAMP,
    usage_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_keyword_value UNIQUE (keyword)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(64) NOT NULL,
    run_date DATE NOT NULL,
    planned_articles INTEGER NOT NULL,
    keywords_consumed INTEGER NOT NULL DEFAULT 0,
    keywords_added INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    metadata_path VARCHAR(255),
    result_path VARCHAR(255),
    error TEXT, -- 新增: 记录错误信息便于追踪
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 新增: 更新时间戳
    CONSTRAINT uq_run_run_id UNIQUE (run_id)
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    character_name VARCHAR(128) NOT NULL,
    work VARCHAR(128) NOT NULL,
    keyword VARCHAR(128) NOT NULL,
    title VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    content TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS platform_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    platform VARCHAR(64) NOT NULL,
    target_id TEXT, -- 新增: 平台返回的草稿 ID
    status TEXT DEFAULT 'pending', -- 新增: 统一状态字段
    ok BOOLEAN NOT NULL DEFAULT 0,
    id_or_url VARCHAR(255),
    error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0, -- 新增: 记录尝试次数
    last_error TEXT, -- 新增: 保存最近一次错误
    next_retry_at TIMESTAMP, -- 新增: 预约下次重试时间
    payload JSON, -- 新增: 序列化存档
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_platform_logs_next_retry ON platform_logs(next_retry_at); -- 新增: 便于扫描到期任务

CREATE TABLE IF NOT EXISTS used_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name VARCHAR(128) NOT NULL,
    work VARCHAR(128) NOT NULL,
    keyword VARCHAR(128) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    used_on DATE NOT NULL,
    similarity_hash VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_used_pair_unique_day UNIQUE (character_name, work, keyword, used_on)
);
