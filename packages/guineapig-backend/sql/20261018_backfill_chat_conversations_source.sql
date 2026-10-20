-- 回填 chat_conversations.source
-- 背景：客户端会话创建路径（SendChatMessage）此前未显式设置 source，
-- 导致 GORM 以空字符串写入（列默认值 'client' 未生效）。IM 平台会话
-- （feishu/wechat/dingtalk）始终显式写入 source，不受影响。
-- 将所有空 source 的会话回填为 'client'（客户端）。

UPDATE `chat_conversations` SET `source` = 'client' WHERE `source` = '';
