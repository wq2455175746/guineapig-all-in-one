-- user_aimodel 表增加 max_tokens 字段
-- 模型最大 token 数，Go 模型 UserAiModel.MaxTokens 默认 8192
-- 旧表缺少该列导致 Create/Update 报 Error 1054 Unknown column 'max_tokens'

ALTER TABLE `user_aimodel`
  ADD COLUMN `max_tokens` INT NOT NULL DEFAULT 8192 COMMENT '模型最大 token 数';