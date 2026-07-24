package file

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func List(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.FileListRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.ListFile(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
