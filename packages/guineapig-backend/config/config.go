package config

import (
	"github.com/joho/godotenv"
	"github.com/spf13/viper"
	"log"
	"os"
)

// Global 全局调用配置文件参数使用
var Global Config

type Config struct {
	Port    int    `yaml:"port" json:"port"`
	Version string `yaml:"version" json:"version"`
	Debug   bool   `yaml:"debug" json:"debug"`
	Logger  struct {
		DbTrace bool `yaml:"dbTrace" json:"dbTrace"`
	} `yaml:"logger" json:"logger"`
	Database struct {
		AutoMigrate bool   `yaml:"autoMigrate" json:"autoMigrate"`
		Driver      string `json:"driver" yaml:"driver"`
		Source      string `json:"source" yaml:"source"`
	} `yaml:"database" json:"database"`
	Redis       Redis    `yaml:"redis" json:"redis"`
	RateLimiter struct { // 限流相关配置
		Type              string         `yaml:"type" json:"type"`
		EnableConcurrency bool           `yaml:"enableConcurrency" json:"enableConcurrency"`
		Concurrency       map[string]int `yaml:"concurrency" json:"concurrency"`
		EnableQps         bool           `yaml:"enableQps" json:"enableQps"`
		Qps               map[string]int `yaml:"qps" json:"qps"`
		BotQps            int            `yaml:"botQps" json:"botQps"` // Bot 消息发送 QPS 限制（每个 Bot 实例）
	} `yaml:"rateLimiter" json:"rateLimiter"`
	CorsHosts   string `yaml:"corsHosts" json:"corsHosts"`
	CorsHeaders string `yaml:"corsHeaders" json:"corsHeaders"`
	Rsa         struct {
		PrivateKey string `yaml:"privateKey" json:"privateKey"`
	} `yaml:"rsa" json:"rsa"`
	Admin   Admin   `yaml:"admin" json:"admin"`
	S3      S3      `yaml:"s3" json:"s3"`
	AiAgent AiAgent `yaml:"aiAgent" json:"aiAgent"`
}

type Admin struct {
	Token string `yaml:"token" json:"token"`
}

type S3 struct {
	Bucket              string `yaml:"bucket" json:"bucket"`
	Region              string `yaml:"region" json:"region"`
	Endpoint            string `yaml:"endpoint" json:"endpoint"`
	AccessKey           string `yaml:"accessKey" json:"accessKey"`
	SecretKey           string `yaml:"secretKey" json:"secretKey"`
	PresignExpiryMinute int    `yaml:"presignExpiryMinute" json:"presignExpiryMinute"`
	ForcePathStyle      bool   `yaml:"forcePathStyle" json:"forcePathStyle"`
}

type AiAgent struct {
	BaseUrl string `yaml:"baseUrl" json:"baseUrl"`
}

type Redis struct {
	Db               int    `yaml:"db" json:"db"`
	Password         string `yaml:"password" json:"password"`
	Addr             string `yaml:"addr" json:"addr"`
	MasterName       string `yaml:"masterName" json:"masterName"`
	SentinelPassword string `yaml:"sentinelPassword" json:"sentinelPassword"`
}

func ParseConfig() *Config {
	// 使用godotenv加载.env文件
	if err := godotenv.Load(); err != nil {
		log.Printf("Warning: .env file not found or error loading: %v", err)
	}

	viper.SetDefault("fileDir", "./")
	// 加载主配置文件
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AutomaticEnv() // 启用自动环境变量读取

	if err := viper.ReadInConfig(); err != nil {
		panic(err)
	}

	// 解析环境变量占位符
	for _, key := range viper.AllKeys() {
		value := viper.GetString(key)
		// 使用os.ExpandEnv替换环境变量占位符
		expandedValue := os.ExpandEnv(value)
		viper.Set(key, expandedValue)
	}

	conf := &Config{}
	if err := viper.Unmarshal(conf); err != nil {
		panic(err)
	}

	// 设置全局配置
	Global = *conf

	return conf
}
