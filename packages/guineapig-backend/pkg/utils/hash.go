package utils

import (
	"crypto/hmac"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
)

// HMACApiKey 使用 HMAC-SHA256 对 api_key 做单向哈希（存储态），替代弱 MD5。
func HMACApiKey(secret, apiKey string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(apiKey))
	return hex.EncodeToString(mac.Sum(nil))
}

// MD5ApiKey 兼容旧数据的 MD5 单向哈希（仅用于历史 api_key 匹配）。
func MD5ApiKey(apiKey string) string {
	sum := md5.Sum([]byte(apiKey))
	return hex.EncodeToString(sum[:])
}
