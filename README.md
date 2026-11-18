# 微博监控推送 · 挖地瓜的超级鹿鼎公

在 **A 股交易日交易时段（9:30–15:00，含午休）**，自动监控微博用户「挖地瓜的超级鹿鼎公」(UID 3962719063) 的新微博，一旦有更新就通过 pushplus 推送到你的手机微信。

部署在 GitHub Actions（免费、云端运行、电脑关机也能跑），每 5 分钟检查一次。

## 工作原理

1. **数据源**：抓取 `sina.cn` 的移动版镜像页（服务端渲染，无需微博登录、无需 Cookie，反爬风险低）。
2. **去重**：每条微博有唯一 `mid`，记录在 `state.json`，只推送没见过的新微博，不会重复。
3. **时段控制**：脚本内判断北京时间是否为交易日（周一至周五，排除 2026 年法定休市日）且在 9:30–15:00 内，否则直接跳过，不浪费推送额度。
4. **状态持久化**：每次运行后把 `state.json` 提交回仓库，实现跨次运行去重。
5. **推送**：调用 pushplus `/send` 接口，HTML 模板，含正文、转发内容和原文链接。

## 部署步骤

### 1. 创建 GitHub 仓库

在 GitHub 新建一个**私有仓库**（Private，避免 token 相关信息泄露；token 本身放 Secrets，不会进仓库）。

### 2. 上传项目文件

把本目录下的所有文件上传到仓库，包括：

- `monitor.py`
- `state.json`
- `.github/workflows/monitor.yml`（注意是隐藏目录 `.github`）

> 可以用网页上传，也可以：
> ```bash
> cd 本目录
> git init
> git remote add origin https://github.com/你的用户名/仓库名.git
> git add -A && git commit -m "init"
> git branch -M main && git push -u origin main
> ```

### 3. 配置 pushplus Token（关键）

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**：

- Name：`PUSHPLUS_TOKEN`
- Value：`你的pushplus用户token`

### 4. 启用 Actions 写权限

进入 **Settings → Actions → General → Workflow permissions**，选择 **Read and write permissions**，并勾选 **Allow GitHub Actions to create and approve pull requests**（如需要）。这是为了让工作流能把 `state.json` 去重状态提交回仓库。

### 5. 手动测试

进入 **Actions** 标签页 → 左侧选「微博监控推送」→ **Run workflow** → 手动触发一次。

- 若当前不在交易时段，日志会显示"非交易时段，跳过"——这是正常的。
- 首次运行会把当前最新微博设为已读基准，**不推送历史微博**（避免刷屏）。
- 想立刻看到推送效果，可在 Actions 里带 `--force` 参数测试（或告诉我，我帮你调整）。

### 6. 自动运行

部署完成后，工作日交易时段会自动每 5 分钟检查并推送。非交易时段静默跳过。

## 首次收到推送的时机

- 部署后**第一条**被推送的微博，是"初始化基准之后"新发布的微博。
- 如果你想从部署那一刻起的下一条更新就开始推送，直接部署即可（首次运行自动初始化）。

## 常见问题

**Q: 为什么是 5 分钟而不是 3 分钟？**
GitHub Actions 的定时任务最小粒度是 5 分钟，官方不支持 3 分钟。5 分钟已足够及时。

**Q: 一天会推送多少条？会不会超 pushplus 额度？**
只推送该博主在交易时段新发的微博。pushplus 实名免费用户微信渠道 200 条/天，正常情况远用不完。脚本在交易时段外不推送。

**Q: 博主发博很多、一次抓到多条怎么办？**
按发文时间顺序逐条推送，每条间隔 0.5 秒，避免触发频率限制（pushplus 限制每分钟 5 次）。

**Q: 节假日会推吗？**
不会。已内置 2026 年 A 股休市日，周末和节假日自动跳过。2027 年需更新 `monitor.py` 里的 `HOLIDAYS_2026`。

**Q: 数据源失效了怎么办？**
如果 `sina.cn` 页面结构变化导致解析不到微博（日志显示"未解析到微博"），需要更新 `parse_posts()` 的正则。可随时找我修。

## 本地调试

```bash
# 抓取并解析，不推送（当前时段外需加 --force）
python3 monitor.py --force --dry-run

# 强制把当前最新微博设为已读基准
python3 monitor.py --force --init
```
