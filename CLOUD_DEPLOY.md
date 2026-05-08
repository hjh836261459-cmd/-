# 云端部署：每日 AI/AIGC 高质量新闻简报

这个方案使用 GitHub Actions 定时运行，不依赖本机电脑开机。默认每天北京时间 9:00 运行一次，抓取国内外 AI/AIGC 新闻，先筛选高质量候选，再生成中文编辑简报，并通过 QQ SMTP 发到 `hjh836261459@qq.com`。

## 简报质量要求

新版脚本不是简单发送链接，而是按编辑简报输出：

- 全部中文输出，英文新闻会翻译并重写。
- 过滤重复、低信息量、SEO、股票短线、软文和纯观点内容。
- 每条新闻总结“发生了什么、为什么重要、可能影响什么”。
- 分类包括：技术与模型、公司与产品新闻、中国 AI/AIGC 动态、政策监管与安全、投融资与产业、应用与生态、编辑观察。
- 链接只作为来源保留，不作为正文主体。

## 必需 GitHub Secrets

进入 GitHub 仓库：

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

添加：

- `QQ_SMTP_AUTH_CODE`：QQ 邮箱 SMTP 授权码
- `GEMINI_API_KEY`：Gemini API Key，用于免费/低成本生成中文编辑简报

## 可选 GitHub Secrets / Variables

- `OPENAI_API_KEY`：可选；如果配置，脚本会优先用 OpenAI 生成简报
- `QQ_SMTP_USER`：默认 `hjh836261459@qq.com`
- `MAIL_TO`：默认 `hjh836261459@qq.com`
- `OPENAI_MODEL`：默认 `gpt-5-mini`
- `GEMINI_MODEL`：默认 `gemini-2.5-flash`

模型优先级：

1. 有 `OPENAI_API_KEY` 时优先用 OpenAI
2. 没有 OpenAI key 但有 `GEMINI_API_KEY` 时用 Gemini
3. 两者都没有时降级为规则版，仍会发邮件，但总结质量较低

## 运行时间

GitHub Actions 的 cron 使用 UTC 时间：

- `0 1 * * *` = UTC 01:00
- 对应北京时间 / Asia/Shanghai 09:00

## 手动测试

进入 GitHub 仓库的 `Actions` 页面，选择 `Daily AI/AIGC News Mail`，点击 `Run workflow`。

成功后你会收到邮件，Actions 页面也会保存一份 Markdown 简报 artifact。

## 可能失败的情况

- `GEMINI_API_KEY` 未配置、失效或免费额度受限。
- QQ SMTP 授权码失效或没有开启 SMTP。
- QQ 邮箱限制来自云端 IP 的登录或发信。
- GitHub Actions 无法访问 Google News RSS、Gemini API 或 OpenAI API。
- 邮件被 QQ 邮箱反垃圾策略拦截。
