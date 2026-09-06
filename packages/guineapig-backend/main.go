package main

import (
	"context"
	"encoding/json"
	"guineapig/config"
	"guineapig/internal/router"
	"guineapig/internal/server"
	"guineapig/internal/service"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"os"
	"os/signal"
	"regexp"
	"syscall"
	"time"

	"github.com/hibiken/asynq"
	"go.uber.org/zap"
)

func main() {
	//--初始化log
	log := logger.Init()
	defer func() {
		// 确保日志写入
		_ = log.Sync()
	}()
	log.Info("hello guinea-pig server start...")

	//--解析配置文件
	conf := config.ParseConfig()
	if conf.Debug {
		// debug 模式，打印配置文件（脱敏敏感字段）
		buf, err := json.MarshalIndent(conf, "", "\t")
		if err != nil {
			panic(err)
		}
		redacted := redactSecrets(string(buf))
		logger.Infof("guinea-pig  parse config: %s", redacted)
	}

	//--安装插件
	setupPlugin(conf, log)

	//--启动 Asynq (分布式任务调度)
	redisOpt := asynq.RedisClientOpt{
		Addr:     conf.Redis.Addr,
		Password: conf.Redis.Password,
		DB:       conf.Redis.Db,
	}

	// Asynq Scheduler: 每 5 分钟入队 otel:sync 任务
	scheduler := asynq.NewScheduler(redisOpt, &asynq.SchedulerOpts{
		Logger: asynqLogger(),
	})
	if _, err := scheduler.Register("@every 5m", asynq.NewTask(service.OtelSyncTaskType, nil)); err != nil {
		logger.Errorf("注册 otel:sync 定时任务失败: %v", err)
	}
	if _, err := scheduler.Register("@every 12h", asynq.NewTask(service.MemorySummarizeTaskType, nil)); err != nil {
		logger.Errorf("注册 memory:summarize 定时任务失败: %v", err)
	}
	scheduler.Start()
	logger.Infof("[Asynq] Scheduler 已启动...")

	// Asynq Server: 消费任务
	mux := asynq.NewServeMux()
	mux.HandleFunc(service.OtelSyncTaskType, service.HandleOtelSyncTask)
	mux.HandleFunc(service.MemorySummarizeTaskType, service.HandleMemorySummarizeTask)

	serverSrv := asynq.NewServer(redisOpt, asynq.Config{
		Concurrency: 1,
		Logger:      asynqLogger(),
	})
	go func() {
		if err := serverSrv.Start(mux); err != nil {
			logger.Errorf("[Asynq] Server 启动失败: %v", err)
		}
	}()
	logger.Infof("[Asynq] Server 已启动 (concurrency=1)")

	srv := server.NewServer(conf.Debug)
	router.Register(srv.Echo)

	// 启动所有已绑定的 IM Bot 连接
	service.StartupBots(context.Background())
	// 等待 Bot 连接建立
	service.LoadBotManager().WaitForReady(10 * time.Second)

	// 启动 Echo 服务（非阻塞）
	echoDone := srv.RunAsync(conf.Port)

	// 统一信号监听：等待信号后依次关闭所有服务
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	logger.Infof("Shutting down...")

	scheduler.Shutdown()
	serverSrv.Shutdown()
	logger.Infof("Asynq Scheduler & Server 已关闭")

	srv.ShutdownEcho()
	<-echoDone
}

func setupPlugin(conf *config.Config, log *zap.Logger) {
	plugin.Init(conf, log)
}

// redactSecrets 对配置 JSON 中的敏感字段值进行脱敏，避免 debug 模式打印泄露凭据。
func redactSecrets(s string) string {
	for _, key := range []string{"source", "password", "accessKey", "secretKey"} {
		re := regexp.MustCompile(`"` + key + `":\s*"[^"]*"`)
		s = re.ReplaceAllString(s, `"`+key+`": "***"`)
	}
	return s
}

// asynqLogger 适配 Asynq 日志到 Zap
func asynqLogger() asynq.Logger {
	return &zapAsynqLogger{}
}

type zapAsynqLogger struct{}

func (l *zapAsynqLogger) Debug(args ...interface{}) {
	logger.Infof("[DEBUG] %v", args...)
}

func (l *zapAsynqLogger) Info(args ...interface{}) {
	logger.Infof("%v", args...)
}

func (l *zapAsynqLogger) Warn(args ...interface{}) {
	logger.Warnf("%v", args...)
}

func (l *zapAsynqLogger) Error(args ...interface{}) {
	logger.Errorf("%v", args...)
}

func (l *zapAsynqLogger) Fatal(args ...interface{}) {
	logger.Errorf("[FATAL] %v", args...)
}
