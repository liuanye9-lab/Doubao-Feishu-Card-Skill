---
name: doubao-feishu-card
description: "面向豆包工作平台，把文案、文档、表格或案例材料转成源锁定的飞书 Card 2.0。先逐问澄清到 95%，再自动压缩长文、加入节制的语义 Emoji、生成来源数据图表和真实按钮；静态视觉使用平台内置 Seedream 5.0 Pro，流程/时间线/状态变化等内容自动改用平台内置 Seedance 2.5 直出 GIF，并优先通过 img_key 嵌入 CardKit。输出可编辑 spec、visual/motion spec、raw .card 与 .cardkit.card，支持 CardKit 导入和可选 Bot 预览。用户提到豆包工作、飞书卡片、CardKit、图文卡、案例卡、数据卡、信息图卡或动态卡片时使用。"
metadata:
  short-description: "豆包原生生图/动图与可编辑飞书卡片"
---

# 豆包飞书卡片 Skill

把用户材料做成一张“先看懂、再行动”的飞书 Card 2.0。默认结果不是长文搬运，而是：1 句摘要、3–5 个关键点、3–6 个节制的语义 Emoji、来源数据图表（如有）、一张信息视觉，以及最多 1 个主按钮和 1 个次按钮。完整原文始终锁定在 `source.txt` 和 `analysis.source_text`。

本 Skill 是独立的豆包工作适配版。静态图调用宿主内置 Seedream 5.0 Pro；动效调用宿主内置 Seedance 2.5，并要求直接生成 GIF，不在本地把视频转成 GIF。CardKit 可直接呈现上传后的 GIF `img_key`；关键事实、图表和按钮仍须保留在原生 Card 中，不能只存在于动画帧。

## 需求澄清门（最高优先级）

全局指令：在回答前先向用户提问，一次只问一个问题；根据回答继续追问，直到有至少 95% 的信心完全理解真实需求、目标与卡片形态，再给出最终方案或开始制作。只有卡片形态清晰了才开始制作。

- 第一条回复只问一个最关键的问题，不同时给方案或生成产物。即使材料完整，也用一个确认问题锁定最终卡片形态。
- 每轮只问一个问题并等待回答，不把多个维度拼成问卷。
- 必须弄清：使用场景与受众、核心信息、视觉形态、静态/动态偏好、交互和交付边界。仍有会实质改变结果的缺口时继续追问。
- 用户没有说明按钮时，单独问：“是否需要补充按钮？”如果回答需要，下一轮只问：“请描述按钮功能或提供真实链接。”
- 达到 95% 后，用一句话复述已理解的目标，然后直接执行。用户纠正时回到单问题追问。
- 澄清门不扩大授权范围。上传图片、发送消息、导入 CardKit、创建或覆盖远程资源仍只在用户明确要求后执行。

## 不可破坏的契约

1. **源锁定**：不得编造标题、日期、数字、人名、URL、状态、效果或图片 key。所有安全改写写入 `analysis.transformations`。
2. **短而可扫**：全卡可见文字默认不超过 900 字；单块不超过 220 字；不把全文塞入折叠区规避密度门。
3. **信息视觉默认开启**：除非用户明确要求无图，否则必须生成真正承载关系、阶段、对比或指标的信息视觉，不接受纯装饰图。
4. **Emoji 有节制**：默认 `semantic`，每个关键模块最多一个，每张卡约 3–6 个；用户要求无 Emoji 时关闭。
5. **按钮必须真实**：图片里禁止按钮、CTA 胶囊、假链接和伪交互。原生按钮只能使用来源中的真实 URL，或已经实现的 application Bot callback/form。
6. **原生事实兜底**：图片/GIF 不能成为唯一事实载体；摘要、关键点、图表、alt 和动作保留在 Card 原生组件中。
7. **可编辑优先**：修改 `.spec.json`、`.visual-spec.json` 或 `.motion-spec.json` 后重编译，不直接手改最终 `.card`。
8. **CardKit 二次编辑兼容**：正文 `text_color` 只用平台原生色名；禁止 `brand_accent`、`brand_gold`、`brand_ink` 等自定义颜色引用，避免二次编辑时报 `invalid color`。
9. **远程结果要回读**：dry-run、HTML 预览或 API `card_id` 都不等于 CardKit 模板成功。模板导入必须回读 `template_id`、template get 和 template list。

