package utils

import (
	"strconv"
	"strings"
)

// KeyOwnerUserID 从 S3 对象 key 中提取属主用户 id。
// 上传 key 统一形如 `{prefix}/{user_id}/{date}/{name}`（见 service/s3.go 中
// audio/asr、skills、resources 前缀），user_id 恒为第二段。
// 解析失败或格式不符返回 0（表示无法判定归属，调用方应按越权处理）。
func KeyOwnerUserID(key string) int64 {
	parts := strings.Split(key, "/")
	if len(parts) < 2 {
		return 0
	}
	uid, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil {
		return 0
	}
	return uid
}
