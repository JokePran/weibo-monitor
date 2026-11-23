# 用 cron-job.org 触发（解决 GitHub 定时器失联）

## 为什么要这一步

GitHub Actions 自带的 `schedule` 定时触发**不可靠**，实测两次事故：

- 2026-11-20：三次 cron（09:15 / 10:30 / 12:50）全部被丢弃，整天没跑
- 2026-11-23（周一）：09:15、10:30 两次又被丢弃，盘中完全没推送

GitHub 官方文档也写明：高负载时会延迟甚至丢弃定时任务。这不是配置问题，改 cron 表达式治不了。

所以改用外部免费定时服务 **cron-job.org** 每 5 分钟调用一次 GitHub 的 `workflow_dispatch` 接口。原来的 `schedule` 保留作兜底。

---

## 第一步：新建一个专用 GitHub Token

不要复用之前那个权限很大的经典 token，新建一个**只对这个仓库、只有 Actions 权限**的细粒度 token，泄漏风险最小。

1. 打开 https://github.com/settings/personal-access-tokens/new
2. 填写：
   - **Token name**：`cron-trigger-weibo`
   - **Expiration**：90 days（到期后重新生成即可）
   - **Resource owner**：`JokePran`
   - **Repository access**：选 `Only select repositories` → 选中 `weibo-monitor`
3. 展开 **Permissions → Repository permissions**，只给一项：
   - **Actions** → `Read and write`
   - 其余全部保持 `No access`
4. 点 **Generate token**，复制 `github_pat_...` 开头的字符串（**只显示一次**）

> 这个 token 只能触发这一个仓库的工作流，删掉也不影响其他任何东西。

---

## 第二步：在 cron-job.org 建任务

1. 打开 https://cron-job.org 注册（邮箱即可，免费）
2. 登录后 **Settings → Timezone** 改成 **Asia/Shanghai**（很重要，否则时间会差 8 小时）
3. 点 **CREATE CRONJOB**，按下表填写：

| 字段 | 填写内容 |
|---|---|
| **Title** | `微博监控触发` |
| **URL** | `https://api.github.com/repos/JokePran/weibo-monitor/actions/workflows/monitor.yml/dispatches` |
| **Schedule** | Every **5** minutes |
| **Days** | 勾选 **Mon / Tue / Wed / Thu / Fri**，取消周末 |
| **Hours** | 只勾 **09:10 – 15:05** 这一段 |
| **Request method** | `POST` |

4. 展开 **Advanced**（高级设置），加三个 Header：

| Header 名称 | 值 |
|---|---|
| `Authorization` | `Bearer 你第一步生成的 github_pat_...` |
| `Accept` | `application/vnd.github+json` |
| `Content-Type` | `application/json` |

5. **Request body** 填：

```json
{"ref":"main"}
```

6. 保存。点任务右侧的 **TEST RUN** 手动跑一次。

---

## 第三步：确认成功

TEST RUN 之后，去这里看是否多了一条运行记录：

https://github.com/JokePran/weibo-monitor/actions

- **出现新记录**（哪怕日志写着"非监控窗口，立即退出"）→ 说明触发通了
- **没出现记录** → 检查 header 里的 token 是否正确、是否给了 Actions 读写权限

---

## 之后的行为

- 每个交易日 09:10 起，每 5 分钟触发一次
- 第一次成功的触发会启动一个**长驻任务**，一直跑到 15:05 收盘自动退出
- 期间的后续触发会进入排队（GitHub 并发组会合并），不会重复跑
- 收盘后 / 半夜 / 周末的触发会**立即退出**，不消耗额度

## 如果哪天又没收到推送

先看 https://github.com/JokePran/weibo-monitor/actions 有没有当天的运行记录：

- **没有记录** → 是 cron-job.org 那边停了（登录看看任务是否被禁用），或 token 过期了
- **有记录但日志显示"没有新微博"** → 抓取端滞后（新浪 CDN 问题），需新增抓取入口
- **有记录且推送成功** → 检查 pushplus 额度或手机通知设置
