#!/bin/bash

npm run build

podman build --platform linux/amd64 --tag=harbor.whg11.local:17020/aiagent/guineapig-web:1.0.0 .
podman push harbor.whg11.local:17020/aiagent/guineapig-web:1.0.0