# credentials/

此目录存放 Google OAuth 凭证，**目录内文件不会提交 Git**（`.gitignore` 已排除，本说明文件除外）。

需要放在这里：

- `credentials.json` —— 从 Google Cloud Console 下载的 OAuth 客户端密钥
  （APIs & Services → Credentials → OAuth client ID → Desktop app → Download JSON）

首次运行 `python scripts/list_events.py` 完成授权后，会自动生成：

- `token.json` —— 缓存的访问令牌（过期会自动刷新）

详细配置步骤见项目根目录的 `README.md`。
