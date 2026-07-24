package user

import (
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
)

func ListUser(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.SearchRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.ListUser(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
