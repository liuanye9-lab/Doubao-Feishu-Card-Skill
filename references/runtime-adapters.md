# 豆包工作运行时适配

本仓库保留成熟卡片工作流的源锁定、信息分工、Card 2.0、CardKit、CLI 和质量门，并把视觉执行层完整适配为豆包工作平台内置模型。模型名称来自用户确认的宿主能力；运行时仍须记录真实可观察的工具与模型 ID，未暴露时写 `platform-managed`。

| 能力 | 豆包工作适配 | 产物 | 硬门禁 |
|---|---|---|---|
| 静态信息视觉 | 默认 Seedream 5.0 Pro / `doubao.image_gen`；文字密集结构化内容可受控切到 HTML→PNG | `hero.png` | 对应模型或 HTML provenance、图片哈希、提示词哈希 |
| HTML 信息图 fallback | `scripts/html_infographic.py` + 本机 Chrome | `hero.png` | 自包含 HTML、固定视口、HTML render provenance；不进入 Card JSON、不绘制按钮/CTA |
| 动态解释视觉 | Seedance 2.5 / `doubao.video_gen` | `hero.gif` | 真实 GIF、至少 2 帧、`hero-motion-generation.json`、资产与提示词哈希 |
| Card 结构 | 原生 Feishu Card 2.0 | `<name>.card` | Python 安全门、可选 TypeScript Schema 门 |
| CardKit 网页导入 | wrapper | `<name>.cardkit.card` | 顶层 `{name,dsl,variables}`，DSL 与 raw Card 同源 |
| CardKit CLI 导入 | Web-backed template import | `<name>.card` | `.card` 扩展名、`template_id` + get/list 回读 |

## 自动媒体决策

`scripts/motion_strategy.py` 在 Card 编译前执行：

- 时间线、多步骤流程、前后对比、状态流转或显式动效要求达到阈值时，选择 `seedance_2_5_direct_gif`。
- 单一状态、纯静态指标、轻量首图或显式“不要动图”时，选择 Seedream 静态模式；文字密集结构化内容才选择 HTML fallback。
- `--motion on|off|auto` 可控制路由；来源中的明确否定优先于强制动效。
- 动态模式不再要求 Seedream 静态伴随图；关键事实、图表和按钮由原生 Card 兜底。

## 模型与 provenance

`presets/runtime-profile.json` 中：

- `generation_model=seedream-5.0-pro` 和 `generation_model=seedance-2.5` 是宿主适配标签。
- `generation_tool` 是预期的宿主内置工具名；登记时应改成实际可观察值。
- 平台未暴露具体模型 ID 时使用 `platform-managed`，不得把配置标签冒充实测证据。
- 所有 AI 媒体 `post_processing=none`。Seedream 直出 PNG；Seedance 直出 GIF；HTML 只在受控 fallback 中导出 PNG；不允许本地合成、补字、转码或二次模型修补。

## GIF 直嵌

CardKit 中的图片节点引用飞书上传后返回的 `img_key`。动态模式上传 `hero.gif`，随后用同一个真实 key 重编译 Card；`card_image_contract.status=embedded_seedance_gif` 才表示动态卡已完成。GIF 文件存在但没有 provenance 或 `img_key` 时仍是 `needs_gif`。

Bot 预览是可选交付面，不是生成、上传或 CardKit 模板导入的前置条件。

## 能力探测是前置条件

CardKit 支持 GIF 与模型工具支持 GIF 输出是两项独立能力。每次先发现宿主工具及输出格式；不得照抄 `doubao.video_gen` 假装宿主存在同名工具，不得发明 `output_format` 参数。可调用工具只支持 MP4 或不可用时返回 `motion_capability_unavailable`，保留草稿并向用户说明；不能改后缀、伪造动图或宣称成功。逻辑 adapter 与实际工具名/响应证据分别登记，未暴露模型 ID 写 platform-managed。
