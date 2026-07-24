package file

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Embed(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.FileEmbedRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.FileId <= 0 {
		return common.ResponseParamError(e, errors.New("file_id 不能为空"))
	}
	if req.ResRagId <= 0 {
		return common.ResponseParamError(e, errors.New("res_rag_id 不能为空"))
	}

	result, err := service.EmbedFile(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, result)
}
