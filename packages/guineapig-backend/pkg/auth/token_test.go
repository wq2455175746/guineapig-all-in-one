package auth

import (
	"strings"
	"testing"
	"time"
)

func TestIssueAndParseToken(t *testing.T) {
	secret := "test-secret"
	userID := int64(42)

	token, err := IssueUserToken(secret, userID, time.Hour)
	if err != nil {
		t.Fatalf("IssueUserToken failed: %v", err)
	}
	if token == "" {
		t.Fatal("token should not be empty")
	}

	got, err := ParseUserToken(secret, token)
	if err != nil {
		t.Fatalf("ParseUserToken failed: %v", err)
	}
	if got != userID {
		t.Fatalf("userID mismatch: got %d, want %d", got, userID)
	}
}

func TestParseTokenRejectsTampered(t *testing.T) {
	secret := "test-secret"
	token, err := IssueUserToken(secret, 7, time.Hour)
	if err != nil {
		t.Fatalf("IssueUserToken failed: %v", err)
	}

	// 篡改 payload（改成另一个 userID）
	parts := strings.SplitN(token, ".", 2)
	tampered := strings.ReplaceAll(parts[0], "7:", "99:")
	if tampered == parts[0] {
		t.Log("payload 不含可直接替换的 userID，跳过 tamper payload 用例")
	} else {
		bad := tampered + "." + parts[1]
		if _, err := ParseUserToken(secret, bad); err == nil {
			t.Fatal("expected error for tampered payload, got nil")
		}
	}

	// 篡改签名
	bad := parts[0] + "." + "Zm9vYmFyYmF6"
	if _, err := ParseUserToken(secret, bad); err == nil {
		t.Fatal("expected error for tampered signature, got nil")
	}

	// 错误密钥
	if _, err := ParseUserToken("other-secret", token); err == nil {
		t.Fatal("expected error for wrong secret, got nil")
	}

	// 空 token
	if _, err := ParseUserToken(secret, ""); err == nil {
		t.Fatal("expected error for empty token, got nil")
	}

	// 非法格式
	if _, err := ParseUserToken(secret, "no-dot-format"); err == nil {
		t.Fatal("expected error for invalid format, got nil")
	}
}

func TestParseTokenExpired(t *testing.T) {
	secret := "test-secret"
	token, err := IssueUserToken(secret, 1, -time.Minute)
	if err != nil {
		t.Fatalf("IssueUserToken failed: %v", err)
	}
	if _, err := ParseUserToken(secret, token); err == nil {
		t.Fatal("expected error for expired token, got nil")
	}
}

func TestIssueTokenWithoutSecret(t *testing.T) {
	if _, err := IssueUserToken("", 1, time.Hour); err == nil {
		t.Fatal("expected error for empty secret, got nil")
	}
}

func TestParseTokenWithoutSecret(t *testing.T) {
	if _, err := ParseUserToken("", "abc.def"); err == nil {
		t.Fatal("expected error for empty secret, got nil")
	}
}

func TestIssueTokenInvalidUser(t *testing.T) {
	if _, err := IssueUserToken("s", 0, time.Hour); err == nil {
		t.Fatal("expected error for userID<=0, got nil")
	}
}
