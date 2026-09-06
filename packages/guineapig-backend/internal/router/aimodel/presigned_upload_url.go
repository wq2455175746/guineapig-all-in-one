package aimodel

import (
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

	resp, err := service.GeneratePresignedDownloadURL(ctx, key)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
