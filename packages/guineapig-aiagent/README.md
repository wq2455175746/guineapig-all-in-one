# doc2store
```
1，数据同步服务主要功能为同步S3中的JSON文献内容到elastic+milvus中。
2，同步服务尽量保证简洁，业务操作在ops-center中实现
```

## 项目结构
```

```

## 项目初始化
```
1，先安装uv
curl -LsSf https://astral.sh/uv/install.sh | sh

2，初始化虚拟环境
uv venv

3，安装依赖包
uv sync
```


## 本地运行命令
```
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产启动命令（关键参数说明）
uvicorn \
  main:app \
  --host 0.0.0.0 \  # 监听所有网卡，允许外部访问
  --port 8000 \     # 服务端口
  --workers 4 \     # 工作进程数（推荐：CPU核心数 * 2 + 1）
  --threads 2 \     # 每个进程的线程数
  --log-level info \# 日志级别（info/warning/error）
  --access-log \    # 开启访问日志
  --error-log /opt/fastapi_demo/logs/uvicorn_error.log \  # 错误日志
  --access-log /opt/fastapi_demo/logs/uvicorn_access.log  # 访问日志

uv run gunicorn -c gunicorn_config.py app.main:app

# Gunicorn 启动 Uvicorn 命令
uv run  gunicorn \
  main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \  # 指定 Uvicorn 工作器
  --bind 0.0.0.0:8000 \
  --log-level info \
  --access-logfile /opt/fastapi_demo/logs/gunicorn_access.log \
  --error-logfile /opt/fastapi_demo/logs/gunicorn_error.log

```


## 本地测试接口CURL
```
curl -X POST http://localhost:8000/guineapig-aiagent/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "session-t1",
    "taskId": "t1",
    "requestId": "r1",
    "its": 1717000000,
    "objectKey": "audio/asr/1000000001/20260525/audio.mp3"
  }'

## ASR接口 通过s3文件链接直接返回文本内容
curl -X POST http://localhost:8000/guineapig-aiagent/asr/transcribe \
    -H "Content-Type: application/json" \
    -d '{"objectKey": "audio/asr/2060308477309358000/20260602/ce928ac23f0646d7a0de5108d0f893a6.mp3"}'

```


## 镜像本地打包
```
podman build -t "harbor.whg11.local:17020/hz-dmx/dmx/openalexdata2store:develop" .

podman push harbor.whg11.local:17020/hz-dmx/dmx/openalexdata2store:develop

需要注意的是，如果每次uv add 包或者修改了pyproject.toml中的依赖，需要同步修改requirements.txt中的信息
```

## 单元测试
```

首先要到test目录中创建自己的单元测试文件

添加依赖
uv add pytest pytest-mock pytest-cov pytest-asyncio

执行单元测试
.venv/bin/python -m pytest test/ -v 2>&1

uv run pytest test/ -v 2>&1
```