## 豆包多模态自动路由

统一配置在 [`presets/runtime-profile.json`](./presets/runtime-profile.json)。配置中的模型名称是用户指定的宿主适配标签；每次真实生成仍要记录宿主实际可观察的工具、模型 ID、文件哈希和提示词哈希，平台未暴露时写 `platform-managed`，不得伪造 provenance。

### 静态视觉：Seedream 5.0 Pro

- `seedream_5_pro_direct_full_card`：2:3 竖版信息图，默认选择。
- `seedream_5_pro_banner_plus_native_card`：约 3:1 横幅首图 + 原生 Card，需显式选择。

Seedream 直接生成最终 PNG。禁止 HTML/CSS、SVG、Pillow 叠字、本地拼接、二次模型补字或任何后处理。生成内容只取自 `information_allocation.image.include`，不把 URL、按钮或长段落画进图片。

### 动态视觉：Seedance 2.5 直出 GIF

`scripts/motion_strategy.py` 自动判断动效是否显著提升理解。以下内容优先进入 `seedance_2_5_direct_gif`：

- 三步及以上的流程、操作路径或工作流；
- 时间线、阶段推进、状态流转；
- 前后对比、转化、升级或演进；
- 用户明确要求 GIF、动图、动画或动态演示。

单一状态、纯指标看板、合规说明或用户明确“不要动图”时保持静态。可用 `--motion on|off|auto` 覆盖；显式“不要动图”始终优先。

Seedance 必须直接输出 `hero.gif`，约 4–8 秒、可循环、移动端可读。禁止先生成 MP4 再本地转换，也禁止本地补帧、截帧或叠字。`register_motion_generation.py` 会拒绝伪 GIF、单帧 GIF、哈希不匹配或缺提示词 provenance 的资产。

## 稳定入口

所有生成只从 [`scripts/stable_card.py`](./scripts/stable_card.py) 进入。内部脚本不作为调用方自由组合的入口。

```bash
python3 scripts/stable_card.py \
  --text-file ./copy.txt \
  --purpose "案例展示" \
  --recipient "项目群" \
  --output-dir outputs \
  --name my-card
```

常用参数：

| 参数 | 用途 |
|---|---|
| `--text` / `--text-file` | 二选一，唯一事实源 |
| `--scene case-showcase` | 强制案例卡“背景—做法—结果”结构 |
| `--purpose` / `--recipient` | 只影响内容分工和语气，不等于发送授权 |
| `--motion auto\|on\|off` | 自动判断、强制动图或强制静态 |
| `--no-image` | 用户明确不要任何图片时使用 |
| `--emoji-mode semantic\|off` | 默认节制语义 Emoji |
| `--link-mode button\|inline` | 控制真实 URL 的原生呈现 |
| `--hero-img-key` | 上传 PNG/GIF 后写入真实 `img_key` 并重编译 |
| `--propose` / `--layout` | 本地输出或选择三种布局方案，不触发远程写入 |

流水线状态：

- `needs_image`：静态卡结构已完成，必须继续调用 Seedream 5.0 Pro、登记并上传 `hero.png`。
- `needs_gif`：动态卡结构已完成，必须继续调用 Seedance 2.5 直出、登记并上传 `hero.gif`。
- `ready`：结构、provenance、真实 `img_key` 和发送门禁均通过。
- `blocked`：来源、结构、安全或兼容性门禁失败，先修复同源 spec 再重跑。

`needs_image` 和 `needs_gif` 都是中间态，不能当成交付完成。

## 媒体生成与登记

静态路径：读取 `<name>.visual-spec.json` 与 `<name>.image-prompt.md`，调用豆包工作内置 Seedream 5.0 Pro，直接保存为 `hero.png`，然后运行：

```bash
python3 scripts/register_image_generation.py \
  --image outputs/my-card/hero.png \
  --prompt outputs/my-card/my-card.image-prompt.md
```

动态路径：读取 `<name>.motion-spec.json` 与 `<name>.motion-prompt.md`，调用豆包工作内置 Seedance 2.5，直接保存为 `hero.gif`，然后运行：

