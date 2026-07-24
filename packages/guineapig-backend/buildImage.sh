#!/usr/bin/env bash

CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags "-s -w" -trimpath -o ./bin/autoeval main.go

podman build --tag=harbor.whg11.local:17020/aiagent/guineapig:1.0.0 .
podman push harbor.whg11.local:17020/aiagent/guineapig:1.0.0