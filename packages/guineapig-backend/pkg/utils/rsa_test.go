package utils

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// testPrivateKeyPEM 是一个用于测试的 RSA 私钥 (PKCS#1)
const testPrivateKeyPEM = `-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA1h/AvFJ/K4rancinBo6HjUvBLGH4P9TuWx+ZjWPaVfRlytha
AVzcHVB6C2LfJpu+41Wc0zjbiB/HFIkI7vpeuMdKbvjy9GOAR+yanR3KhFD4fCqM
Tmcp1zAqCF7tStrK6eVQsZUQ1oV8TgW/wrjsFuj2mdg7i615faQ7Ia8iS6yZVwIL
pnFvP8AIu6UhBBUnxnzdF25i3SXw54ars5f+Mfcrt+YaVwjanastke3LFfSJJJsJ
aMw7vPedxG/KLl9YvZeEyhLYhvduhPDwMXLLUkwIjUUC9BQDi0YQjAZzSSvYawYJ
ANHD3XXR2Vfjiz6KDu6gteaz0EHKn0VcaPP9pwIDAQABAoIBABHb0B1k3AprqFQk
mhmn5ZJZUSE8gpIAVmjvN8VdIKaunZbPeKJIdmtTfPpaIrZ7ou4fA9dyFI1D6TzD
OSWFaEUNCh47UTgk3FwjVbno9C0Y+8CPY+heHlU+RSMxl6T4npfnclV9U0wxEe8H
97hr5/T5NSgbqsu5ijp6ahwjGT8qXQmRw3Loivj3DrUQo/OSz8e9UCYOjM3do1eS
JaMC74QvShet+dboEu6vGYr5P/tYWD/vchneIsSjXEc3O1/AvWdSPdyeCQaA9Q0y
NOAI/+VaZW0sxXmKS9BQwDcKpPIx18ftemNN8zl5sa7Gg9sKpdI3yO0s9gAirURa
CH21ZpECgYEA61Rxhb+TlXHIxMx5oec0tAvi5jkDTRnFfP9WJcLUP3e96CFKqqZ1
go7+u/iQf4bKro1DkFlX/Ln8S/181zgf/zdz2voKbQrQDR2Z+Z2MBGZza5epG7Oc
gJbt7kYdpdMDXA+uaxvND1I5vCEcLdo0TmVMvYZUYeYhOKbA+MalfMUCgYEA6O57
TlL2TeJ6ay0dxerSPpecf6gOl6n4tBujZlHHp4naLQ/oFLHkGFOE/4FxA8e5kARL
S0m0qUpyJMngL/0UfQWkB4k5JR0UYuUsVwvmB+llpMENBrXYlXj0WbxEmYdzPEwb
1y8YceC2XRL9e7sKAVv/mPRIo+sIPnZxPbWzj3sCgYEA4uF20UvyLZKVzaaVXdJa
rXsINo2g8SR3khtaIu3DU61OGg5+vifeAxF55h+usER0A/WNvg1lFvL4mwq44YXq
01PTDrsich6KlxqC6HVMGLHtdT2yfFKeABuDKMXQr57RDmDP99PFz4+mugnx8QL+
itZ/NfncQMZuIQAj67UYt0ECgYAG8BN8Ibx0VWqQBqf8XSIl+x4OL1M/8TAXLTuQ
sJ7hvplg/jhLZYEFuHcdpR1Yn3pHb9lORMO8xxrfPaQPydnyX1ijYNLy6ArTZ0AK
16/iTHFaluVsbb4ltZSRl6nzaLVl9l5d6mkv+yFzZD1okgmaQMM8Kwp+12FHev+k
duUCQQKBgF5SWPnJDDOzJOEEFsy/tBfkJS9EgGAWNeyL1GPlzQ/QsdJJGVkIR8O/
0KawCq2vwYR+1l6JRj6Cz3rhaYtw530ybDHJAWnMoHQvD1RpTN4hhlILZC2fYPbN
lhbQQl/oziRMHNRnpNHVyRY40LQGsQQSGdkOTm74TqP3KHyCL8ea
-----END RSA PRIVATE KEY-----`

// testPublicKeyPEM 是对应的 RSA 公钥 (PKCS#1)
const testPublicKeyPEM = `-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEA1h/AvFJ/K4rancinBo6HjUvBLGH4P9TuWx+ZjWPaVfRlythaAVzc
HVB6C2LfJpu+41Wc0zjbiB/HFIkI7vpeuMdKbvjy9GOAR+yanR3KhFD4fCqMTmcp
1zAqCF7tStrK6eVQsZUQ1oV8TgW/wrjsFuj2mdg7i615faQ7Ia8iS6yZVwILpnFv
P8AIu6UhBBUnxnzdF25i3SXw54ars5f+Mfcrt+YaVwjanastke3LFfSJJJsJaMw7
vPedxG/KLl9YvZeEyhLYhvduhPDwMXLLUkwIjUUC9BQDi0YQjAZzSSvYawYJANHD
3XXR2Vfjiz6KDu6gteaz0EHKn0VcaPP9pwIDAQAB
-----END RSA PUBLIC KEY-----`

