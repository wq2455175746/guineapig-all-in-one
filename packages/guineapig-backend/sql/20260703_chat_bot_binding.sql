CREATE TABLE `guineapig`.`chat_bot_binding` (
  `id`           bigint UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键id',
  `user_id`      bigint NOT NULL COMMENT '系统用户ID',
  `platform`     VARCHAR(32) NOT NULL COMMENT '平台标识，feishu-飞书，wechat-微信，dingtalk-钉钉',
  `app_id`       VARCHAR(128) NOT NULL COMMENT '平台应用AppID',
  `app_secret`   VARCHAR(512) NOT NULL COMMENT '平台AppSecret（RSA加密后存储）',
  `tenant_key`   VARCHAR(128) DEFAULT '' COMMENT '平台租户标识（飞书tenant_key / 企微corp_id）',
  `bot_status`   TINYINT NOT NULL DEFAULT 0 COMMENT 'bot连接状态，0-未连接，1-已连接，2-连接失败',
  `bot_name`     VARCHAR(128) DEFAULT '' COMMENT '机器人别名/备注名',
  `extra_config` JSON NULL COMMENT '平台扩展配置，JSON格式灵活存储各平台私有配置',
  `description`  VARCHAR(512) DEFAULT '' COMMENT '绑定备注说明',
  `created_by`   VARCHAR(255) DEFAULT NULL COMMENT '创建者',
  `created_at`   timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`   timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  UNIQUE KEY `uk_user_platform` (`user_id`, `platform`) COMMENT '一个用户在每个平台只能绑定一个bot',
  INDEX `idx_platform_tenant` (`platform`, `tenant_key`) COMMENT '通过平台+租户查找绑定关系',
  INDEX `idx_user_id` (`user_id`) COMMENT '按用户查询绑定列表'
) ENGINE=InnoDB AUTO_INCREMENT=0 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IM平台Bot绑定表';
