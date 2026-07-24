-- chat_conversations 表增加消息来源和外部平台会话ID字段
-- 用于支持 IM Bot 多平台消息来源标识

ALTER TABLE `chat_conversations`
  ADD COLUMN `source`      VARCHAR(32)  NOT NULL DEFAULT 'client'
    COMMENT '消息来源: client-客户端, feishu-飞书, wechat-企业微信, dingtalk-钉钉',
  ADD COLUMN `ext_chat_id` VARCHAR(128) NOT NULL DEFAULT ''
    COMMENT '外部IM平台会话ID（用于防重复创建会话）',
  ADD INDEX `idx_source_extchat` (`source`, `ext_chat_id`);
