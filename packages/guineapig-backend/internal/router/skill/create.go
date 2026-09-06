package skill

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Create(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.SkillCreateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(e, &req.UserId)

	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}
	if req.ZipKey == "" {
		return common.ResponseParamError(e, errors.New("zip_key 不能为空"))
	}

	resp, err := service.CreateSkill(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
