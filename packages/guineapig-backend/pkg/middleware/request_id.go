package middleware

import (
	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
)

func RequestId(next echo.HandlerFunc) echo.HandlerFunc {
	return func(c echo.Context) error {
		// Generate a new UUID
		newUUID := uuid.NewString()

		// Store UUID in the context (echo.Context)
		c.Set("requestId", newUUID)

		// Proceed to the next handler
		return next(c)
	}
}