```bash
python3 scripts/register_motion_generation.py \
  --asset outputs/my-card/hero.gif \
  --prompt outputs/my-card/my-card.motion-prompt.md
```

随后用 `scripts/feishu_cli.py upload-image` 获取真实 `image_key`，再以 `--hero-img-key` 重跑稳定入口。Bot 预览不是生成或 CardKit 导入的必需步骤。

## 默认产物

每次生成落到 `outputs/<name>/`：

- `<name>.source.txt`：锁定原文。
- `<name>.spec.json`：可编辑卡片源。
- `<name>.visual-spec.json` / `<name>.image-prompt.md`：Seedream 静态视觉源与提示词。
- `<name>.motion-spec.json` / `<name>.motion-prompt.md`：Seedance 自动路由结论、动态源与提示词。
- `hero.png` + `hero-generation.json`：静态直出与 provenance（静态模式）。
- `hero.gif` + `hero-motion-generation.json`：动态直出与 provenance（动态模式）。
- `<name>.card`：裸 Card 2.0，供 CLI 模板导入、API 或发送。
- `<name>.cardkit.card`：网页导入 wrapper，顶层为 `{name, dsl, variables}`。
- `<name>.cardkit.json`：仅内部兼容产物，严禁导入 CardKit。
- `<name>.report.json`：路由、密度、Emoji、图表、媒体、CardKit 与发送就绪状态。
- `<name>.prompt-routing.json`、`<name>.plan.json`、`<name>.proposals.json`：可解释的路由、规划和布局候选。

## CardKit 导入硬约束

CardKit 的真实导入文件必须以 `.card` 结尾，禁止导入 `.json`：

- CLI 模板导入使用裸 `<name>.card`。
- 网页“导入卡片”使用 `<name>.cardkit.card` wrapper。
- 不允许通过改后缀把普通 JSON 伪装成 `.card`。
- 导入前必须校验实际方言和扩展名。完整定义见 [`references/cardkit-file-format.md`](./references/cardkit-file-format.md)。

预检：

```bash
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/my-card/my-card.card \
  --name "我的卡片" \
  --dry-run
```

用户明确授权后才执行远程写入：

```bash
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/my-card/my-card.card \
  --name "我的卡片" \
  --confirm \
  --record outputs/my-card/my-card.cardkit-import-result.json
```

CLI 会话不可用时，使用已登录 CardKit 浏览器导入 `.cardkit.card`。Bot 预览仅在用户明确要求时执行；API Card Entity 的 `card_id` 不能代替 CardKit `template_id`。

## 质量验收

交付前至少满足：

- `python3 scripts/validate_card.py outputs/<name>/<name>.card` 通过；`.cardkit.card` 同样通过。
- `readiness.valid=true`、`readiness.image_ready=true`、`readiness.sendable=true`。
- 静态模式 `seedream_output_ready=true`；动态模式 `seedance_output_ready=true`。
- PNG/GIF 中无错字、乱码、错数字、错日期、Logo 水印、假按钮或伪交互。
- GIF 至少两帧、真实 GIF 格式、循环可读；关键事实和按钮仍在原生 Card。
- 可见文字符合预算，Emoji 不堆叠，图表仅来自同口径真实数值。
- 每个按钮都有真实 URL 或已实现回调；没有链接时保持待补，不造链接。
- CardKit wrapper 与 raw Card DSL 同源；二次编辑后无 `brand_*` 非法颜色引用。
- 真实导入有 `template_id` + get/list 回读；仅 dry-run 时明确写 `preview_only`。

更细的实现约束按需读取：

- [`references/information-allocation.md`](./references/information-allocation.md)：图片、原生 Card 和按钮分工。
- [`references/media-and-interaction.md`](./references/media-and-interaction.md)：静态图、GIF、图集和切换器。
- [`references/runtime-adapters.md`](./references/runtime-adapters.md)：豆包工作模型与 provenance 映射。
- [`references/delivery.md`](./references/delivery.md)：上传、导入、预览和发送授权边界。
- [`references/developer-guide.md`](./references/developer-guide.md)：模块职责、调试和回归验证。
- [`references/beauty-review.md`](./references/beauty-review.md)：人工视觉验收。

纯海报、Logo、单纯生图、单纯视频或长文档排版不属于本 Skill；转给相应图片、视频或文档能力。