// parseTestPrivateKey 解析内联的测试私钥
func parseTestPrivateKey(t *testing.T) *rsa.PrivateKey {
	t.Helper()
	block, _ := pem.Decode([]byte(testPrivateKeyPEM))
	if block == nil {
		t.Fatal("failed to decode test private key PEM")
	}
	key, err := x509.ParsePKCS1PrivateKey(block.Bytes)
	if err != nil {
		t.Fatalf("failed to parse test private key: %v", err)
	}
	return key
}

// parseTestPublicKey 解析内联的测试公钥
func parseTestPublicKey(t *testing.T) *rsa.PublicKey {
	t.Helper()
	block, _ := pem.Decode([]byte(testPublicKeyPEM))
	if block == nil {
		t.Fatal("failed to decode test public key PEM")
	}
	key, err := x509.ParsePKCS1PublicKey(block.Bytes)
	if err != nil {
		t.Fatalf("failed to parse test public key: %v", err)
	}
	return key
}

// TestEncryptDecryptRoundTrip 测试加密-解密往返
func TestEncryptDecryptRoundTrip(t *testing.T) {
	privateKey := parseTestPrivateKey(t)
	publicKey := parseTestPublicKey(t)

	testCases := []struct {
		name string
		text string
	}{
		{"短文本", "hello"},
		{"中文", "你好世界"},
		{"API Key", "sk-1234567890abcdef"},
		{"特殊字符", "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"},
		{"长文本", strings.Repeat("A", 100)},
		{"包含空格的文本", "test api key with spaces"},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// 加密
			ciphertext, err := EncryptRSA(publicKey, tc.text)
			if err != nil {
				t.Fatalf("EncryptRSA failed: %v", err)
			}
			if ciphertext == "" {
				t.Fatal("ciphertext should not be empty")
			}

			// 解密
			plaintext, err := DecryptRSA(privateKey, ciphertext)
			if err != nil {
				t.Fatalf("DecryptRSA failed: %v", err)
			}
			if plaintext != tc.text {
				t.Fatalf("round trip failed: got %q, want %q", plaintext, tc.text)
			}
		})
	}
}

// TestEncryptRSA 测试加密函数
func TestEncryptRSA(t *testing.T) {
	publicKey := parseTestPublicKey(t)

	t.Run("正常加密", func(t *testing.T) {
		ciphertext, err := EncryptRSA(publicKey, "test-api-key")
		if err != nil {
			t.Fatalf("EncryptRSA failed: %v", err)
		}
		if len(ciphertext) == 0 {
			t.Fatal("ciphertext should not be empty")
		}
	})

	t.Run("空字符串", func(t *testing.T) {
		// RSA PKCS#1 v1.5 允许加密空字符串，返回有效的 base64 编码
		ciphertext, err := EncryptRSA(publicKey, "")
		if err != nil {
			t.Fatalf("EncryptRSA failed for empty string: %v", err)
		}
		if len(ciphertext) == 0 {
			t.Fatal("ciphertext should not be empty even for empty plaintext")
		}
	})
}

// TestDecryptRSA 测试解密函数
func TestDecryptRSA(t *testing.T) {
	privateKey := parseTestPrivateKey(t)

	t.Run("无效的 Base64", func(t *testing.T) {
		_, err := DecryptRSA(privateKey, "这不是base64!!!")
		if err == nil {
			t.Fatal("expected error for invalid base64, got nil")
		}
	})

	t.Run("错误的 Base64 内容（不是 RSA 密文）", func(t *testing.T) {
		// 有效的 Base64 但内容不是 RSA 加密的结果
		_, err := DecryptRSA(privateKey, "dGhpcyBpcyBub3QgYW4gUlNBLWVuY3J5cHRlZCBtZXNzYWdl")
		if err == nil {
			t.Fatal("expected error for non-RSA ciphertext, got nil")
		}
	})

	t.Run("空字符串", func(t *testing.T) {
		_, err := DecryptRSA(privateKey, "")
		if err == nil {
			t.Fatal("expected error for empty ciphertext, got nil")
		}
	})
}

