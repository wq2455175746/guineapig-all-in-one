# guineapig-client


## 前端启动:
```shell 
npm run dev -- --host 0.0.0.0 --port 5174
npm run dev -- --host guineapig-client.local --port 5174
``` 

## 命令执行白名单配置
Electron 主进程执行 LLM 生成的本地命令时受白名单限制（`execute-command`）。
白名单可在 `userData/command-whitelist.json` 中配置（首次启动自动生成默认文件）：

```json
{
  "allowedBinaries": ["open", "xdg-open", "ls", "cat", "pwd", "echo", "which", "node", "python3"]
}
```

- 文件缺失或损坏时自动回退到内置默认白名单（开发命令 + 系统只读/打开命令）
- 修改配置后需重启 Electron 应用生效
- 所有命令仍受参数安全校验（`SAFE_ARG_TOKEN`）与 cwd 目录限制 
