# guinea pig

## 后端开发
golang版本: 1.25.1
涉及的框架：
- web 框架 [echo](https://github.com/labstack/echo)
- mysql 操作 [gorm](https://github.com/go-gorm/gorm)
- 定时任务 [cron](github.com/robfig/cron/v3)
- redis缓存 [go-redis](github.com/redis/go-redis/v9)
- k8s 操作 [k8s.io](k8s.io/client-go)
- 单元测试 [testify](github.com/stretchr/testify)

## 文档结构
internal/ 包含项目私有代码
pkg/ 包含可以被其他项目复用的公共代码
config/ 处理配置相关逻辑