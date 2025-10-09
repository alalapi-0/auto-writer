-- 去重闭环结构化约束迁移脚本
-- 为 articles 表新增签名、实体归一化字段及唯一索引
ALTER TABLE articles ADD COLUMN IF NOT EXISTS title_signature TEXT; -- 新增标题归一化签名列
ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_signature TEXT; -- 新增正文归一化签名列
ALTER TABLE articles ADD COLUMN IF NOT EXISTS role_slug TEXT; -- 新增角色归一化标识列
ALTER TABLE articles ADD COLUMN IF NOT EXISTS work_slug TEXT; -- 新增作品归一化标识列
ALTER TABLE articles ADD COLUMN IF NOT EXISTS psych_keyword TEXT; -- 新增心理学关键词归一化列
ALTER TABLE articles ADD COLUMN IF NOT EXISTS lang TEXT DEFAULT 'zh'; -- 新增语言代码列并设置默认值
ALTER TABLE articles ADD COLUMN IF NOT EXISTS meta JSON; -- 新增扩展元数据列
CREATE UNIQUE INDEX IF NOT EXISTS uq_articles_combo_day ON articles(role_slug, work_slug, psych_keyword, lang, date(created_at)); -- 同日角色作品关键词语言组合唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_articles_content_sig ON articles(content_signature) WHERE content_signature IS NOT NULL; -- 正文签名唯一索引避免完全重复
CREATE INDEX IF NOT EXISTS ix_articles_title_sig ON articles(title_signature); -- 标题签名普通索引用于巡检
-- 为 used_pairs 表补充归一化列与时间戳
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS role_slug TEXT; -- 新增角色归一化列
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS work_slug TEXT; -- 新增作品归一化列
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS psych_keyword TEXT; -- 新增心理学关键词归一化列
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS lang TEXT DEFAULT 'zh'; -- 新增语言代码列
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS first_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP; -- 新增首次使用时间
ALTER TABLE used_pairs ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP; -- 新增最近使用时间
CREATE UNIQUE INDEX IF NOT EXISTS uq_used_pairs_combo ON used_pairs(role_slug, work_slug, psych_keyword, lang); -- used_pairs 组合唯一索引
-- 平台日志补充唯一约束与状态字段
ALTER TABLE platform_logs ADD COLUMN IF NOT EXISTS target_id TEXT; -- 新增平台返回目标 ID 列
ALTER TABLE platform_logs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'; -- 新增状态列
CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_logs_article_platform ON platform_logs(article_id, platform); -- 同平台文章唯一记录
CREATE INDEX IF NOT EXISTS ix_platform_logs_status ON platform_logs(status); -- 平台日志状态筛选索引
-- 创建 taxonomy 规范化字典表
CREATE TABLE IF NOT EXISTS taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 主键自增
    kind TEXT NOT NULL, -- 字典类型字段
    slug TEXT NOT NULL, -- 规范化标识
    display_name TEXT NOT NULL -- 显示名称
); -- 结束表定义
CREATE UNIQUE INDEX IF NOT EXISTS uq_taxonomy_kind_slug ON taxonomy(kind, slug); -- 字典类型与标识唯一索引
