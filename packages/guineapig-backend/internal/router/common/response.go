package common

import (
	"errors"
	"fmt"
	"github.com/labstack/echo/v4"
	"github.com/spf13/cast"
	"guineapig/pkg/constant"
	"guineapig/pkg/plugin/logger"
	"net/http"
)

type CustomError struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	Detail    string `json:"detail"`
	RequestId string `json:"requestId"`
}

func (e *CustomError) Error() string {
	return fmt.Sprintf("code: %d, message: %s, detail: %s", e.Code, e.Message, e.Detail)
}

// ResponseServerError code是200
func ResponseServerError(e echo.Context, err error) error {
	requestId := cast.ToString(e.Get("requestId"))
	e.Response().Header().Set(echo.HeaderXRequestID, requestId)

	var ce *CustomError
	if errors.As(err, &ce) {
		// 如果是自定义错误
		ce.RequestId = requestId
		return e.JSON(http.StatusOK, ce)
	}

	// 服务器内部错误：详情仅在服务端日志记录，客户端返回通用提示，避免泄漏 SQL/文件路径等内部信息
	if err != nil {
		logger.Errorf("[ResponseServerError] request_id=%s, err=%v", requestId, err)
	}

	return e.JSON(http.StatusOK, CustomError{
		Code:      constant.SystemErr,
		Message:   constant.SystemErrMsg,
		Detail:    constant.SystemErrMsg,
		RequestId: requestId,
	})
}

// ResponseServerCodeError code是500
func ResponseServerCodeError(e echo.Context, err error) error {
	requestId := cast.ToString(e.Get("requestId"))
	e.Response().Header().Set(echo.HeaderXRequestID, requestId)

	// 服务器内部错误：详情仅在服务端日志记录，客户端返回通用提示
	if err != nil {
		logger.Errorf("[ResponseServerCodeError] request_id=%s, err=%v", requestId, err)
	}

	return e.JSON(http.StatusInternalServerError, CustomError{
		Code:      constant.SystemErr,
		Message:   constant.SystemErrMsg,
		Detail:    constant.SystemErrMsg,
		RequestId: requestId,
	})
}

// ResponseCodeMsgError 状态码为200的 code码错误的
func ResponseCodeMsgError(e echo.Context, code int, msg string) error {
	requestId := cast.ToString(e.Get("requestId"))
	e.Response().Header().Set(echo.HeaderXRequestID, requestId)

	return e.JSON(http.StatusOK, CustomError{
		Code:      code,
		Message:   msg,
		Detail:    msg,
		RequestId: requestId,
	})
}

func ResponseOk(e echo.Context, data interface{}) error {
	requestId := cast.ToString(e.Get("requestId"))
	e.Response().Header().Set(echo.HeaderXRequestID, requestId)

	return e.JSON(http.StatusOK, map[string]interface{}{
		"code":      0,
		"message":   "success",
		"result":    data,
		"requestId": requestId,
	})
}

func ResponseParamError(e echo.Context, err error) error {
	requestId := cast.ToString(e.Get("requestId"))
	e.Response().Header().Set(echo.HeaderXRequestID, requestId)

	detail := constant.SystemErrMsg
	if err != nil {
		detail = err.Error()
	}
	return e.JSON(http.StatusOK, CustomError{
		Code:      constant.ParamErr,
		Message:   constant.ParamErrMsg,
		Detail:    detail,
		RequestId: requestId,
	})
}
