package plugin

import (
	"go.uber.org/zap"
	"guineapig/config"
)

func panicIfError(err error) {
	if err != nil {
		panic(err)
	}
}

func Init(conf *config.Config, log *zap.Logger) {
	SetupDB(conf.Database.Driver, conf.Database.Source)
	SetupRedis(conf.Redis)
}
