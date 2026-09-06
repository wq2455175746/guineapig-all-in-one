package memory

import (
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
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

	// 用户会话强制查询自己的记忆；admin 会话可查询任意用户
	if uid := gdMid.CurrentUserID(e); uid > 0 {
		req.UserId = uid
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

	resp, err := service.GetMemory(ctx, id, gdMid.CurrentUserID(e))
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

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(e, &req.UserId)

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

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(e, &req.UserId)

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
