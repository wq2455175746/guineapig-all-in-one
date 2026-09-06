package model

import (
	"context"
	"errors"
	"guineapig/pkg/plugin"

	"gorm.io/gorm"
)

var MUserApiKey = &UserApiKey{}

type UserApiKey struct {
	Id     int64  `gorm:"column:id;primaryKey"`
	UserId int64  `gorm:"column:user_id"`
	ApiKey string `gorm:"column:api_key"`
	Status int8   `gorm:"column:status"`
}

func (*UserApiKey) TableName() string {
	return "user_apikey"
}

func (k *UserApiKey) Create(ctx context.Context) error {
	return plugin.GetDB(ctx).Create(k).Error
}

// FindByStoredKey 根据已哈希的 api_key（HMAC-SHA256 或兼容旧数据的 MD5）精确匹配存储值。
func (*UserApiKey) FindByStoredKey(ctx context.Context, storedKey string) (*UserApiKey, error) {
	var key UserApiKey
	err := plugin.GetDB(ctx).Where("api_key = ? AND status = 1", storedKey).First(&key).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &key, nil
}
