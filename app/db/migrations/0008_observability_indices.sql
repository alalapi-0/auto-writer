-- -*- coding: utf-8 -*-  # 指定文件编码
-- 为可观测性与重试查询补充索引，提升常用检索性能。  # 文件说明

BEGIN;  -- 开启事务，确保执行失败时整体回滚

CREATE INDEX IF NOT EXISTS idx_platform_logs_article_platform  -- 为平台日志按文章+平台建立复合索引
ON platform_logs(article_id, platform);

CREATE INDEX IF NOT EXISTS idx_platform_logs_next_retry_observe  -- 为重试扫描建立 next_retry_at 索引
ON platform_logs(next_retry_at);

CREATE INDEX IF NOT EXISTS idx_runs_status_updated  -- 加速按状态与更新时间筛选运行记录
ON runs(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_articles_created_at  -- 加速文章按创建时间统计
ON articles(created_at);

CREATE INDEX IF NOT EXISTS idx_keywords_keyword_plain  -- 加速关键词精确查询
ON keywords(keyword);

CREATE INDEX IF NOT EXISTS idx_psy_themes_role_work  -- 加速主题角色与作品组合检索
ON psychology_themes(character_name, show_name);

COMMIT;  -- 提交事务
