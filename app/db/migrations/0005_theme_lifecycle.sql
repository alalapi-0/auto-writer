-- app/db/migrations/0005_theme_lifecycle.sql
-- 为主题/选题表增加软锁与使用标记字段（字段名请与实际表名对齐）
-- 假设表名为 psychology_themes，已有 used(bool) 字段；若不同，请自行替换。
ALTER TABLE psychology_themes /* TODO: 为主题表增加软锁相关字段 */
  ADD COLUMN IF NOT EXISTS locked_by_run_id TEXT /* TODO: 记录锁定的运行 ID */,
  ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP /* TODO: 记录锁定时间 */,
  ADD COLUMN IF NOT EXISTS used_at TIMESTAMP /* TODO: 记录最终使用时间 */,
  ADD COLUMN IF NOT EXISTS used_by_run_id TEXT; /* TODO: 记录消耗主题的运行 ID */

-- 推荐建立索引以加速回收与领取
CREATE INDEX IF NOT EXISTS idx_psy_themes_locked ON psychology_themes(locked_by_run_id, locked_at); /* TODO: 加速软锁查询 */
CREATE INDEX IF NOT EXISTS idx_psy_themes_used ON psychology_themes(used, used_at); /* TODO: 加速回收与领取 */
