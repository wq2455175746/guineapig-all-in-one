package plugin

import (
	"context"
	"gorm.io/driver/mysql"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
	"guineapig/config"
	dbLogger "guineapig/pkg/plugin/logger"
	"time"
)

// DB sqlite 实例
var DB *gorm.DB

func SetupDB(driver, dsn string) {
	switch driver {
	case "sqlite":
		openSqlite(dsn)
	case "mysql":
		openMySQL(dsn)
	default:
		panic("unsupported db driver")
	}
}

func openSqlite(dsn string) {
	db, err := gorm.Open(sqlite.Open(dsn), &gorm.Config{})
	if err != nil {
		panic("failed to connect database")
	}
	DB = db
}

func openMySQL(dsn string) {
	cfg := &gorm.Config{}
	if config.Global.Logger.DbTrace {
		customLogger := &dbLogger.CustomLogger{}
		cfg.Logger = customLogger.LogMode(logger.Info)
	}
	db, err := gorm.Open(mysql.Open(dsn), cfg)
	if err != nil {
		panic("failed to connect database")
	}

	// 获取底层 *sql.DB 对象，配置连接池
	sqlDB, err := db.DB()
	if err != nil {
		panic("failed to get sql.DB")
	}

	// 配置连接池参数
	// 最大打开连接数（根据并发量调整）
	sqlDB.SetMaxOpenConns(100)
	// 最大空闲连接数（建议小于等于 MaxOpenConns）
	sqlDB.SetMaxIdleConns(20)
	// 连接最大生存时间（如 30 分钟）
	sqlDB.SetConnMaxLifetime(30 * time.Minute)
	// 连接最大空闲时间（如 10 分钟）
	sqlDB.SetConnMaxIdleTime(10 * time.Minute)

	// 测试连接是否有效
	if err := sqlDB.Ping(); err != nil {
		panic("ping database failed: " + err.Error())
	}

	DB = db
	dbLogger.Infof("MySQL 连接成功.")
}

func GetDB(ctx context.Context) *gorm.DB {
	return DB.WithContext(ctx)
}
