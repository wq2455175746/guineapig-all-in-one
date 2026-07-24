package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"time"

	"gorm.io/gorm"
)

var MUser = &User{}

type User struct {
	// gorm.Model 是 GORM 内置的基础模型，包含 ID, CreatedAt, UpdatedAt, DeletedAt（软删除）
	gorm.Model
	Id          int64     `gorm:"column:id"`
	UserName    string    `gorm:"column:username"`
	NickName    string    `gorm:"column:nickname"`
	PhoneNumber string    `gorm:"column:phone_number"`
	Email       string    `gorm:"column:email"`
	LoginTime   time.Time `gorm:"column:last_login_time"`
	Password    string    `gorm:"column:password"`
	Source      string    `gorm:"column:source"`
}

func (*User) TableName() string {
	return "user"
}

func (*User) FindByEmail(ctx context.Context, email string) (*User, error) {
	var user User
	err := plugin.GetDB(ctx).Where("email = ?", email).First(&user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &user, nil
}

func (u *User) Create(ctx context.Context) error {
	u.CreatedAt = time.Now()
	u.UpdatedAt = time.Now()
	u.LoginTime = time.Now()

	return plugin.GetDB(ctx).Create(u).Error
}

func (u *User) Save(ctx context.Context) error {
	u.UpdatedAt = time.Now()
	u.LoginTime = time.Now()
	if u.Id == 0 {
		u.CreatedAt = time.Now()
	}

	return plugin.GetDB(ctx).Save(u).Error
}

func (*User) FindById(ctx context.Context, id int64) (*User, error) {
	var user User
	err := plugin.GetDB(ctx).Where("id = ?", id).First(&user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}

	return &user, nil
}

func (*User) FindByIds(ctx context.Context, ids []int64) ([]User, error) {
	var users []User
	err := plugin.GetDB(ctx).Where("id in ?", ids).Find(&users).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}

	return users, nil
}

func (*User) FindByUserName(ctx context.Context, userName string) (*User, error) {
	var user User
	err := plugin.GetDB(ctx).Where("user_name = ?", userName).First(&user).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}

	return &user, nil
}

func (*User) Search(ctx context.Context, keywords string) ([]User, error) {
	var users []User
	query := plugin.GetDB(ctx).Model(&User{})
	searchKey := "%" + keywords + "%"
	query = query.Where("nick_name LIKE ?", searchKey).Or("user_name LIKE ?", searchKey)
	query = query.Limit(20)

	query = query.Order("id desc")
	err := query.Find(&users).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil
	}

	return users, nil
}
func (*User) ListUser(ctx context.Context, req *request.SearchRequest) ([]*User, int64, error) {

	query := plugin.GetDB(ctx).Model(&User{})

	if req.GetKeywords() != "" {
		searchKey := "%" + req.GetKeywords() + "%"
		query = query.
			Where("nick_name LIKE ?", searchKey).
			Or("user_name LIKE ?", searchKey).
			Or("email LIKE ?", searchKey)

	}

	// 获取总数
	var total int64
	if err := query.Count(&total).Error; err != nil {
		logger.ErrorReqIdf(ctx, "count users err: %v", err)
		return nil, 0, err
	}

	// 处理分页
	if req != nil {
		if offset := req.Offset(); offset > 0 {
			query = query.Offset(offset)
		}
		if limit := req.Limit(); limit > 0 {
			query = query.Limit(limit)
		}
	}
	query = query.Order("id desc")

	var users []*User
	if err := query.Find(&users).Error; err != nil {
		logger.ErrorReqIdf(ctx, "find users err: %v", err)
		return nil, 0, err
	}

	return users, total, nil
}

// FindAllUserIds 查询所有用户ID
func (*User) FindAllUserIds(ctx context.Context) ([]int64, error) {
	var ids []int64
	if err := plugin.GetDB(ctx).Model(&User{}).Select("id").Find(&ids).Error; err != nil {
		return nil, err
	}
	return ids, nil
}

// Delete 物理删除user数据
func (u *User) Delete(ctx context.Context, id int64) error {
	return plugin.GetDB(ctx).Where("id = ?", id).Delete(&User{}).Error
}
