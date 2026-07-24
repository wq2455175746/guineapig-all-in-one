package file

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func EmbedProgress(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.FileEmbedProgressRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.FileId <= 0 {
		return common.ResponseParamError(e, errors.New("file_id 不能为空"))
	}
	if req.TaskId == "" {
		return common.ResponseParamError(e, errors.New("task_id 不能为空"))
	}

	if err := service.UpdateEmbedProgress(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
