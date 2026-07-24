package user

import (
	"errors"
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
)

func Register(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RegisterRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.Email == "" {
		return common.ResponseParamError(e, errors.New("邮箱不能为空"))
	}
	if req.Code == "" {
		return common.ResponseParamError(e, errors.New("验证码不能为空"))
	}

	resp, err := service.Register(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
