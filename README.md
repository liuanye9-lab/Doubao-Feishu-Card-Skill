# Doubao Feishu Card Skill

面向豆包工作平台的独立飞书 Card 2.0 Skill。它把长文案、案例、通知、流程或数据材料转成短而可扫、可继续编辑、可导入 CardKit 的卡片。

核心能力：

- 一次只问一个问题，澄清到 95% 后才制作；按钮需求单独确认。
- 自动压缩长文，默认 1 句摘要、3–5 个关键点、3–6 个语义 Emoji。
- 真实数据自动选择原生柱状图、扇形图或折线图；不编造数字。
- 静态信息视觉默认使用豆包工作内置 Seedream 5.0 Pro；文字密集且结构化的信息图才自动切换到自包含 HTML → 本机 Chrome → PNG。
- 时间线、多步骤流程、状态变化或前后对比自动使用 Seedance 2.5 直出 GIF。
- GIF 通过真实 `img_key` 优先嵌入 CardKit；关键事实和按钮仍保留在原生 Card。
- 只用 `.card` 文件导入 CardKit，避免 `.json` 方言报错。
- CardKit 二次编辑兼容门会清理 `brand_*` 非法颜色引用。
- Bot 预览可选，不是 CardKit 交付前置。

## 安装

### 文字与交付可靠性更新 · 2026-09-07

正文统一进入可编辑高亮块，保留步骤编号；完整句压缩替代省略号截断，长日期和说明不再挤入大字指标格，制作备注不进入正文。视觉验收须记录桌面/手机截图与文件哈希；本地预览、远程导入和编辑保存分别记录。已有 CardKit 草稿支持 `push-cardkit --template-id` 按版本更新，失败不自动新建。

保留豆包内置 Seedream/Seedance 与 GIF 校验，不用 Codex 模型配置覆盖。详见 [文字与验收契约](references/text-and-review-contract.md)。

将发布页中的 `doubao-feishu-card.zip` 导入豆包工作，或把仓库目录作为 Skill 安装。入口文件是 [`SKILL.md`](./SKILL.md)。

运行要求：Python 3.9+；媒体检验使用 Pillow；可选 `tsx` 用于结构 Schema 校验。仓库不包含任何飞书凭据或模型密钥。

## 最简调用

```bash
python3 scripts/stable_card.py \
  --text-file ./copy.txt \
  --output-dir outputs \
  --name my-card
```

媒体路由默认为 `--motion auto`：

```bash
# 强制 Seedance 2.5 GIF
python3 scripts/stable_card.py --text-file ./copy.txt --name my-card --motion on

# 强制 Seedream 5.0 Pro 静态图
python3 scripts/stable_card.py --text-file ./copy.txt --name my-card --motion off
```

静态生成完成后登记：

```bash
python3 scripts/register_image_generation.py \
  --image outputs/my-card/hero.png \
  --prompt outputs/my-card/my-card.image-prompt.md
```

如果报告中的 `render_strategy` 为 `html_infographic_to_png`，流程会自动生成并渲染 `my-card.infographic.html`，再登记同一目录的 `hero-generation.json`：

```bash
python3 scripts/render_html_infographic.py \
  --html outputs/my-card/my-card.infographic.html \
  --output outputs/my-card/hero.png \
  --width 1200 --height 1800 --scale 2
python3 scripts/register_html_render.py \
  --image outputs/my-card/hero.png \
  --html outputs/my-card/my-card.infographic.html \
  --prompt outputs/my-card/my-card.html-prompt.md
```

HTML 只是精确排版的可编辑源，不是 CardKit 导入文件；真实按钮仍在原生 Card，上传前必须通过 HTML 源、PNG 和提示词哈希门禁。

动态生成完成后登记：

```bash
python3 scripts/register_motion_generation.py \
  --asset outputs/my-card/hero.gif \
  --prompt outputs/my-card/my-card.motion-prompt.md
```

上传后把真实 `img_key` 写回：

```bash
python3 scripts/stable_card.py \
  --resume outputs/my-card/my-card.spec.json \
  --hero-img-key '<real_img_key>'
```

## 状态

- `needs_image`：按 `render_strategy` 继续调用 Seedream 或完成 HTML→PNG，登记 PNG、上传并重编译。
- `needs_gif`：继续调用 Seedance、登记 GIF、上传并重编译。
- `needs_visual_review`：查看媒体与原生卡片，记录实际检查结论。
- `ready`：结构、媒体 provenance、真实 `img_key`、视觉验收和安全门均通过。
- `blocked`：先按报告修复来源或结构问题。

## CardKit

CLI 导入使用裸 `outputs/<name>/<name>.card`，网页导入使用 `outputs/<name>/<name>.cardkit.card`。禁止把 `.json` 文件导入 CardKit。

```bash
# 本地预检
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/my-card/my-card.card \
  --name "我的卡片" \
  --dry-run

# 用户明确授权后执行并回读模板证据
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/my-card/my-card.card \
  --name "我的卡片" \
  --confirm \
  --record outputs/my-card/my-card.cardkit-import-result.json
```

