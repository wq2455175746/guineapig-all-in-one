package scheduler

import (
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func List(e echo.Context) error {
	ctx := utils.NewContext(e)

	resp, err := service.ListSchedulerEntries(ctx)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
