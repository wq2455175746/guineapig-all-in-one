package utils

import "time"

// DBQueryTimeout 单次 DB 查询/写入的超时上限。
const DBQueryTimeout = 10 * time.Second

// HTTPRequestTimeout 非流式出站 HTTP 调用的整体超时上限。
const HTTPRequestTimeout = 30 * time.Second

// AsyncTaskTimeout 后台异步任务（fire-and-forget）的整体超时上限。
const AsyncTaskTimeout = 5 * time.Minute