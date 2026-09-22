# 湾区鸟讯

[阅读鸟讯](https://outman.cc/birding/) · [JSON](https://lincleejun.github.io/birding/feed.json) · [运行记录](https://github.com/lincleejun/birding/actions)

这是无 AI、无外部 API 密钥的采集试运行。GitHub Actions 每小时的第 17 分钟检查 Sialia 的五个湾区邮件列表，将结果提交到 `data/feed.json`，并发布为静态 JSON。网页独立放在 `outman.me` 仓库的 `site/birding/`，按消息时间倒序显示，滚动自动加载。

## 当前范围

- SouthBayBirds、peninsula-birding、SFBirds、EBB-Sightings、northbaybirds。
- 只发布标题、来源列表、收到消息的时间、原帖链接；不复制正文、照片、邮箱或作者名。
- 删除标题里的邮件列表前缀，标记回复/转发，按来源消息 ID 去重；回复不算新的目击，社区所在区域不等于观测地点。
- 首次补采 7 天；之后每次读取今天和昨天，当前 JSON 保留 30 天，Git 提交历史仍会保留历史版本。
- **尚未实现**跨来源事件合并、鸟种和地点的正文提取、观察者人数计算。eBird 暂只提供原站入口，访问方式和公开发布范围待确认。Facebook、Reddit、Discord 尚未接入。
- `samples/` 是早期人工研究样本，保留在本地，不进入公开仓库或在线 feed。

## 运行

Python 3.12+，仅标准库：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/collect.py
python3 scripts/collect.py --days 7   # 手动补采（最多 30 天）
gh workflow run collect.yml --repo lincleejun/birding
```

macOS python.org 安装的 Python 若缺少 CA，可完成它的 Install Certificates.command，或运行时指定系统证书 `SSL_CERT_FILE=/etc/ssl/cert.pem`；不要关闭 HTTPS 验证。

## 数据语义与故障

`reported_at` 是 Sialia 页面显示的收到消息时间，**未带时区**，不是实际观察时间。`first_seen_at`、`generated_at`、`last_success_at` 是带偏移的 UTC 时间。列表按 `reported_at` 倒序。网页标明时区限制；来自同一来源的墙上时间仍可比较先后。

`sources.sialia.status` 为 `ok` / `partial` / `error`。任何一天访问或解析失败都会记录错误，并保留已保存的消息；失败不更新完整采集的 `last_success_at`。页面超过 3 小时未完整成功会显示陈旧提示。云端任务先提交并发布故障状态，再标记运行失败；测试失败则停止发布。

数据只通过静态 GitHub Pages 发布。outman.cc 的 `/birding/feed.json` 用 Vercel rewrite 代理这份静态文件，浏览器不调用 GitHub API，也不需要密钥。

## 调度与维护

计划 `17 * * * *`（UTC），每小时运行一次，GitHub 调度可能延迟或跳过，不能当作准点服务。公开仓库长期无活动时定时任务可能停用，需查看 Actions 状态。首次验证后应观察至少 24–48 小时，检查源状态、消息新增与失败次数；目前不声称完成长期稳定性验证。

工作流串行执行，防止两个采集任务同时写数据。人工修改前先 `git pull --ff-only`，避免与机器人提交冲突；推送冲突会明确失败，不强推。若需停止试运行：

```sh
gh workflow disable collect.yml --repo lincleejun/birding
```

网页改动可在 `outman.me` 仓库 revert 对应提交后推送，沿用其 Vercel 自动部署。数据发布遵循来源条件；标题索引并不代表取得正文或图片的再发布权。

本地的 `Context.md`、研究文档和 `samples/` 保留作后续扩展参考，不发布到这个公开仓库。
