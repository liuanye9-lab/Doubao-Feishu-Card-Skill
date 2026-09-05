# 开发与回归指南

## 架构

公开入口只有 `scripts/stable_card.py`。它将自然语言参数交给 `doubao_pipeline.py`，内部顺序固定为：

```text
source_text
  → input_brief / source hash
  → 场景、内容和视觉方法路由
  → 信息分工与长文压缩
  → Seedream/Seedance/HTML→PNG 自动媒体决策（模型优先）
  → editable spec + visual spec + motion spec
  → raw Card 2.0 + CardKit wrapper 同源编译
  → 密度、Emoji、动作、图表、颜色、媒体和 CardKit 门禁
  → 真实 img_key 回写与重编译
  → 用户授权后 CardKit 导入和回读
```

主要模块：

| 文件 | 职责 |
|---|---|
| `stable_card.py` | 唯一稳定入口；参数收口，不执行远程写入 |
| `doubao_pipeline.py` | 总编排、状态和报告 |
| `content_intelligence.py` | 信息分工、长文压缩、Emoji 和按钮候选 |
| `auto_layout.py` / `plan_card.py` | 场景、布局与组件计划 |
| `visual_spec.py` | Seedream 可编辑视觉源 |
| `html_infographic.py` / `render_html_infographic.py` | 文字密集结构化信息图的自包含 HTML 生成与本机浏览器导出 |
| `register_html_render.py` | HTML→PNG source/hash provenance |
| `motion_strategy.py` | Seedance 自动路由、motion spec 与提示词 |
| `generate_card.py` | Card 2.0 编译 |
| `cardkit_format.py` | raw Card 与 wrapper 同源转换、原生颜色清洗 |
| `register_image_generation.py` | Seedream PNG provenance |
| `register_motion_generation.py` | Seedance GIF 格式、帧与 provenance |
| `media_assets.py` | 用户媒体、图集与 GIF 的只读 manifest |
| `validate_card.py` | Card 安全与兼容门 |
| `feishu_cli.py` | 上传、CardKit、预览和发送；远程写入必须显式确认 |
| `preview_card.py` | 可选本地调试，不是交付证据 |
| `package_skill.py` | 生成豆包工作可导入 ZIP |

## 媒体状态机

静态内容：

```text
needs_image
  → 默认 Seedream 5.0 Pro 直出 hero.png；密集结构化内容选择 HTML→PNG
  → register_image_generation.py 或 render_html_infographic.py + register_html_render.py
  → upload-image 得到真实 img_key
  → stable_card.py --resume <spec> --hero-img-key ...
  → needs_visual_review → 实际检查 → finalize_card.py --record-review
  → ready
```

流程、时间线或状态变化：

```text
needs_gif
  → Seedance 2.5 直出 hero.gif
  → register_motion_generation.py
  → upload-image 得到真实 img_key
  → stable_card.py --hero-img-key ...
  → ready
```

动态模式只要求 Seedance GIF，不同时强制生成 Seedream PNG。原生 Card 必须保留关键事实和动作，因而 GIF 不是唯一信息载体。

HTML fallback 只使用自包含、静态、固定视口的源文件；不加载外链/脚本，不画按钮，也不进入 CardKit。`--resume` 沿用 spec 已保存的 `render_strategy`，不会因为环境变化重新分流。

## Provenance 规则

静态门检查：

- `hero.png` 和 `hero-generation.json` 同目录；
- `generation_family` 为 `seedream-class`；
- 生成模式属于 runtime profile；
- 图片哈希、提示词路径和提示词哈希匹配；
- 记录实际工具；具体模型 ID 未暴露时写 `platform-managed`。
- 若 `render_strategy=html_infographic_to_png`，检查 HTML 路由标记、无脚本/外链、`generation_family=html-render`、HTML/PNG/提示词哈希和 `post_processing=none`。

动态门检查：

- `hero.gif` 是真实 GIF，不是改后缀的视频或静态图；
- 至少两帧；
- `hero-motion-generation.json` 的 `generation_family` 为 `seedance-class`；
- 模式为 `seedance_2_5_direct_gif`、输出为 `gif`；
- 资产哈希和提示词哈希匹配；
- `post_processing=none`。

## CardKit 文件方言

- `<name>.card`：裸 Card 2.0；CLI 模板导入、API 和 Bot 使用。
- `<name>.cardkit.card`：网页导入 wrapper；顶层 `{name,dsl,variables}`。
- `<name>.cardkit.json`：内部兼容文件，禁止用于 CardKit 导入。

`cardkit_format.py` 会清洗 `config.style.color` 和正文中的 `brand_*` 引用，防止用户在 CardKit 二次编辑时触发 `invalid color`。保存后如有条件，应回读 DSL 再跑同一校验。

## 本地回归

```bash
python3 -m compileall -q scripts tests
python3 -m unittest discover -s tests -p 'test_*.py'
# 可选：在装有 skill-creator 的环境调用其 quick_validate.py，勿依赖作者机器路径
```

测试至少覆盖：

- 静态文案进入 `needs_image`，Seedream provenance + 真实 key + 实际视觉验收后进入 `ready`；
- 多步骤流程进入 `needs_gif`，Seedance GIF provenance + 真实 key 后进入 `ready`；
- 强制 `--motion off` 能回到静态；来源明确“不要动图”不会被覆盖；
- 伪 GIF、单帧 GIF、哈希或提示词不匹配被拒绝；
- 长文密度、Emoji 数量、真实按钮和数据图表门有效；
- 文字密集结构化内容自动进入 HTML→PNG，短文仍保持模型优先，HTML provenance 篡改会被上传门拒绝；
- raw Card 与 wrapper DSL 同源；非法颜色别名被清理；
- `.json` 不进入 CardKit 导入路径；dry-run 不被当成成功。

## 打包

```bash
python3 scripts/package_skill.py
unzip -t dist/doubao-feishu-card.zip
```

ZIP 只有一个顶层目录 `doubao-feishu-card/`，包含 `SKILL.md`、`agents/`、`scripts/`、`presets/`、`references/`、`scenes/`、`examples/` 和测试；排除 `.git`、缓存、历史输出和 ZIP 自身。

## 远程交付

所有远程动作先 dry-run，再在用户明确授权后使用 `--confirm`。CardKit 成功要求：

1. CLI 返回 `template_id`；
2. template get 成功；
3. template list 命中同一模板。

CLI 会话不可用时才使用已登录浏览器导入 `.cardkit.card`，并以“我的卡片”名称匹配和编辑页可打开作为双证据。Bot 预览仅在用户明确要求时执行，不是 CardKit 成功前置。

## 运行时限制

本仓库不能在非豆包工作环境中执行平台内置 Seedream 5.0 Pro 或 Seedance 2.5。它能确定媒体路由、生成提示词、校验产物和构建 Card；实际模型调用必须由导入后的豆包工作宿主完成，并留下可观察 provenance。
