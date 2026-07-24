package logger

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"os"
)

func Init() *zap.Logger {
	// 创建一个 logger 实例
	encoderConfig := zapcore.EncoderConfig{
		TimeKey:        "timestamp",
		LevelKey:       "level",
		NameKey:        "logger",
		CallerKey:      "logger",
		MessageKey:     "message",
		StacktraceKey:  "stacktrace",
		LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    zapcore.CapitalLevelEncoder, // 设置日志级别为大写
		EncodeTime:     zapcore.ISO8601TimeEncoder,  // 设置时间格式
		EncodeDuration: zapcore.StringDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	}

	// 构建 zapcore.Core
	core := zapcore.NewCore(
		zapcore.NewJSONEncoder(encoderConfig),
		zapcore.AddSync(zapcore.Lock(os.Stdout)),
		zap.InfoLevel, // 日志级别
	)

	log := zap.New(core, zap.AddCaller()).With(zap.String("app", "guineapig"))
	// 将 logger 实例传递到其他包
	SetLogger(log)

	return log
}
