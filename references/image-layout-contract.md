# Seedream 5.0 Pro 图片信息契约

这是当前视觉路径生成整张 `hero.png` 的信息契约：默认由 Seedream 5.0 Pro 一次性完成被分配到图片的文字、排版、时间线和 quote；文字密集结构化信息回到原生 Card 高亮块。按钮、CTA、URL 和回调永远由原生 Card 承载。本仓库不提供底图、叠字、拼接或未声明后处理实现。

## 当前版式入口

当前默认使用 `presets/image-art-direction.json` 与 `scripts/image_art_direction.py`：
五套生产模板共享 Apple 官网式现代主义极简基线：精致现代无衬线、标题中等字重、正文与数字轻盈、克制标签、1.5 倍留白、通栏/细线分隔和单一强调色。
下面的网格/坐标是历史可选示例，不是默认强制的 2×2 盒子；不得同时套用多种视觉方案。
图片可以透明；验收时必须放在实际目标背景上检查，而非一律拒绝 alpha。
字体名和字号是模型的视觉指导，不是可编辑字体文件或嵌入承诺。

## 画布和坐标

生成输入必须声明 `image_source`（`real_image` 或 `ai_generated`）和 `image_roles`。`ai_generated` 的完整图片必须对应 Seedream `hero-generation.json`；真实图片必须对应媒体来源/尺寸/哈希元数据。默认角色为 `cover`、`information_carrier`、`text_companion`；历史 `cta_companion` 仅兼容元数据，不得触发按钮绘制。

### 推荐 `reference_card_banner`（1200×720）

| 区域 | 像素坐标（1200×720） | 用途 |
| --- | --- | --- |
| 横向主题 | `(32,24)-(1168,696)` | Seedream 5.0 Pro 在同一张完整信息图中组织主题主体和标题安全区 |
| 标题 | `(64,58)-(704,360)` | 1 个来源锁定 title，最多两行 |
| 快速扫描 | `(64,394)-(1136,666)` | 最多 4 个等宽阶段/事实卡和一条关系线；日期、短动作和事实直接写入图片 |
| 原生补充 | Banner 外部 | 完整时间线、长解释、quote 和 CTA 留在 Card 原生模块，不在 Banner 内重复绘制 |

### 推荐 `timeline_infographic_inside_illustration`（1200×1600）

| 区域 | 像素坐标（1200×1600） | 用途 |
| --- | --- | --- |
| 标题 | `(64,64)-(1136,256)` | 1 个来源锁定 title，最多两行 |
| 视觉关系 | `(64,300)-(1136,760)` | 含日期、阶段和动作文字的完整时间轴/事实图 |
| 信息标题 | `y=804` | 固定结构标签，不承载新事实 |
| 信息卡 | `y=874-1180` | timeline 最多 4 个等宽卡；否则 facts 采用 2×2 |
| 寄语 | `(64,1230)-(1136,1470)` | 仅当源 blocks 有 quote 时显示 |
| CTA | 不设图片区域 | 图片不得出现 CTA、按钮标签、按钮形控件或假链接；真实行动只在原生 Card 中出现 |

Banner 画布逻辑尺寸是 600×360；长图信息版式逻辑尺寸是 600×800；这些只是给 Seedream 5.0 Pro 的构图参考，不是本地绘制坐标。模型路径由 Seedream 5.0 Pro 完成主题、文字、关系图和信息模块；文字密集部分由原生 Card 高亮块承载。

## 信息预算

