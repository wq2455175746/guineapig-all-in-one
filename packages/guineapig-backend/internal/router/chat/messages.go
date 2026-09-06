package chat

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func ListMessages(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MessageListRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	// requester 为 Token 推导的 caller identity（admin 会话为 0，可查询任意会话）
	resp, err := service.ListMessages(ctx, &req, gdMid.CurrentUserID(e))
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
