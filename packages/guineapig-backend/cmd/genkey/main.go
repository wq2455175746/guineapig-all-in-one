package main

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		panic(err)
	}

	projectRoot := findProjectRoot()
	if projectRoot == "" {
		panic("cannot find project root")
	}

	// 保存私钥 (PKCS#1)
	privateKeyPath := filepath.Join(projectRoot, "packages/guineapig-backend", "private.key")
	if err := savePrivateKey(privateKey, privateKeyPath); err != nil {
		panic(err)
	}
	fmt.Printf("私钥已生成: %s\n", privateKeyPath)

	// 保存公钥
	publicKeyPath := filepath.Join(projectRoot, "packages/guineapig-client", "public.key")
	if err := savePublicKey(&privateKey.PublicKey, publicKeyPath); err != nil {
		panic(err)
	}
	fmt.Printf("公钥已生成: %s\n", publicKeyPath)
}

func savePrivateKey(key *rsa.PrivateKey, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	block := &pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(key),
	}
	return pem.Encode(f, block)
}

func savePublicKey(key *rsa.PublicKey, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	block := &pem.Block{
		Type:  "RSA PUBLIC KEY",
		Bytes: x509.MarshalPKCS1PublicKey(key),
	}
	return pem.Encode(f, block)
}

func findProjectRoot() string {
	dir, err := os.Getwd()
	if err != nil {
		return ""
	}
	for {
		// 检查当前目录下是否有 go.mod (表示当前是 Go 模块根目录)
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			// 检查父目录是否包含 packages 结构
			parent := filepath.Dir(dir)
			if _, err := os.Stat(filepath.Join(parent, "packages", "guineapig-backend", "go.mod")); err == nil {
				return parent
			}
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return ""
		}
		dir = parent
	}
}
