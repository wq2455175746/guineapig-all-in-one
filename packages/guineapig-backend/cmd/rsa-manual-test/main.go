package main

import (
	"bufio"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"guineapig/pkg/utils"
)

// keyPaths 候选密钥文件路径（相对于项目根目录或当前目录）
var keyPaths = []struct {
	private string
	public  string
}{
	// 从项目根目录（monorepo 结构）
	{"packages/guineapig-backend/private.key", "packages/guineapig-client/public/public.key"},
	// 从 packages/guineapig-backend 目录
	{"private.key", "../../packages/guineapig-client/public/public.key"},
	// 从项目根目录的直接子目录
	{"../private.key", "../guineapig-client/public/public.key"},
}

func main() {
	// 命令行参数
	privateKeyPath := flag.String("key", "", "RSA 私钥文件路径（默认自动查找）")
	mode := flag.String("mode", "decrypt", "操作模式: decrypt（解密）| encrypt（加密）")
	publicKeyPath := flag.String("pub", "", "RSA 公钥文件路径（加密模式时使用，默认自动查找）")
	text := flag.String("text", "", "要解密/加密的文本（可选，不指定则从 stdin 读取）")
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, `RSA 加解密手动测试工具

用法:
  %s [选项]

选项:
`, os.Args[0])
		flag.PrintDefaults()
		fmt.Fprintf(os.Stderr, `
示例:
  # 解密给定的 Base64 密文
  %[1]s --mode decrypt --text "base64_ciphertext_here"

  # 从管道输入解密
  echo "base64_ciphertext_here" | %[1]s --mode decrypt

  # 加密明文（需要指定公钥路径）
  %[1]s --mode encrypt --pub /path/to/public.key --text "api_key_value"

  # 自动查找密钥文件（从项目根目录）
  %[1]s --mode decrypt --text "base64_ciphertext"
`, os.Args[0])
	}
	flag.Parse()

	// 获取要处理的文本
	input := *text
	if input == "" {
		// 从 stdin 读取
		scanner := bufio.NewScanner(os.Stdin)
		var lines []string
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line != "" {
				lines = append(lines, line)
			}
		}
		if err := scanner.Err(); err != nil {
			fmt.Fprintf(os.Stderr, "读取输入失败: %v\n", err)
			os.Exit(1)
		}
		if len(lines) == 0 {
			flag.Usage()
			os.Exit(1)
		}
		input = lines[0]
	}

	switch *mode {
	case "decrypt":
		runDecrypt(*privateKeyPath, input)
	case "encrypt":
		runEncrypt(*publicKeyPath, *privateKeyPath, input)
	default:
		fmt.Fprintf(os.Stderr, "未知模式: %s（仅支持 decrypt/encrypt）\n", *mode)
		os.Exit(1)
	}
}

// findKeyFile 在多个候选路径中查找第一个存在的文件
func findKeyFile(candidates []string) string {
	for _, p := range candidates {
		abs, err := filepath.Abs(p)
		if err != nil {
			continue
		}
		if _, err := os.Stat(abs); err == nil {
			return abs
		}
	}
	return ""
}

func resolvePrivateKeyPaths() []string {
	paths := make([]string, 0, len(keyPaths))
	for _, kp := range keyPaths {
		paths = append(paths, kp.private)
	}
	return paths
}

func resolvePublicKeyPaths() []string {
	paths := make([]string, 0, len(keyPaths))
	for _, kp := range keyPaths {
		paths = append(paths, kp.public)
	}
	return paths
}

func findDefaultPrivateKey() string {
	return findKeyFile(resolvePrivateKeyPaths())
}

func findDefaultPublicKey() string {
	return findKeyFile(resolvePublicKeyPaths())
}

func runDecrypt(keyPath, ciphertext string) {
	if keyPath == "" {
		keyPath = findDefaultPrivateKey()
	}
	if keyPath == "" {
		fmt.Fprintln(os.Stderr, "错误: 未找到私钥文件，请使用 --key 参数指定路径")
		os.Exit(1)
	}

	// 检查私钥文件是否存在
	if _, err := os.Stat(keyPath); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "错误: 私钥文件不存在: %s\n", keyPath)
		os.Exit(1)
	}

	fmt.Fprintf(os.Stderr, "加载私钥: %s\n", keyPath)
	privateKey, err := utils.LoadPrivateKey(keyPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载私钥失败: %v\n", err)
		os.Exit(1)
	}

	plaintext, err := utils.DecryptRSA(privateKey, ciphertext)
	if err != nil {
		fmt.Fprintf(os.Stderr, "解密失败: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(plaintext)
}

func runEncrypt(pubKeyPath, privKeyPath, plaintext string) {
	if pubKeyPath == "" {
		pubKeyPath = findDefaultPublicKey()
	}
	if pubKeyPath == "" {
		// 尝试从私钥提取公钥
		if privKeyPath == "" {
			privKeyPath = findDefaultPrivateKey()
		}
		if privKeyPath != "" {
			if _, err := os.Stat(privKeyPath); err == nil {
				privateKey, err := utils.LoadPrivateKey(privKeyPath)
				if err == nil {
					ciphertext, err := utils.EncryptRSA(&privateKey.PublicKey, plaintext)
					if err != nil {
						fmt.Fprintf(os.Stderr, "加密失败: %v\n", err)
						os.Exit(1)
					}
					fmt.Fprintln(os.Stderr, "（使用私钥中的公钥加密）")
					fmt.Println(ciphertext)
					return
				}
			}
		}
		fmt.Fprintln(os.Stderr, "错误: 未找到公钥文件，请使用 --pub 参数指定路径")
		os.Exit(1)
	}

	if _, err := os.Stat(pubKeyPath); os.IsNotExist(err) {
		fmt.Fprintf(os.Stderr, "错误: 公钥文件不存在: %s\n", pubKeyPath)
		os.Exit(1)
	}

	fmt.Fprintf(os.Stderr, "加载公钥: %s\n", pubKeyPath)
	publicKey, err := utils.LoadPublicKey(pubKeyPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加载公钥失败: %v\n", err)
		os.Exit(1)
	}

	ciphertext, err := utils.EncryptRSA(publicKey, plaintext)
	if err != nil {
		fmt.Fprintf(os.Stderr, "加密失败: %v\n", err)
		os.Exit(1)
	}

	fmt.Println(ciphertext)
}
