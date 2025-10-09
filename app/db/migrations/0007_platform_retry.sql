-- 为平台投递日志增加重试与审计字段
ALTER TABLE platform_logs
  ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE platform_logs
  ADD COLUMN IF NOT EXISTS last_error TEXT;
ALTER TABLE platform_logs
  ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP;
ALTER TABLE platform_logs
  ADD COLUMN IF NOT EXISTS payload JSON;
-- 典型状态索引：pending / prepared / queued / success / failed / skipped
CREATE INDEX IF NOT EXISTS ix_platform_logs_next_retry
ON platform_logs(next_retry_at);
-- 若 runs 表不存在则创建运行状态机表
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_run_id ON runs(run_id);
-- 若 runs 表已存在则补充 error 与 updated_at 字段
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
