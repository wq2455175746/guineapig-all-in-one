package logger

import (
	"context"
	"fmt"
	"github.com/spf13/cast"
	"go.uber.org/zap"
)

// 共享的 logger 实例
var log *zap.Logger

// SetLogger 设置 logger 实例
func SetLogger(l *zap.Logger) {
	log = l
}

// format 仅在传入参数时按 fmt 格式化；无参数时原样输出 msg，
// 避免消息内容中的 `%` 被当作格式占位符导致日志损坏（如 `%!s(MISSING)`）。
func format(msg string, a ...interface{}) string {
	if len(a) == 0 {
		return msg
	}
	return fmt.Sprintf(msg, a...)
}

func Infof(msg string, a ...interface{}) {
	if log != nil {
		log.Info(format(msg, a...))
	}
}

func Warnf(msg string, a ...interface{}) {
	if log != nil {
		log.Warn(format(msg, a...))
	}
}

func Errorf(msg string, a ...interface{}) {
	if log != nil {
		log.Error(format(msg, a...))
	}
}

func InfoReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Info(format(msg, a...))
	}
}

func ErrorReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Error(format(msg, a...))
	}
}

func WarnReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Warn(format(msg, a...))
	}
}
