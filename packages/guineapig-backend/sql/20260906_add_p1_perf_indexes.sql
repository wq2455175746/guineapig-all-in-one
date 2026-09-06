-- P1 性能/可用性：高频查询补索引（消除 N+1 扫描与 UPSERT 退化）
-- 覆盖 chat_messages 会话查询、chat_otel UPSERT 唯一键、属主+软删除过滤、登录按哈希 key 匹配

-- chat_messages: 按会话加载消息（历史/上下文构建）
ALTER TABLE `chat_messages`
  ADD INDEX `idx_conversation_id` (`conversation_id`);

-- chat_otel: UPSERT 唯一键（user_id, name, stat_date, type）。
-- UpsertCount 依赖 ON DUPLICATE KEY UPDATE，缺少唯一键时 UPSERT 会退化为 INSERT 造成重复。
-- 先清理历史重复（保留 id 最小一条），确保唯一键可创建。
DELETE t1 FROM `chat_otel` t1
  INNER JOIN `chat_otel` t2
    ON t1.user_id = t2.user_id
   AND t1.name = t2.name
   AND t1.stat_date = t2.stat_date
   AND t1.type = t2.type
   AND t1.id > t2.id;

ALTER TABLE `chat_otel`
  ADD UNIQUE KEY `uk_user_name_statdate_type` (`user_id`, `name`, `stat_date`, `type`);

-- res_files: 属主过滤 + 软删除（列表/校验）
ALTER TABLE `res_files`
  ADD INDEX `idx_user_deleted` (`user_id`, `deleted_at`);

-- chat_memory: 属主过滤 + 软删除（记忆列表/场景记忆加载）
ALTER TABLE `chat_memory`
  ADD INDEX `idx_user_deleted` (`user_id`, `deleted_at`);

-- user_apikey: 登录时按哈希后的 api_key 精确匹配
ALTER TABLE `user_apikey`
  ADD INDEX `idx_api_key` (`api_key`);

-- user_aimodel: 属主过滤 + 软删除（模型列表/默认模型）
ALTER TABLE `user_aimodel`
  ADD INDEX `idx_user_deleted` (`user_id`, `deleted_at`);