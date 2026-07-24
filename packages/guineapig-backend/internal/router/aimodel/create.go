package aimodel

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
	var req request.AiModelCreateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}
	if req.ModelName == "" {
		return common.ResponseParamError(e, errors.New("model_name 不能为空"))
	}
	if req.ApiUrl == "" {
		return common.ResponseParamError(e, errors.New("api_url 不能为空"))
	}
	if req.ApiKey == "" {
		return common.ResponseParamError(e, errors.New("api_key 不能为空"))
	}

	resp, err := service.CreateAiModel(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
