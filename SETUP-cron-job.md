# 触发源：cron-job.org（已配置完成）

## 为什么不用 GitHub 自带的定时器

GitHub Actions 的 `schedule` **不可靠**，实测两次事故：

- 2026-11-20：三次 cron（09:15 / 10:30 / 12:50）全部被丢弃，整天没跑
- 2026-11-23（周一）：09:15、10:30 又被丢弃，盘中完全没推送

GitHub 官方文档也写明高负载时会延迟甚至丢弃。所以主触发源改成 cron-job.org，`schedule` 仅作兜底。

## 当前配置（jobId 8921052）

| 项 | 值 |
|---|---|
| URL | `https://api.github.com/repos/JokePran/weibo-monitor/actions/workflows/monitor.yml/dispatches` |
| 方法 | `POST` |
| Header `Authorization` | `Bearer <GitHub token>` |
| Header `Accept` | `application/vnd.github+json` |
| Header `Content-Type` | `application/json` |
| Body | `{"ref":"main"}` |
| 时区 | `Asia/Shanghai` |
| 星期 | 周一至周五（wdays `[1,2,3,4,5]`，**0=周日**） |
| 小时 | 9–15 |
| 分钟 | 每 5 分钟（0,5,10,…,55） |

预期返回 `204 No Content`。

## 用 API 修改/重建（不用开网页）

```bash
KEY='<cron-job.org API key>'

# 查看
curl -s -H "Authorization: Bearer $KEY" https://api.cron-job.org/jobs/8921052

# 修改（PATCH，可只传变化字段）
curl -s -X PATCH -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  https://api.cron-job.org/jobs/8921052 \
  -d '{"job":{"enabled":true}}'
```

**最容易踩的坑**：请求头和 body 必须放在 `extendedData` 里，放顶层会被静默忽略：

```json
{
  "job": {
    "extendedData": {
      "headers": {"Authorization": "Bearer ghp_xxx", "Accept": "application/vnd.github+json",
                  "Content-Type": "application/json", "User-Agent": "cron-job.org"},
      "body": "{\"ref\":\"main\"}"
    }
  }
}
```

## 验证

```bash
# cron 侧执行历史（看 httpStatus 是否 204）
curl -s -H "Authorization: Bearer $KEY" https://api.cron-job.org/jobs/8921052/history
```

GitHub 侧看有没有新记录：https://github.com/JokePran/weibo-monitor/actions

## 整套链路（全部在云端，电脑关机也照常工作）

```
cron-job.org（每 5 分钟）
  → GitHub Actions workflow_dispatch
    → 长驻任务跑 09:10~15:05，每 4 分钟抓一次微博
      → pushplus → 手机微信
```

本地不参与任何环节。

## 排障判据

- **Actions 没有当天记录** → cron 侧问题：查 history 的 httpStatus（401 = token 过期；404 = 仓库/文件名错）
- **有记录但 `last_check` 在动、`last_mid` 不动** → 抓取端滞后（新浪 CDN），需给 `MIRROR_URLS` 加新入口
- **推送成功但手机没收到** → pushplus 额度（免费 200 条/天）或手机通知设置

## 并发说明（看到 pending / cancelled 属正常）

长驻任务在盘中一直占着并发组，期间的每 5 分钟触发会生成一个**排队**的运行；
新触发会把上一个排队的顶掉，所以列表里会出现 `cancelled`。这是预期行为，不影响推送。
长驻任务一旦中途挂掉，下一次触发会自动把它重新拉起。
