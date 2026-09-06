package bot

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

// Bind 绑定 IM 平台 Bot
func Bind(c echo.Context) error {
	ctx := utils.NewContext(c)

	var req request.BotBindRequest
	if err := c.Bind(&req); err != nil {
		return common.ResponseParamError(c, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(c, &req.UserId)

	resp, err := service.BindBot(ctx, &req)
	if err != nil {
		return common.ResponseServerError(c, err)
	}

	return common.ResponseOk(c, resp)
}

// Unbind 解绑 IM 平台 Bot
func Unbind(c echo.Context) error {
	ctx := utils.NewContext(c)

	var req request.BotUnbindRequest
	if err := c.Bind(&req); err != nil {
		return common.ResponseParamError(c, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(c, &req.UserId)

	if err := service.UnbindBot(ctx, &req); err != nil {
		return common.ResponseServerError(c, err)
	}

	return common.ResponseOk(c, nil)
}

// Info 查询 Bot 绑定信息
func Info(c echo.Context) error {
	ctx := utils.NewContext(c)

	var req request.BotInfoRequest
	if err := c.Bind(&req); err != nil {
		return common.ResponseParamError(c, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(c, &req.UserId)

	items, err := service.GetBotInfo(ctx, &req)
	if err != nil {
		return common.ResponseServerError(c, err)
	}

	return common.ResponseOk(c, items)
}
