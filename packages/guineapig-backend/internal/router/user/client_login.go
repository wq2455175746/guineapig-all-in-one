package user

import (
	"errors"
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
)

func ClientLogin(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.ClientLoginRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.ApiKey == "" {
		return common.ResponseParamError(e, errors.New("api_key 不能为空"))
	}

	resp, err := service.ClientLogin(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
