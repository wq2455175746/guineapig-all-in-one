package otel

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func List(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.OtelListRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	// 用户会话强制查询自己的指标；admin 会话可查询任意用户
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		req.UserId = uid
	}

	if req.PageSize <= 0 {
		req.PageSize = 10
	}
	if req.PageNum <= 0 {
		req.PageNum = 1
	}

	resp, err := service.ListOtel(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
