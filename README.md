# Doubao Feishu Card Skill

面向豆包工作平台的独立飞书 Card 2.0 Skill。它把长文案、案例、通知、流程或数据材料转成短而可扫、可继续编辑、可导入 CardKit 的卡片。

核心能力：

- 一次只问一个问题，澄清到 95% 后才制作；按钮需求单独确认。
- 自动压缩长文，默认 1 句摘要、3–5 个关键点、3–6 个语义 Emoji。
- 真实数据自动选择原生柱状图、扇形图或折线图；不编造数字。
- 静态信息视觉使用豆包工作内置 Seedream 5.0 Pro。
- 时间线、多步骤流程、状态变化或前后对比自动使用 Seedance 2.5 直出 GIF。
- GIF 通过真实 `img_key` 优先嵌入 CardKit；关键事实和按钮仍保留在原生 Card。
- 只用 `.card` 文件导入 CardKit，避免 `.json` 方言报错。
- CardKit 二次编辑兼容门会清理 `brand_*` 非法颜色引用。
- Bot 预览可选，不是 CardKit 交付前置。

## 安装

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

- `needs_image`：继续调用 Seedream、登记 PNG、上传并重编译。
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

完整规则、媒体模型、交付证据和质量门见 [`SKILL.md`](./SKILL.md) 与 [`references/`](./references/)。

## 运行时边界

`Seedream 5.0 Pro` 与 `Seedance 2.5` 是用户确认的豆包工作宿主能力标签。仓库负责路由、提示词、文件契约和 provenance 校验，但不能在 Codex 环境中代替豆包工作执行其内置模型。真实运行时必须记录宿主实际暴露的工具与模型 ID；未暴露时写 `platform-managed`，不得伪造。

## 2026-09 可靠性更新

已补齐指标进入案例信息图、限定值/千分位解析、媒体真实解码、仅 `.card` 导入、保留编辑的 `--resume` 与哈希绑定的视觉验收。正文目标约 200–350 字；900 字只是拒绝线。安装先执行 `python3 -m pip install -r requirements.txt`；完整执行规则见 [可靠性闭环](./references/reliability-workflow.md)。

自动测试使用明确标注的合成媒体与 mock，不作为真实宿主/远程 CardKit 成功证据。

默认生图提示词已统一为瑞士编辑设计：中等字重的现代黑体标题、等尺度的轻盈数字、克制标签和单一强调色；透明底允许使用，并在实际卡片底色上验收。版式按真实指标数量或流程结构适配，不为套模板补造数据。具体可调参数见 [`presets/image-art-direction.json`](./presets/image-art-direction.json)。
