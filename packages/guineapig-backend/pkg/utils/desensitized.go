package utils

import (
	"strings"
)

// Email 对电子邮件地址进行脱敏
func Email(email string) string {
	if strings.TrimSpace(email) == "" {
		return ""
	}

	atIndex := strings.Index(email, "@")
	if atIndex <= 1 { // @在第一个字符或之前，或者没有@
		return email
	}

	// 隐藏从第1个字符(索引1)到@前的所有字符
	hidden := email[:1] + strings.Repeat("*", atIndex-1) + email[atIndex:]
	return hidden
}

// NickName 对用户名进行脱敏
// 例如: 张三 -> 张*，张三丰 -> 张*丰
func NickName(name string) string {
	runes := []rune(name)
	length := len(runes)

	switch {
	case length <= 1:
		return "*"
	case length == 2:
		return string(runes[0]) + "*"
	default:
		return string(runes[0]) + strings.Repeat("*", length-2) + string(runes[length-1])
	}
}
