package aimodel

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

	resp, err := service.GeneratePresignedUploadURL(ctx, userID, filename)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}

func PresignedDownloadURL(e echo.Context) error {
	ctx := utils.NewContext(e)

	key := e.QueryParam("key")
	if key == "" {
		return common.ResponseParamError(e, nil)
	}

	resp, err := service.GeneratePresignedDownloadURL(ctx, key)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