- `role=title` 必须且只能有一个；标题最多两行，低于最小字号就失败。
- `role=stage` 进入 timeline；最多 4 项，按源文案顺序排列。每项第一行是日期/阶段，其余行是动作或结果。
- timeline 的每一项必须同时出现在 `layout.zones.illustration.relationship_map.text_nodes`，日期是视觉主标签，动作/结果是视觉副标签；它们不是只放在下方原生信息区。
- 图片内时间轴的日期最多两行、动作最多三行；字号降到固定最小值仍放不下时必须失败，不能缩成微型字或静默省略。
- 没有 stage 时，非 title 项进入 facts 的 2×2 网格，最多 4 项。
- 每项白名单文字完整绘制；“放不下”是错误，不是允许缩小到难以阅读或截断的理由。未进入白名单的长文留在 `source.txt`，原生 Card 只保留精简摘要和关键点。
- 被选中的 quote 文本完整绘制，不从 quote 中抽取新句子，也不自动附加鼓励语；过长 quote 留在 `source.txt`，Card 可保留一条精简可读引用。源文案包含合适长度的 quote 时，由同一次 Seedream 5.0 Pro 生成并放在显著、可读的 quote 区。
- 图片内禁止 CTA 索引和按钮视觉。所有真实点击行为、URL、回调和权限仍在原生 Card 2.0 按钮中校验；没有真实目标就不生成按钮。

## 信息与视觉的关系

timeline 的视觉关系图必须展示一条由阶段节点组成的阅读路径；节点用几何图标区分“培训/准备”“提交/检查”“决赛/展示”等语义，同时在节点卡内直接显示源锁定日期和动作文字。图标是视觉编码，不得替代源文字，也不能增加新的事实。

facts 使用对齐的 2×2 盒子、同一字号层级和同一颜色 token；不能每个事实卡使用不同风格的插画。模型路径必须让材质、主题主体、关系图和信息卡在同一次 Seedream 生成中统一完成；文字密集部分回到原生 Card 高亮块，不做本地转图。

## 来源和失败条件

## 能力包路由契约

`prompt_routing.visual_skill_routing` 必须记录：

- `selected_packs`：最多两个本地能力包，通常一个负责信息结构、一个负责视觉系统或系列一致性；
- `style_id` 与 `visual_layout`：风格和信息关系分开，显式风格优先于自动风格；
- `selection_reason` 与 `source_packs`：可以解释为什么选择 Guizang/Baoyu 方法，但不把来源 URL 当作图片素材；
- `upstream_method_pass`：记录是否按 Guizang Social Card Skill → baoyu-skills 尝试调用/读取；不可用时记录本地映射降级，不得虚报调用；
- `runtime.provider=doubao.image_gen`、`runtime.generation_mode` 为 `seedream_5_pro_direct_full_card` 或 `seedream_5_pro_banner_plus_native_card`、`runtime.generation_model_label=Seedream 5.0 Pro`、`runtime.post_processing=none`。

能力包只改变所选视觉路径的设计约束。它不能改变 `analysis.source_text`、图片文字白名单、Card 原生事实、按钮目标、真实 `img_key` 或 CardKit 导入状态；不得启动 HTML/CSS/SVG/Playwright 转图链或其他模型。

渲染前必须校验：

1. `analysis.source_sha256 == sha256(analysis.source_text)`；
2. `visual_contract.text_in_image` 必须与当前模式匹配：竖版为 `seedream_5_pro_direct_selected_text_and_layout`，横幅为 `seedream_5_pro_banner_selected_text_and_layout`；
3. `functional_text` 非空且所有文字字段来自源锁定 spec；
4. stage/facts、quote 和 buttons 的数量不超过固定预算；
5. 每个文字块都能在自己的 zone 内完整排版；`illustration.relationship_map.contains_text=true` 且每个 `text_nodes[].fitted=true`。
6. `reference_card_banner` 的输出尺寸建议为 1200×720；`timeline_infographic_inside_illustration` 的输出尺寸建议为 1200×1600；横幅模式使用约 3:1 的宽高比，竖版信息图使用约 2:3。quote 是否进入图片由源文案和白名单决定；CTA 永远不进入图片。

任一条件失败就停止并重新调用 Seedream 5.0 Pro；不能改用 HTML、截图或未登记的后处理。`hero-generation.json` 必须记录完整图片、提示词、来源 hash 和人工视觉复核状态，不能生成或依赖叠字 sidecar。
