-- 2026-09-30 将 max_tokens 默认值从 8192 调整为 4096：
-- vLLM 等本地模型上下文有限，8192 会因"上下文长度+输入token"超限报 400。
-- 同时将现存 guineapig 模型（原 max_tokens=8192）下调为 4096，避免历史模型继续报错。

ALTER TABLE user_aimodel MODIFY COLUMN max_tokens INT NOT NULL DEFAULT 4096;

UPDATE user_aimodel SET max_tokens = 4096 WHERE id = 6 AND deleted_at IS NULL;