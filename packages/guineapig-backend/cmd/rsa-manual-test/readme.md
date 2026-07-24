# 使用命令

```
## 解密（默认模式，自动查找私钥）
echo "base64_ciphertext" | go run cmd/rsa-manual-test/main.go --mode decrypt
go run cmd/rsa-manual-test/main.go --mode decrypt --text "base64_ciphertext"

## 加密（需要公钥）
go run cmd/rsa-manual-test/main.go --mode encrypt --text "sk-test-api-key"

## 也可手动指定密钥路径
go run cmd/rsa-manual-test/main.go --mode decrypt --key /path/to/private.key --text "..."
```