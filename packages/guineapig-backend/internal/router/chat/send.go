package chat

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func SendChatMessage(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.ChatSendRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 userId，杜绝 IDOR
	gdMid.BindRequester(e, &req.UserId)

	resp, err := service.SendChatMessage(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
