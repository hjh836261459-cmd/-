# 云端部署：每日 AI/AIGC 新闻邮件

这个方案使用 GitHub Actions 定时运行，不依赖本机电脑开机。默认每天北京时间 9:00 运行一次，抓取国内外 AI/AIGC 新闻并通过 QQ SMTP 发到 `hjh836261459@qq.com`。

## 需要准备

1. 一个 GitHub 仓库。
2. QQ 邮箱已开启 SMTP 服务。
3. QQ 邮箱 SMTP 授权码。

不要把授权码写进代码或提交到仓库。请放到 GitHub Secrets。

## 上传文件

把当前目录中的这些文件上传到 GitHub 仓库：

- `.github/workflows/daily-ai-aigc-news.yml`
- `scripts/daily_ai_aigc_news_mailer.py`
- `.gitignore`

可选上传：

- `CLOUD_DEPLOY.md`

不要上传这些本地敏感或生成文件：

- `qq-smtp-auth-code.sec`
- `qq-smtp-send.log`
- `out/`

`.gitignore` 已经排除了它们。

## 配置 GitHub Secrets

进入 GitHub 仓库：

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

添加：

- `QQ_SMTP_AUTH_CODE`：QQ 邮箱 SMTP 授权码

可选添加：

- `QQ_SMTP_USER`：`hjh836261459@qq.com`
- `MAIL_TO`：`hjh836261459@qq.com`

如果不设置这两个可选项，脚本会默认使用 `hjh836261459@qq.com` 作为发件人与收件人。

## 运行时间

GitHub Actions 的 cron 使用 UTC 时间：

- `0 1 * * *` = UTC 01:00
- 对应北京时间 / Asia/Shanghai 09:00

## 手动测试

进入 GitHub 仓库的 `Actions` 页面，选择 `Daily AI/AIGC News Mail`，点击 `Run workflow`。

成功后你会收到邮件，Actions 页面也会保存一份 Markdown 简报 artifact。

## 可能失败的情况

- QQ SMTP 授权码失效或没有开启 SMTP。
- QQ 邮箱限制来自云端 IP 的登录或发信。
- GitHub Actions 无法访问 Google News RSS。
- 邮件被 QQ 邮箱反垃圾策略拦截。

如果 QQ SMTP 在 GitHub Actions 上被限制，可以改用腾讯云函数、阿里云函数计算或一个轻量云服务器部署同一个 Python 脚本。
