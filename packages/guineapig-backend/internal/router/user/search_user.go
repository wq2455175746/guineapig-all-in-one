package user

import (
	"github.com/labstack/echo/v4"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"
)

// SearchUser 获取用户列表
func SearchUser(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.SearchUserRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}
	if req.Keywords == "" {
		return common.ResponseOk(e, &response.SearchUserResponse{})
	}
	resp, err := service.SearchUser(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}
	return common.ResponseOk(e, resp)
}
