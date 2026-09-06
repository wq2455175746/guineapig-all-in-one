package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

// File type constants
const (
	FileTypeTXT      = 0
	FileTypeMarkdown = 1
	FileTypeHTML     = 2
	FileTypePDF      = 3
	FileTypeMP3      = 4
	FileTypeIMG      = 5
	FileTypeOther    = 99
)

// IsEmbedded status constants
const (
	IsEmbeddedNo     = 0 // 未嵌入
	IsEmbeddedYes    = 1 // 已嵌入
	IsEmbeddedDoing  = 2 // 嵌入中
	IsEmbeddedFailed = 9 // 嵌入失败
)

var MResFiles = &ResFiles{}

type ResFiles struct {
	Id              int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId          int64     `gorm:"column:user_id"`
	Name            string    `gorm:"column:name"`
	FileDesc        string    `gorm:"column:file_desc"`
	FileURL         string    `gorm:"column:file_url"`
	FileMetadata    string    `gorm:"column:file_metadata;type:json"`
	FileType        int       `gorm:"column:file_type"`
	EmbeddingConfig *string   `gorm:"column:embedding_config;type:json"`
	IsEmbedded      int8      `gorm:"column:is_embedded"`
	StorageType     int8      `gorm:"column:storage_type"`
	CreatedBy       string    `gorm:"column:created_by"`
	CreatedAt       time.Time `gorm:"column:created_at"`
	UpdatedBy       string    `gorm:"column:updated_by"`
	UpdatedAt       time.Time `gorm:"column:updated_at"`
	DeletedAt       *int64    `gorm:"column:deleted_at"`
}

func (*ResFiles) TableName() string {
	return "res_files"
}

func (m *ResFiles) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ResFiles) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()
	updates := map[string]any{
		"updated_at": m.UpdatedAt,
	}
	if m.Name != "" {
		updates["name"] = m.Name
	}
	if m.FileDesc != "" {
		updates["file_desc"] = m.FileDesc
	}
	if m.FileType > 0 {
		updates["file_type"] = m.FileType
	}
	return plugin.GetDB(ctx).Model(m).Where("id = ? AND deleted_at IS NULL", m.Id).Updates(updates).Error
}

func (*ResFiles) Delete(ctx context.Context, id int64, userId int64) error {
	now := time.Now().Unix()
	return plugin.GetDB(ctx).Model(&ResFiles{}).Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*ResFiles) UpdateEmbeddingConfig(ctx context.Context, id int64, embeddingConfig string) error {
	updates := map[string]any{
		"embedding_config": embeddingConfig,
		"updated_at":       time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResFiles{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
}

func (*ResFiles) UpdateIsEmbedded(ctx context.Context, id int64, status int8) error {
	updates := map[string]any{
		"is_embedded": status,
		"updated_at":  time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResFiles{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
}

func (*ResFiles) FindById(ctx context.Context, id int64) (*ResFiles, error) {
	var m ResFiles
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

// FindByIds 批量按 ID 查询文件（供 RAG 上下文解析等场景消除 N+1）。
func (*ResFiles) FindByIds(ctx context.Context, ids []int64) ([]*ResFiles, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	var items []*ResFiles
	err := plugin.GetDB(ctx).Model(&ResFiles{}).
		Where("id IN ? AND deleted_at IS NULL", ids).
		Find(&items).Error
	if err != nil {
		return nil, err
	}
	return items, nil
}

func (*ResFiles) FindByUserIdAndName(ctx context.Context, userId int64, name string) (*ResFiles, error) {
	var m ResFiles
	err := plugin.GetDB(ctx).Model(&ResFiles{}).
		Where("user_id = ? AND name = ? AND deleted_at IS NULL", userId, name).
		First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ResFiles) List(ctx context.Context, req *request.FileListRequest) ([]*ResFiles, int64, error) {
	query := plugin.GetDB(ctx).Model(&ResFiles{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}
	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(name LIKE ? OR file_desc LIKE ?)", searchKey, searchKey)
	}
	if req.FileType != nil {
		query = query.Where("file_type = ?", *req.FileType)
	}
	if req.IsEmbedded != nil && *req.IsEmbedded >= 0 {
		query = query.Where("is_embedded = ?", *req.IsEmbedded)
	} // nil 或负值表示搜索全部

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if req.PageSize > 0 && req.PageNum > 0 {
		offset := (req.PageNum - 1) * req.PageSize
		query = query.Offset(offset).Limit(req.PageSize)
	} else {
		query = query.Limit(MaxListLimit)
	}
	query = query.Order("id desc")

	var items []*ResFiles
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}
	return items, total, nil
}
