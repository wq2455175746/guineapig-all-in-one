package rag

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Create(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RagCreateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}
	if req.Name == "" {
		return common.ResponseParamError(e, errors.New("知识库名称不能为空"))
	}

	resp, err := service.CreateRag(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
