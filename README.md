# vp-pipeline — A7A 全自动短视频生产线

24h 无人值守运行在 Radxa A7A 上：**话题 → 文案 → 配音 → 画面 → 成片 →（可选）发布**。

**单条耗时约 3 分钟**（实测 2 分 52 秒）。已上线 systemd 定时任务，每天自动跑 4 次。

## 架构

```
① 话题       topics.txt 轮换取用（也可命令行指定）
   ↓
② 文案       LLM（NVIDIA NIM，流式）  →  script.txt + meta.json
   ↓
③ 配音       edge-tts              →  tts.mp3 + tts.srt（毫秒级时间轴）
   ↓
④ 画面       html-video 多帧渲染    →  每帧 HTML，时长 = SRT cue 时长
   ↓
⑤ 混音       ffmpeg                →  final.mp4（音画同步误差 <0.03s）
   ↓
⑥ 发布       biliup（默认关闭）      →  B站
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `run_pipeline.sh` | **总调度**（定时器调用的入口） |
| `gen_script.py` | LLM 写文案 + 标题/标签 |
| `gen_video_srt.mjs` | SRT 驱动多帧渲染 + ffmpeg 混音 |
| `publish.py` | biliup 投稿封装 |
| `vp-pipeline.service` | systemd 服务定义 |
| `vp-pipeline.timer` | systemd 定时器 |
| `topics.txt` | 话题池（每行一个） |
| `config.yaml` | LLM/TTS/视频/发布配置 |

## 部署位置（板子）

```
~/vp/                          # 工作目录
├── run_pipeline.sh 等脚本
├── config.yaml                # ⚠️ 含 API key，权限 600
├── topics.txt
├── videos/{name}/             # 每条的产物
│   ├── script.txt  meta.json
│   ├── tts.mp3     tts.srt
│   └── final.mp4
└── logs/
    ├── run-YYYYmmdd-HHMMSS.log   # 每次运行日志
    └── success.log               # 成功记录（每行一个目录）
```

## 定时任务

```bash
# 查看状态
systemctl status vp-pipeline.timer
systemctl list-timers vp-pipeline.timer

# 看某次运行日志
journalctl -u vp-pipeline.service -n 50

# 手动触发一次
sudo systemctl start vp-pipeline.service

# 暂停 / 恢复
sudo systemctl stop vp-pipeline.timer
sudo systemctl start vp-pipeline.timer
```

**计划**：每天 `02:00 / 08:00 / 14:00 / 20:00`，随机延迟 ≤10 分钟错峰，错过的时间点开机后补跑。

## 手动用法

```bash
cd ~/vp

# 从话题池取下一个
./run_pipeline.sh

# 指定话题
./run_pipeline.sh "AI 视频生成的技术原理"

# 生成 + 自动发布（需先 biliup login）
PUBLISH=1 ./run_pipeline.sh "话题"

# 调字数 / 音色 / 语速
CHARS=400 VOICE=zh-CN-XiaoxiaoNeural RATE=+0% ./run_pipeline.sh "话题"

# 只渲染（已有 tts.srt / tts.mp3）
node ~/html-video/gen_video_srt.mjs \
  --srt tts.srt --audio tts.mp3 --out final.mp4 \
  --name my-video --title '主标题|高亮段|收尾' --kicker 'AI · 科技'
