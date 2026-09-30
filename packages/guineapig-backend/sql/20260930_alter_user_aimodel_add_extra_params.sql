-- user_aimodel 表增加 extra_params 扩展参数字段
-- 存储后续新增的模型扩展字段（JSON），避免频繁 ALTER TABLE
-- Go 模型 UserAiModel.ExtraParams (*string, gorm type:json)

ALTER TABLE `user_aimodel`
  ADD COLUMN `extra_params` JSON NULL COMMENT '扩展参数，JSON格式存储后续新增字段';