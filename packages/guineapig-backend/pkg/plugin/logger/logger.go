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

func Infof(msg string, a ...interface{}) {
	if log != nil {
		log.Info(fmt.Sprintf(msg, a...))
	}
}

func Warnf(msg string, a ...interface{}) {
	if log != nil {
		log.Warn(fmt.Sprintf(msg, a...))
	}
}

func Errorf(msg string, a ...interface{}) {
	if log != nil {
		log.Error(fmt.Sprintf(msg, a...))
	}
}

func InfoReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Info(fmt.Sprintf(msg, a...))
	}
}

func ErrorReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Error(fmt.Sprintf(msg, a...))
	}
}

func WarnReqIdf(ctx context.Context, msg string, a ...interface{}) {
	if log != nil {
		requestId := cast.ToString(ctx.Value("requestId"))
		log.With(zap.String("traceId", requestId)).Warn(fmt.Sprintf(msg, a...))
	}
}
