package constant

import "encoding/json"

type ResponseErrMsg struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

func FormatErrMsg(code int, msg string) string {
	errMsg := ResponseErrMsg{
		Code:    code,
		Message: msg,
	}
	msgData, _ := json.Marshal(errMsg)
	return string(msgData)
}

const (
	SystemErr = 500001 // 系统错误
	ParamErr  = 500002 // 参数错误
)

const (
	SystemErrMsg = "系统错误，试试其他功能"
	ParamErrMsg  = "参数错误，请联系管理员"
)
