package file

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Update(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.FileUpdateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if err := service.UpdateFile(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
