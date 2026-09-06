package aimodel

import (
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"
	"strconv"

	"github.com/labstack/echo/v4"
)

func OptionsByType(e echo.Context) error {
	ctx := utils.NewContext(e)

	userIdStr := e.QueryParam("user_id")
	userId, err := strconv.ParseInt(userIdStr, 10, 64)
	if err != nil {
		return common.ResponseParamError(e, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		userId = uid
	}

	modelType := e.QueryParam("model_type")

	resp, err := service.ListAiModelOptionsByType(ctx, userId, modelType)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}

func Options(e echo.Context) error {
	ctx := utils.NewContext(e)

	userIdStr := e.QueryParam("user_id")
	userId, err := strconv.ParseInt(userIdStr, 10, 64)
	if err != nil {
		return common.ResponseParamError(e, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		userId = uid
	}

	resp, err := service.ListAiModelOptions(ctx, userId)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
