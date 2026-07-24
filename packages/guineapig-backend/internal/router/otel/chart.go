package otel

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func ChartData(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.ChartDataRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.Chart == "" {
		return common.ResponseParamError(e, nil)
	}

	resp, err := service.GetChartData(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
