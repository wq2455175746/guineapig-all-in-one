package middleware

import (
	"github.com/labstack/echo/v4"
	"guineapig/config"
	redisPlugin "guineapig/pkg/plugin"
	"guineapig/pkg/ratelimit"
	"net/http"
)

func RateLimit() echo.MiddlewareFunc {
	rateLimiter := config.Global.RateLimiter
	var limiter ratelimit.RateLimiter
	if rateLimiter.Type == "memory" {
		limiter = ratelimit.NewMemoryRateLimiter()
	} else {
		limiter = ratelimit.NewRedisRateLimiter(redisPlugin.GetClient())
	}

	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) (err error) {
			ctx := c.Request().Context()
			key := formattedKey(c.Path())

			if rateLimiter.EnableConcurrency { // 开启并发限制
				if limit, ok := rateLimiter.Concurrency[c.Path()]; ok {
					allowed := limiter.Allow(ctx, key, limit)
					defer limiter.Release(ctx, key)

					if !allowed {
						return c.JSON(http.StatusTooManyRequests, map[string]interface{}{})
					}
				}
			}

			return next(c)
		}
	}
}

func formattedKey(key string) string {
	return "multimedia:ratelimit:" + key
}
