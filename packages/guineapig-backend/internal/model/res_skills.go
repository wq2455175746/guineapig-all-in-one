package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MResSkills = &ResSkills{}

type ResSkills struct {
	Id           int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId       int64     `gorm:"column:user_id"`
	Name         string    `gorm:"column:name"`
	Description  string    `gorm:"column:skill_desc"`
	SkillVersion string    `gorm:"column:skill_version"`
	ZipUrl       string    `gorm:"column:zip_url"`
	FileStat     string    `gorm:"column:file_stat;type:json"`
	Metadata     string    `gorm:"column:metadata;type:json"`
	Status       int8      `gorm:"column:status"`
	CreatedBy    string    `gorm:"column:created_by"`
	CreatedAt    time.Time `gorm:"column:created_at"`
	UpdatedBy    string    `gorm:"column:updated_by"`
	UpdatedAt    time.Time `gorm:"column:updated_at"`
	DeletedAt    *int64    `gorm:"column:deleted_at"`
}

func (*ResSkills) TableName() string {
	return "res_skills"
}

func (m *ResSkills) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ResSkills) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()

	updates := map[string]any{
		"status":     m.Status,
		"updated_at": m.UpdatedAt,
	}

	if m.Name != "" {
		updates["name"] = m.Name
	}
	if m.Description != "" {
		updates["skill_desc"] = m.Description
	}
	if m.SkillVersion != "" {
		updates["skill_version"] = m.SkillVersion
	}
	if m.ZipUrl != "" {
		updates["zip_url"] = m.ZipUrl
	}
	if m.FileStat != "" {
		updates["file_stat"] = m.FileStat
	}
	if m.Metadata != "" {
		updates["metadata"] = m.Metadata
	}

	return plugin.GetDB(ctx).Model(m).Where("id = ? AND deleted_at IS NULL", m.Id).Updates(updates).Error
}

func (*ResSkills) Delete(ctx context.Context, id int64, userId int64) error {
	now := time.Now().Unix()
	return plugin.GetDB(ctx).Model(&ResSkills{}).Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*ResSkills) FindById(ctx context.Context, id int64) (*ResSkills, error) {
	var m ResSkills
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ResSkills) List(ctx context.Context, req *request.SkillListRequest) ([]*ResSkills, int64, error) {
	query := plugin.GetDB(ctx).Model(&ResSkills{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(name LIKE ? OR `skill_desc` LIKE ?)", searchKey, searchKey)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	if req.PageSize > 0 && req.PageNum > 0 {
		offset := (req.PageNum - 1) * req.PageSize
		query = query.Offset(offset).Limit(req.PageSize)
	}

	query = query.Order("id desc")

	var items []*ResSkills
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}

	return items, total, nil
}

// ListEnabledByUserId 查询用户已开启的 skill 列表
func (*ResSkills) ListEnabledByUserId(ctx context.Context, userId int64) ([]ResSkills, error) {
	var list []ResSkills
	err := plugin.GetDB(ctx).
		Where("user_id = ? AND status = 1 AND deleted_at IS NULL", userId).
		Find(&list).Error
	return list, err
}

// FindByUserIdAndName 检查同名 skill 是否已存在
func (*ResSkills) FindByUserIdAndName(ctx context.Context, userId int64, name string) (*ResSkills, error) {
	var m ResSkills
	err := plugin.GetDB(ctx).Model(&ResSkills{}).
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
