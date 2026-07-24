package file

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

	resp, err := service.PresignedResourceUploadURL(ctx, userID, filename)
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

	resp, err := service.PresignedResourceDownloadURL(ctx, key)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
