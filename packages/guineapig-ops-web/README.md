常用命令:
```shell
cd guineapig-web
npm install
npm run dev
```

前端启动:
```shell
npm run dev -- --host 0.0.0.0
npm run dev -- --host guineapig-ops-web.local
```

本地访问前端地址: http://guineapig-ops-web.local:5173
- **注意: `5173` 为前端服务端口**

调用后端接口： http://guineapig-ops-web.local:6880/
- **注意: `6880` 为后端服务端口**