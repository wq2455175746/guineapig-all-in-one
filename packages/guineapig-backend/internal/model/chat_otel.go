package model

import (
	"context"
	"encoding/json"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MChatOtel = &ChatOtel{}

type ChatOtel struct {
	Id             int64     `gorm:"column:id;primaryKey;autoIncrement"`
	Name           string    `gorm:"column:name"`
	UserId         int64     `gorm:"column:user_id"`
	ConversationIDs *string   `gorm:"column:conversation_ids;type:json"`
	StatDate       string    `gorm:"column:stat_date"`
	Type           string    `gorm:"column:type"`
	OtelValue      *string   `gorm:"column:otel_value;type:json"`
	OtelLabel      *string   `gorm:"column:otel_label;type:json"`
	CreatedBy      string    `gorm:"column:created_by"`
	CreatedAt      time.Time `gorm:"column:created_at"`
	UpdatedAt      time.Time `gorm:"column:updated_at"`
}

func (*ChatOtel) TableName() string {
	return "chat_otel"
}

func (m *ChatOtel) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ChatOtel) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()

	updates := map[string]any{
		"updated_at": m.UpdatedAt,
	}

	if m.Name != "" {
		updates["name"] = m.Name
	}
	if m.OtelValue != nil {
		updates["otel_value"] = *m.OtelValue
	}
	if m.OtelLabel != nil {
		updates["otel_label"] = *m.OtelLabel
	}
	if m.Type != "" {
		updates["type"] = m.Type
	}

	return plugin.GetDB(ctx).Model(m).Where("id = ?", m.Id).Updates(updates).Error
}

func (*ChatOtel) Delete(ctx context.Context, id int64) error {
	return plugin.GetDB(ctx).Delete(&ChatOtel{}, id).Error
}

func (*ChatOtel) FindById(ctx context.Context, id int64) (*ChatOtel, error) {
	var m ChatOtel
	err := plugin.GetDB(ctx).First(&m, id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ChatOtel) List(ctx context.Context, req *request.OtelListRequest) ([]*ChatOtel, int64, error) {
	query := plugin.GetDB(ctx).Model(&ChatOtel{})

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("name LIKE ?", searchKey)
	}

	if req.StatDate != "" {
		query = query.Where("stat_date = ?", req.StatDate)
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

	var items []*ChatOtel
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}

	return items, total, nil
}

// ListByStatDate 按日期批量查询（用于 sync 验证）
func (*ChatOtel) ListByStatDate(ctx context.Context, userId int64, statDate string) ([]*ChatOtel, error) {
	var items []*ChatOtel
	err := plugin.GetDB(ctx).
		Where("user_id = ? AND stat_date = ?", userId, statDate).
		Order("id desc").
		Find(&items).Error
	return items, err
}

// UpsertCount INSERT ... ON DUPLICATE KEY UPDATE 写入/覆盖指标计数。
// 唯一约束: (user_id, name, stat_date, type)
// otel_value 格式: {"count": N, "conversation_ids": [...]}
// Redis 中的 count 已经是最新值（Python HINCRBY 的结果），直接覆盖
func (*ChatOtel) UpsertCount(ctx context.Context, userId int64, name string, statDate string, metricType string, count int64, conversationIDs []int64) error {
	// 序列化 conversation_ids JSON 数组
	convIDsJSON := "[]"
	if len(conversationIDs) > 0 {
		if b, err := json.Marshal(conversationIDs); err == nil {
			convIDsJSON = string(b)
		}
	}

	sql := `INSERT INTO chat_otel (user_id, name, stat_date, type, conversation_ids, otel_value, created_by, created_at, updated_at)
			VALUES (?, ?, ?, ?, CAST(? AS JSON), JSON_OBJECT('count', ?), 'system', NOW(), NOW())
			ON DUPLICATE KEY UPDATE
				otel_value = JSON_OBJECT('count', ?),
				conversation_ids = CAST(? AS JSON),
				updated_at = NOW()`
	return plugin.GetDB(ctx).Exec(sql, userId, name, statDate, metricType, convIDsJSON, count, count, convIDsJSON).Error
}

// QueryRows 执行原始 SQL 并返回动态行数据（用于通用图表查询）
func (*ChatOtel) QueryRows(ctx context.Context, sql string, params ...any) ([]map[string]any, error) {
	rows, err := plugin.GetDB(ctx).Raw(sql, params...).Rows()
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}

	var results []map[string]any
	for rows.Next() {
		values := make([]any, len(columns))
		valuePtrs := make([]any, len(columns))
		for i := range columns {
			valuePtrs[i] = &values[i]
		}

		if err := rows.Scan(valuePtrs...); err != nil {
			return nil, err
		}

		row := make(map[string]any)
		for i, col := range columns {
			val := values[i]
			switch v := val.(type) {
			case []byte:
				row[col] = string(v)
			default:
				row[col] = v
			}
		}
		results = append(results, row)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return results, nil
}