// TestLoadPrivateKey 测试从文件加载私钥
func TestLoadPrivateKey(t *testing.T) {
	// 使用内联 PEM 临时文件测试
	tmpDir := t.TempDir()
	keyPath := filepath.Join(tmpDir, "private.key")

	if err := os.WriteFile(keyPath, []byte(testPrivateKeyPEM), 0600); err != nil {
		t.Fatalf("failed to write temp key file: %v", err)
	}

	t.Run("加载有效私钥文件", func(t *testing.T) {
		key, err := LoadPrivateKey(keyPath)
		if err != nil {
			t.Fatalf("LoadPrivateKey failed: %v", err)
		}
		if key == nil {
			t.Fatal("key should not be nil")
		}
	})

	t.Run("文件不存在", func(t *testing.T) {
		_, err := LoadPrivateKey("/tmp/nonexistent_private.key")
		if err == nil {
			t.Fatal("expected error for nonexistent file, got nil")
		}
	})

	t.Run("无效 PEM 文件", func(t *testing.T) {
		badPath := filepath.Join(tmpDir, "bad.key")
		if err := os.WriteFile(badPath, []byte("not a pem file"), 0600); err != nil {
			t.Fatal(err)
		}
		_, err := LoadPrivateKey(badPath)
		if err == nil {
			t.Fatal("expected error for invalid PEM, got nil")
		}
	})
}

// TestLoadPublicKey 测试从文件加载公钥
func TestLoadPublicKey(t *testing.T) {
	tmpDir := t.TempDir()
	keyPath := filepath.Join(tmpDir, "public.key")

	if err := os.WriteFile(keyPath, []byte(testPublicKeyPEM), 0644); err != nil {
		t.Fatalf("failed to write temp key file: %v", err)
	}

	t.Run("加载有效公钥文件", func(t *testing.T) {
		key, err := LoadPublicKey(keyPath)
		if err != nil {
			t.Fatalf("LoadPublicKey failed: %v", err)
		}
		if key == nil {
			t.Fatal("key should not be nil")
		}
	})

	t.Run("文件不存在", func(t *testing.T) {
		_, err := LoadPublicKey("/tmp/nonexistent_public.key")
		if err == nil {
			t.Fatal("expected error for nonexistent file, got nil")
		}
	})

	t.Run("无效 PEM 文件", func(t *testing.T) {
		badPath := filepath.Join(tmpDir, "bad.key")
		if err := os.WriteFile(badPath, []byte("not a pem file"), 0644); err != nil {
			t.Fatal(err)
		}
		_, err := LoadPublicKey(badPath)
		if err == nil {
			t.Fatal("expected error for invalid PEM, got nil")
		}
	})
}

// TestEncryptDecryptLargeData 测试加密时对大数据的限制（RSA 密钥长度限制）
func TestEncryptDecryptLargeData(t *testing.T) {
	publicKey := parseTestPublicKey(t)

	// 2048-bit RSA 密钥最大加密长度 = 2048/8 - 11 = 245 字节
	t.Run("超过最大加密长度", func(t *testing.T) {
		largeText := strings.Repeat("B", 246)
		_, err := EncryptRSA(publicKey, largeText)
		if err == nil {
			t.Fatal("expected error for data exceeding RSA key size limit, got nil")
		}
	})

	t.Run("刚好在最大长度内", func(t *testing.T) {
		// 245 字节应该可以加密（PKCS#1 v1.5 最大明文 = keySize/8 - 11）
		maxText := strings.Repeat("C", 245)
		ciphertext, err := EncryptRSA(publicKey, maxText)
		if err != nil {
			t.Fatalf("EncryptRSA failed for max-length data: %v", err)
		}
		if len(ciphertext) == 0 {
			t.Fatal("ciphertext should not be empty")
		}
	})
}

// TestLoadPrivateKeyFromRealFile 使用项目中的实际私钥文件测试加载
func TestLoadPrivateKeyFromRealFile(t *testing.T) {
	// 查找项目根目录下的私钥文件
	keyPaths := []string{
		"../../private.key",                // 从 pkg/utils/ 到 backend 根目录
		"../../../private.key",             // 深度探索
	}

	var found bool
	for _, p := range keyPaths {
		if _, err := os.Stat(p); err == nil {
			key, err := LoadPrivateKey(p)
			if err != nil {
				t.Fatalf("LoadPrivateKey(%s) failed: %v", p, err)
			}
			if key == nil {
				t.Fatal("key should not be nil")
			}
			found = true
			break
		}
	}

	if !found {
		t.Skip("no private.key file found, skipping real file test")
	}
}

// TestGenerateKeyAndRoundTrip 测试生成新密钥并完成加解密往返
func TestGenerateKeyAndRoundTrip(t *testing.T) {
	// 生成一个 1024 位密钥（测试用，更快）
	privateKey, err := rsa.GenerateKey(rand.Reader, 1024)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}
	publicKey := &privateKey.PublicKey

	plaintext := "test-generate-key-987654"
	ciphertext, err := EncryptRSA(publicKey, plaintext)
	if err != nil {
		t.Fatalf("EncryptRSA failed: %v", err)
	}

	decrypted, err := DecryptRSA(privateKey, ciphertext)
	if err != nil {
		t.Fatalf("DecryptRSA failed: %v", err)
	}

	if decrypted != plaintext {
		t.Fatalf("round trip failed: got %q, want %q", decrypted, plaintext)
	}
}
