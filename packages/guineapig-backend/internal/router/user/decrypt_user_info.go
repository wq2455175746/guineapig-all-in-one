package user

import (
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"
)

func DecryptUserInfo(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.DecryptUserInfoRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.DecryptUserInfo(ctx, &req, gdMid.CurrentUserID(e))
	if err != nil {
		return common.ResponseServerError(e, err)
	}
	return common.ResponseOk(e, resp)
}
