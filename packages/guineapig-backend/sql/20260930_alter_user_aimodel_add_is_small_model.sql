-- 模型增加"小模型"标记：小模型上下文注入到 user 消息，而非 system prompt
-- 0 = 大模型（默认，上下文注入 system prompt），1 = 小模型（注入 user 消息）
ALTER TABLE user_aimodel ADD COLUMN is_small_model TINYINT NOT NULL DEFAULT 0 COMMENT '是否小模型：1=小模型(上下文注入user消息)，0=大模型(注入system prompt)';