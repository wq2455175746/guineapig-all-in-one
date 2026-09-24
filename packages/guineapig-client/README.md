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
- 手动编辑文件后需重启 Electron 应用生效（页面保存则立即生效）
- 所有命令仍受参数安全校验（`SAFE_ARG_TOKEN`）与 cwd 目录限制

### 页面配置（系统设置 → 命令白名单）
除手动编辑 `command-whitelist.json` 外，也可在客户端「系统设置 → 命令白名单」页中通过输入框直接维护：
- 每行一个命令名，点击「保存」立即生效并写入 `userData/command-whitelist.json`
- 「恢复默认」将输入框重置为内置默认白名单
- 留空保存将恢复默认白名单；含空白/特殊字符的非法项会被自动忽略 
