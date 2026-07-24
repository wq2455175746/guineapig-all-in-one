package logger

import (
	"context"
	"gorm.io/gorm/logger"
	"time"
)

type CustomLogger struct {
	logger.Interface
}

func (c *CustomLogger) LogMode(level logger.LogLevel) logger.Interface {
	return &CustomLogger{}
}

func (c *CustomLogger) Info(ctx context.Context, msg string, data ...interface{}) {
	InfoReqIdf(ctx, msg, data...)
}

func (c *CustomLogger) Warn(ctx context.Context, msg string, data ...interface{}) {
	WarnReqIdf(ctx, msg, data...)
}

func (c *CustomLogger) Error(ctx context.Context, msg string, data ...interface{}) {
	ErrorReqIdf(ctx, msg, data...)
}

func (c *CustomLogger) Trace(ctx context.Context, begin time.Time, fc func() (string, int64), err error) {
	sql, rowsAffected := fc()
	InfoReqIdf(ctx, "[TRACE] SQL: %s, RowsAffected: %d, Duration: %v", sql, rowsAffected, time.Since(begin))
}
