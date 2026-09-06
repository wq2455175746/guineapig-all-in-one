package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"
)

// TokenTTL 用户会话 Token 有效期
const TokenTTL = 30 * 24 * time.Hour

// IssueUserToken 签发 HMAC-SHA256 签名的用户会话 Token。
// 格式: base64url(userID:expiryUnix) + "." + base64url(hmac-sha256(secret, payload))
func IssueUserToken(secret string, userID int64, ttl time.Duration) (string, error) {
	if secret == "" {
		return "", errors.New("鉴权密钥未配置（JWT_SECRET）")
	}
	if userID <= 0 {
		return "", errors.New("userID 无效")
	}

	expiry := time.Now().Add(ttl).Unix()
	payload := fmt.Sprintf("%d:%d", userID, expiry)

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(payload))
	sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))

	return base64.RawURLEncoding.EncodeToString([]byte(payload)) + "." + sig, nil
}

// ParseUserToken 校验并解析用户会话 Token，返回其中的 userID。
// 校验 HMAC 签名与过期时间。
func ParseUserToken(secret, token string) (int64, error) {
	if secret == "" {
		return 0, errors.New("鉴权密钥未配置（JWT_SECRET）")
	}
	if token == "" {
		return 0, errors.New("缺少用户 Token")
	}

	parts := strings.SplitN(token, ".", 2)
	if len(parts) != 2 {
		return 0, errors.New("Token 格式错误")
	}

	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return 0, errors.New("Token 载荷格式错误")
	}

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payloadBytes)
	expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(parts[1])) {
		return 0, errors.New("Token 签名无效")
	}

	var userID, expiry int64
	if _, err := fmt.Sscanf(string(payloadBytes), "%d:%d", &userID, &expiry); err != nil {
		return 0, errors.New("Token 载荷解析失败")
	}
	if time.Now().Unix() > expiry {
		return 0, errors.New("Token 已过期")
	}
	if userID <= 0 {
		return 0, errors.New("Token 用户无效")
	}

	return userID, nil
}
