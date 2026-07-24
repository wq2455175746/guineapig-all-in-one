package utils

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"os"
)

// LoadPrivateKey 从文件加载 RSA 私钥 (PKCS#1)
func LoadPrivateKey(path string) (*rsa.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	block, _ := pem.Decode(data)
	if block == nil {
		return nil, errors.New("failed to decode PEM block")
	}

	return x509.ParsePKCS1PrivateKey(block.Bytes)
}

// LoadPublicKey 从文件加载 RSA 公钥 (PKCS#1)
func LoadPublicKey(path string) (*rsa.PublicKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	block, _ := pem.Decode(data)
	if block == nil {
		return nil, errors.New("failed to decode PEM block")
	}

	return x509.ParsePKCS1PublicKey(block.Bytes)
}

// DecryptRSA 使用私钥解密 Base64 编码的 RSA 密文 (PKCS#1 v1.5)
func DecryptRSA(privateKey *rsa.PrivateKey, ciphertext string) (string, error) {
	if privateKey == nil {
		return "", errors.New("RSA 私钥为 nil，请检查配置")
	}
	cipherBytes, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", err
	}

	plainBytes, err := rsa.DecryptPKCS1v15(rand.Reader, privateKey, cipherBytes)
	if err != nil {
		return "", err
	}

	return string(plainBytes), nil
}

// EncryptRSA 使用公钥加密明文并返回 Base64 编码的密文 (PKCS#1 v1.5)
func EncryptRSA(publicKey *rsa.PublicKey, plaintext string) (string, error) {
	cipherBytes, err := rsa.EncryptPKCS1v15(rand.Reader, publicKey, []byte(plaintext))
	if err != nil {
		return "", err
	}

	return base64.StdEncoding.EncodeToString(cipherBytes), nil
}
