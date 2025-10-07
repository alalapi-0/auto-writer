-- AutoWriter Text 数据库结构定义

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    work_title TEXT,
    voice TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    keyword_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);

-- 为 (role_id, keyword_id, created_at) 建立复合索引以提升检索
CREATE INDEX IF NOT EXISTS idx_articles_role_keyword_created_at
    ON articles(role_id, keyword_id, created_at);

CREATE TABLE IF NOT EXISTS pair_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    keyword_id INTEGER NOT NULL,
    used_at DATETIME NOT NULL,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);

-- 全局唯一索引由业务层按需创建/删除（见 ensure_pair_usage_scope）
CREATE INDEX IF NOT EXISTS idx_pair_usage_lookup ON pair_usage(role_id, keyword_id, used_at);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER,
    keyword_id INTEGER,
    status TEXT NOT NULL,
    message TEXT,
    logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (keyword_id) REFERENCES keywords(id)
);