```

## 行为边界（重要）

### 自动上传（PUBLISH=1，**已开启**）

生成后自动投稿到 B站。**前置条件**：必须先登录一次（见下节），否则会**跳过并提示**，不会失败。

发布成功后会在该条目录写 `.published` 标记文件 —— 这个标记**同时是清理逻辑的删除凭据**。

### 自动删除（CLEANUP=1，**已开启**）

**保守策略，四重安全约束（缺一不可）**：

| # | 约束 | 说明 |
|---|---|---|
| 1 | 只处理 `~/vp/videos/` 下的一级子目录 | 不会碰别的地方 |
| 2 | 只删**带 `.published` 标记**的 | **未发布的成品永不删** |
| 3 | 必须超过 `RETENTION_DAYS` 天（默认 7） | 新视频不删 |
| 4 | 至少保留最近 `MIN_KEEP` 条（默认 10） | 兜底，不会清空 |

路径还会做二次校验（必须匹配 `$VP/videos/v20*`）。每次删除都记进 `logs/cleanup.log`（时间 + 路径 + 大小）。

**可调**（改 `/etc/systemd/system/vp-pipeline.service` 后 `daemon-reload`）：
```ini
Environment=RETENTION_DAYS=7    # 保留天数
Environment=MIN_KEEP=10         # 最少保留条数
Environment=CLEANUP=0           # 关闭清理
```

**单独测清理**（安全，不生成视频）：
```bash
cd ~/vp
MIN_KEEP=1 ./run_pipeline.sh --cleanup-only
cat logs/cleanup.log
```

### 其他

- **发布前建议先看成品**：临时 `PUBLISH=0 ./run_pipeline.sh "话题"`，检查 `final.mp4` 再决定。

## 发布前置（一次性，必须人工）

### 方式一：只发 B站（`backend: biliup`，默认）

```bash
~/biliup/biliupR-v1.2.4-aarch64-linux/biliup login
```

⚠️ **这条必须在真实终端里跑**（SSH 交互会话 / 串口 / 本机终端）——
在脚本里重定向会报 `IO error: not a terminal`。跑完会出二维码，用 B站 App 扫码，
成功后生成 `~/vp/cookies.json`。

### 方式二：多平台（`backend: sau`）

支持 10 个平台：`douyin / kuaishou / xiaohongshu / bilibili / tencent(视频号) /
alipay / weibo / hupu / youtube / baijiahao`。

每个平台登录一次（**同样需要真实终端**）：

```bash
cd ~/sau
.venv/bin/sau douyin      login --account 我的抖音
.venv/bin/sau xiaohongshu login --account 我的小红书
.venv/bin/sau kuaishou    login --account 我的快手
.venv/bin/sau bilibili    login --account 我的B站
.venv/bin/sau youtube     login --account 我的YouTube
```

然后在 `config.yaml` 里把对应平台 `enabled` 改成 `true`，并把 `backend` 改成 `sau`
（或 `both` 同时跑 biliup + sau）：

```yaml
publish:
  backend: "sau"
  platforms:
    - { name: "douyin",      account: "我的抖音",   enabled: true }
    - { name: "xiaohongshu", account: "我的小红书", enabled: true }
```

**国际平台（YouTube / TikTok）走代理** —— `~/sau/conf.py` 里已配好：
```python
YT_PROXY = "http://127.0.0.1:7890"   # ghboost 的 mihomo 节点
```
实测：直连 YouTube 超时 15s，走 7890 是 200/2s。

### 手动测试发布（不真发）

```bash
cd ~/vp
~/venv-tts/bin/python publish.py --video videos/xxx/final.mp4 --meta videos/xxx/meta.json --dry-run
# 只测某几个平台
~/venv-tts/bin/python publish.py --video xxx.mp4 --meta meta.json --backend sau --only douyin,xiaohongshu --dry-run
```

**没登录时**：会跳过该平台并打印提示，其他平台和流水线其余部分不受影响。


## 环境依赖

| 组件 | 版本 | 位置 |
|---|---|---|
| Python | 3.13.5 | 系统 |
| edge-tts | 7.2.8 | `~/venv-tts` |
| Node.js | v20.19.2 | 系统 |
| pnpm | 9.15.9 | 全局 |
| ffmpeg | 7.1.5 | 系统 |
| Chromium | 120 / Playwright 153 | `~/.cache/ms-playwright` |
| html-video | Apache-2.0 | `~/html-video` |
| biliup | 1.2.4 (arm64) | `~/biliup/biliupR-v1.2.4-aarch64-linux/` |

## 踩过的坑（改代码前先看）

1. **LLM 必须用流式**：NVIDIA NIM 非流式响应 220s+ 直接超时，`stream:true` 后 10s 出结果。
2. **NVIDIA NIM 模型可用性受限**：列表里有 81 个模型，但很多返回 404（不在账户范围）。
   实测可用：`mistralai/mistral-nemotron`。
3. **html-video 单模板渲染时长不可控**：`duration:'auto'` 会探测动画实际长度。
   要精确控制**必须走多帧 storyboard**（`writeContentGraph` + `writeFrameHtml`）。
4. **systemd `Environment=` 含空格要加引号**：`Environment="KICKER=AI · 科技"`。
5. **改 `/etc/systemd/system/` 下的文件时**，`radxa_ssh.py --sudo` 的命令里
   别用单引号（会被 `bash -c '...'` 截断）—— 用「写 /tmp → sudo cp」两步法。
6. **pnpm install 要换淘宝镜像**：`pnpm config set registry https://registry.npmmirror.com`
   （官方源会中途无声断掉）。
