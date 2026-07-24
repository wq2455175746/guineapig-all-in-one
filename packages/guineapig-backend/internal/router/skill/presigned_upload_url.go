package skill

import (
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func PresignedUploadURL(e echo.Context) error {
	ctx := utils.NewContext(e)

	userID := e.QueryParam("user_id")
	if userID == "" {
		return common.ResponseParamError(e, nil)
	}

	filename := e.QueryParam("filename")

	resp, err := service.GeneratePresignedSkillUploadURL(ctx, userID, filename)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
