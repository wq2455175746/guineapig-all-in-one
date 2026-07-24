package memory

import (
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
	"strconv"

	"github.com/labstack/echo/v4"
)

func List(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemoryListRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.ListMemory(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}

func Get(e echo.Context) error {
	ctx := utils.NewContext(e)

	idStr := e.QueryParam("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.GetMemory(ctx, id)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}

func Delete(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemoryDeleteRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}
	if err := service.DeleteMemory(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}

func Summarize(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemorySummarizeRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	memoryId, err := service.CreateMemorySummary(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, response.MemorySummarizeResponse{MemoryId: memoryId})
}

func UpdateContent(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemoryUpdateContentRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if err := service.UpdateMemoryContent(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
