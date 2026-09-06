package aimodel

import (
	"errors"
	"fmt"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func PresignedUploadURL(e echo.Context) error {
	ctx := utils.NewContext(e)

	userID := e.QueryParam("user_id")
	if userID == "" {
		return common.ResponseParamError(e, nil)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		userID = fmt.Sprintf("%d", uid)
	}

	filename := e.QueryParam("filename")

	resp, err := service.GeneratePresignedUploadURL(ctx, userID, filename)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}

func PresignedDownloadURL(e echo.Context) error {
	ctx := utils.NewContext(e)

	key := e.QueryParam("key")
	if key == "" {
		return common.ResponseParamError(e, nil)
	}

	// 预签名下载是资源读取的唯一路径：S3 key 内嵌用户 id（{prefix}/{user_id}/...）。
	// 仅允许下载属于当前用户会话的对象；admin / inner 会话（CurrentUserID==0）放行。
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		keyUID := utils.KeyOwnerUserID(key)
		if keyUID <= 0 || keyUID != uid {
			return common.ResponseForbidden(e, errors.New("无权访问该资源"))
		}
	}

	resp, err := service.GeneratePresignedDownloadURL(ctx, key)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