## 验证

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -p 'test_*.py'
# 可选：使用当前宿主安装的 Skill 校验工具
```

完整规则、媒体模型、交付证据和质量门见 [`SKILL.md`](./SKILL.md)、[`references/html-infographic-route.md`](./references/html-infographic-route.md) 与 [`references/`](./references/)。

## 运行时边界

`Seedream 5.0 Pro` 与 `Seedance 2.5` 是用户确认的豆包工作宿主能力标签。仓库负责路由、提示词、文件契约和 provenance 校验，但不能在 Codex 环境中代替豆包工作执行其内置模型。默认保持模型优先；只有文字密集结构化信息图才使用受控、自包含 HTML→PNG fallback。真实运行时必须记录宿主实际暴露的工具与模型 ID；未暴露时写 `platform-managed`，不得伪造。

## 2026-09 可靠性更新

已补齐指标进入案例信息图、限定值/千分位解析、媒体真实解码、仅 `.card` 导入、保留编辑的 `--resume` 与哈希绑定的视觉验收。正文目标约 200–350 字；900 字只是拒绝线。安装先执行 `python3 -m pip install -r requirements.txt`；完整执行规则见 [可靠性闭环](./references/reliability-workflow.md)。

自动测试使用明确标注的合成媒体与 mock，不作为真实宿主/远程 CardKit 成功证据。

默认生图提示词已统一为五套模板共享的 Apple 官网式层级纪律 + 高级信息设计基线：中等字重的现代无衬线标题、轻盈数字、克制标签、单一强调色、1.5 倍留白；允许 1–3 个有信息作用的透明磨砂玻璃层、动态模糊、柔和光晕和低饱和渐变，并在实际卡片底色上验收。版式按真实指标数量或流程结构适配，不为套模板补造数据。具体可调参数见 [`presets/image-art-direction.json`](./presets/image-art-direction.json) 与 [`presets/preset-index.json`](./presets/preset-index.json)。

新增 [图文按钮协同排版](./references/layout-coordination.md)：轻量通知可自动选横幅，原生模块集中标题/说明/行动，按来源标题区间绑定按钮，保留显式短按钮文案；信息图完整展示而非居中裁切。新增模型优先 + HTML 信息图 fallback 路由，已有 spec 续编译不自动重排，但新生成和显式模板会统一采用五套生产模板基线。

### 五套生产模板

系统会按内容自动选模板，也支持 `--template <template_id>` 由用户指定：
`apple-minimal`（Apple 高级信息设计）、`swiss-grid`（瑞士国际主义网格）、
`modern-editorial`（现代杂志编辑风）、`data-narrative`（数据叙事信息图）、
`product-showcase`（产品发布/案例展示）。五套模板共用克制配色、1.5 倍间距、极致留白、
现代无衬线、细线/通栏分隔和微圆角基线；颜色为内容服务，允许受控的低饱和渐变、磨砂玻璃和柔和环境阴影，不使用廉价装饰、重阴影或密集卡片墙。

### 五套模板实测案例（2026-09-06）

以下 5 条均已用 `stable_card.py` 跑过本地源锁定、模板路由、Card 2.0 编译和 `.card` 输出；未伪造图片 key，未把未完成的远程发送冒充为成功。

| 输入主题 | 场景 | 自动模板 | 视觉表达建议 | 本地验收结果 |
| --- | --- | --- | --- | --- |
| “AI 先锋训练营报名开启，9 月 10 日—12 日完成学习、提交、展示” | `event-info` | `apple-minimal` | Seedream 5.0 Pro 轻量主题首图 + 原生入口按钮 | `.card` / wrapper / spec 通过编译 |
| “9 月 10 日准备 → 9 月 12 日提交 → 9 月 20 日评审 → 9 月 30 日展示” | `activity-timeline` | `swiss-grid` | 单轨时间线 + 日期/动作层级 | `.card` / wrapper / spec 通过编译 |
| “背景：案例资料分散；做法：统一收集；结果：查找时间 30 分钟降到 5 分钟” | `case-showcase` | `modern-editorial` | 问题—做法—结果关系图 + 案例摘要 | `.card` / wrapper / spec 通过编译 |
| “提交 48 个、评审 36 个、入选展示 12 个，评审提升 20%” | `event-recap` | `data-narrative` | 真实指标优先，按数据选择柱状/对比图 | `.card` / wrapper / spec 通过编译 |
| “案例卡片支持信息图、作品链接和一键提交” | `prelaunch-promo` | `product-showcase` | 产品价值首屏 + 单一真实行动 | `.card` / wrapper / spec 通过编译 |

另做了一个结构化长文专项：显式选择 `html_infographic_to_png` 后，`case-showcase` 自动落到 `modern-editorial`，生成自包含 HTML、`hero.png` 和 provenance；并验证标题会压缩为“案例复盘”，不会把整段源文案塞进大标题。HTML/PNG 本地链路通过，仍需真实图片上传、视觉复核和 CardKit 回读后才能标记为 `ready`。
