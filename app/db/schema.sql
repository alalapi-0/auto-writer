-- 数据库建表语句，兼容 SQLite 与 PostgreSQL
CREATE TABLE IF NOT EXISTS articles ( -- 存储文章正文与标题
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
    title VARCHAR(255) NOT NULL, -- 文章标题，用于去重
    content TEXT NOT NULL, -- 文章正文内容
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP -- 创建时间戳
);

CREATE TABLE IF NOT EXISTS keywords ( -- 存储文章关键词
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE, -- 关联文章并随之删除
    keyword VARCHAR(128) NOT NULL -- 关键词文本
);

CREATE TABLE IF NOT EXISTS runs ( -- 记录每次运行状态
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自增主键
    article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL, -- 关联文章，文章删除时置空
    status VARCHAR(32) NOT NULL, -- 运行状态 success/failed 等
    detail TEXT, -- 运行详情或错误信息
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP -- 记录创建时间
);
