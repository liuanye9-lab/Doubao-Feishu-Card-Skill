# 图片视觉模板目录（研究版）

这份目录把 GitHub、小红书 Skill 和腾讯 SkillHub 中值得借鉴的视觉方法，转译成适合飞书 Card 2.0 的 Seedream 5.0 Pro 整图模板。它是“风格”目录，不是“事实”目录：

- 风格决定 Seedream 5.0 Pro 整图的材质、色彩、线条、插画语言和氛围。
- 版式决定内容是时间线、流程、对比、分层还是关系图；Seedream 5.0 Pro 接收图片文字白名单和完整源文案参考，长文不自动进入图片。
- 日期、阶段、动作和数字默认由同一次 Seedream 5.0 Pro 直接生成；文字密集结构化信息图可按 `render_strategy=html_infographic_to_png` 由自包含 HTML 精确排版后导出。图片不得生成按钮视觉，人工逐字复核并确认没有伪交互，错误只能按所选路径重新生成/导出。

机器可读索引见 [`presets/image-style-index.json`](../../presets/image-style-index.json)，能力包自动选择见 [`presets/visual-skill-packs.json`](../../presets/visual-skill-packs.json)。首次生成按内容关系自动选择风格；用户显式指定风格时覆盖自动结果，只有用户要求比较/切换时才暂停确认。这里的模板只改变视觉语言；原生模型路径不接入本地渲染器，HTML fallback 使用独立的自包含信息图排版契约。

## 先给结论

对于当前“AI 先锋大赛开营”这类培训通知，建议优先从下面三种中选：

1. **蓝图流程**：最适合时间线、培训节点、提交和决赛路径。信息最清楚，建议作为第一候选。
2. **极简编辑**：最稳妥、最像企业产品卡片。适合公告、培训概览和少量事实。
3. **手绘教育**：更亲和，适合社群开营和新人学习，但需要严控装饰数量。

如果想强化象上汇的东方气质，可以选择 **墨色研究札记**；如果想更像小红书的 AI/科技内容，可以选择 **小红书科技杂志**。等距、黏土、概念字体等风格先作为探索项，不用于长通知默认方案。

## 候选模板总览

| 模板 ID | 中文名 | 参考来源 | 信息文字适配 | 推荐场景 | 当前建议 |
| --- | --- | --- | --- | --- | --- |
| `blueprint-timeline` | 蓝图流程 | AntV Infographic、Baoyu technical-schematic | 很高 | 时间线、培训、SOP、阶段路径 | 首选 |
| `clean-editorial` | 极简编辑 | Zhuang WebUI Clean Modern、infographic-builder Clean Minimalist、Aura Minimal | 很高 | 公告、摘要、产品能力、数据摘要 | 首选 |
| `ink-research-note` | 墨色研究札记 | Zhuang Ink Minimal、Baoyu Aged Academia / Ink、知识卡 | 很高 | 案例、复盘、规则、CEO 寄语 | 首选 |
| `enterprise-tech-blue` | 企业科技蓝图 | SkillHub 社区企业科技模板、AntV、腾讯 WorkRally 的生图工作流 | 高 | 企业培训、AI 能力、方案流程 | 可选 |
| `handdrawn-edu` | 手绘教育 | Baoyu hand-drawn-edu、WorkBuddy XHS 小黑配图、Aura Notion | 中高 | 开营、学习路径、社群教程 | 可选 |
| `xhs-editorial-magazine` | 小红书科技杂志 | XHS Visual Director、XHS Cover Skill、WorkBuddy XHS | 中 | AI 观点、工具方法、单一结论 | 短文案可用 |
| `morandi-journal` | 莫兰迪手记 | Baoyu morandi-journal、XHS material illustration | 中高 | 团队故事、作品复盘、经验沉淀 | 可选 |
| `corporate-memphis` | 企业孟菲斯 | Baoyu corporate-memphis、AntV 主题系统 | 中 | 企业培训、角色协作、能力分组 | 控制颜色 |
| `isometric-map` | 等距全景地图 | Zhuang Isometric、Baoyu isometric-map、SkillHub T9 | 较低 | 系统全景、架构、组织地图 | 探索项 |
| `claymation-story` | 黏土故事场景 | infographic-builder Claymation、Baoyu claymation | 低 | 轻量六步以内流程、活动氛围 | 探索项 |

## 模板说明

### `blueprint-timeline` · 蓝图流程

视觉关键词：深蓝或米白蓝图底、细网格、工程线、圆角节点、琥珀色日期、单条连接轨道。

适合把“培训 → 提交 → 辅导 → 路演”这类内容变成一条能顺着读的路径。图片内的日期和动作使用深色面板配浅色文字，背景插画只负责表达学习、协作或推进关系。

推荐组合：`sequence-timeline-rounded-rect-node`、`sequence-roadmap-vertical-simple`、`linear-progression`。

不可做的事：不要铺满工程标注，不要把每个节点做成不同图标，不要让网格线穿过文字。

### `clean-editorial` · 极简编辑

视觉关键词：白或浅灰底、严格对齐、单一强调色、细边框、轻阴影、现代无衬线、大留白。

这是最适合飞书企业卡片的“安全模板”。它能把图片做成一个清晰的视觉索引，而不是一张海报；标题、日期和动作可以在固定关系区内保持较大字号。

推荐组合：`list-row-horizontal-icon-arrow`、`sequence-timeline-simple`、`bento-grid`。

不可做的事：不能只留下一个大图标和大量空白；至少要有一组与原生 Card 同源的功能标签。

### `ink-research-note` · 墨色研究札记

视觉关键词：暖白纸张、墨黑线稿、轻网纹、细边框、研究札记式留白、少量朱红或金色。

适合案例复盘和 CEO 寄语。日期、阶段、来源和结论在纸面上有稳定的阅读顺序，能保留东方感，又不会把文字交给模型自由发挥。

推荐组合：`linear-progression`、`dense-modules`、`list-grid-badge-card`。

不可做的事：不能用低对比灰色代替正文，不能用水墨飞溅遮住日期，也不能用按钮形状或按钮索引制造伪交互。

### `enterprise-tech-blue` · 企业科技蓝图

视觉关键词：白底浅蓝分区、深蓝标题、SaaS 圆角模块、少量蓝紫强调、轻量 3D 对象、企业方案感。

这个方向来自 SkillHub 中的企业科技信息图模板，但本仓库只借鉴信息层级和配色逻辑，不使用腾讯云 Logo、企鹅、WorkBuddy 标识或其品牌文案。它适合 AI 能力、协同流程和团队培训。

推荐组合：`bento-grid`、`dense-modules`、`list-row-horizontal-icon-arrow`。

不可做的事：不能把图片做成完整 PPT 截图，也不能把第三方品牌角色当成自己的视觉资产。

### `handdrawn-edu` · 手绘教育

视觉关键词：暖奶油纸张、少量马卡龙色块、轻微手绘抖动、线性箭头、简单图标、教学板书节奏。

它适合“大家一起学习、边做边分享”的社群气质。Seedream 5.0 Pro 可以把学习或协作隐喻与日期、动作、阶段卡融合在同一张图中，但装饰不能压住文字。

推荐组合：`sequence-timeline-simple`、`hub-spoke`、`list-grid-badge-card`。

不可做的事：不为每个节点添加贴纸、星星和 Emoji；手绘感不能成为文字不清楚的理由。

### `xhs-editorial-magazine` · 小红书科技杂志

视觉关键词：黑白灰、一个亮色信号、杂志式大标题、强对比裁切、一个主视觉锚点、短标签。

小红书 Skill 的价值不在于把飞书卡片做成 3:4 封面，而在于“每张图只承担一个传播任务”“先做视觉确认图”“把配色、构图、字体层级和材质拆开说明”。因此这里只借鉴科技杂志的气质和单焦点原则，把图片文字白名单交给同一次 Seedream 5.0 Pro；Card 原生层只承载精简摘要/图表/真实行动，完整事实留在 `source.txt`。

推荐组合：`linear-progression`、`structural-breakdown`、`dense-modules`，但只适合短标签。

不可做的事：不能让标题钩子替代活动事实，不能把长通知压缩成不可读的社媒封面。

### `morandi-journal` · 莫兰迪手记

视觉关键词：米灰、低饱和橄榄绿、暖陶色数字、纸张、手帐线条、圆角模块、柔和连接箭头。

适合团队故事、作品复盘和经验沉淀。对于飞书卡片，应删减胶带、贴纸、角落涂鸦，只保留一到两个能表达关系的手绘符号。

推荐组合：`bento-grid`、`linear-progression`、`dense-modules`。

不可做的事：不能让手帐装饰取代日期、动作或原生按钮的语义；图片本身不得绘制按钮，文字颜色必须保持手机端可读。

### `corporate-memphis` · 企业孟菲斯

视觉关键词：扁平几何人物或物件、受控的紫橙青黄、无厚描边、轻松企业培训气质。

适合解释“谁负责什么”“几个能力如何协作”。信息密度较高时让 Seedream 5.0 Pro 使用少量清晰模块承载短标签，不能用人物动作替代事实。

推荐组合：`hub-spoke`、`bento-grid`、`compare-binary-horizontal`。

不可做的事：不能让四种以上高饱和颜色同时抢焦点，也不能用人物动作暗示原文没有写出的结果。

### `isometric-map` · 等距全景地图

视觉关键词：30 度等距视角、平台高低表达层级、空间化路径、小型系统场景。

适合把复杂系统先画成“地图”，但不适合精确承载长中文。使用时应压缩为少量源事实并要求 Seedream 5.0 Pro 放入高对比信息卡；若仍不可读就换成极简编辑或蓝图流程。

推荐组合：`isometric-map`、`structural-breakdown`、`hierarchy-structure`。

### `claymation-story` · 黏土故事场景

视觉关键词：3D 黏土对象、柔和阴影、连续动作、实体隐喻、轻量场景叙事。

适合活动暖场或不超过六步的简单流程。它能让“报名—学习—提交—展示”更有亲和力，但图片文字区域必须非常干净，不能把事实埋在角色和道具里。

推荐组合：`linear-progression`、`comic-strip`、`winding-roadmap`。

## 当前文案的推荐组合

| 组合 | 适合理由 | 需要保留的图片文字 | 风险 |
| --- | --- | --- | --- |
| `blueprint-timeline` + 时间线 | 让三个阶段按顺序读，最适合培训通知 | 三组日期 + 每组一到两条动作 | 网格过多会显得像工程图 |
| `clean-editorial` + 时间线 | 稳定、企业化，适合直接发群 | 三组日期 + 关键行动 | 可能过于平，需要一个主题性插画 |
| `handdrawn-edu` + 时间线 | 更符合开营、社群、一起学习的氛围 | 日期 + 培训/提交/辅导标签 | 装饰会抢掉文字 |
| `ink-research-note` + 时间线/寄语 | 东方感和 CEO 理念更统一 | 日期 + 一句寄语 | 纸面低对比时手机难读 |
| `xhs-editorial-magazine` + 单焦点路径 | AI/科技话题更有传播感 | 只留最关键的日期和一句行动 | 不适合长通知 |

本轮默认采用参考图式的 Seedream 5.0 Pro 整图：保持“标题层级 + 主题视觉 + 模块化信息区 + 阶段路径 + 显著寄语”的节奏，图片文字白名单中的标题、关系标签、时间线和短寄语在同一张 `hero.png` 中生成；文字密集结构化内容可由同一白名单驱动 HTML→PNG。完整源文案与真实行动仍在 Card 原生层。改变风格不能改变事实来源、图片文字复核和 Card 原生按钮。

## 从小红书 Skill 借鉴的工作流

### 1. 用户要求比较时，再给三套方向

小红书视觉导演类 Skill 把“内容判断、风格判断、视觉母版、样例图、批量产出”拆开；这适合飞书卡片的低门槛调用。正常首次生成不要求用户选择，路由器会按内容关系自动选一个方向。只有用户明确要求比较模板时，才输出三组候选：

- 稳妥：`clean-editorial`
- 清晰：`blueprint-timeline`
- 亲和：`handdrawn-edu`

用户选定后再生成最终图片，避免一开始就在多个风格间来回漂移；用户明确指定风格时也可以直接覆盖自动风格。

### 2. 把“封面、解释图、材质图”分流

WorkBuddy XHS Skills 把视觉请求分成完成封面、16:9 单认知锚点手绘图、材质/图表解释图。转译到飞书卡片后：

- 活动通知、培训日程 → `blueprint-timeline` 或 `clean-editorial`。
- 一个机制/案例/流程 → `ink-research-note`、`handdrawn-edu` 或 `enterprise-tech-blue`。
- 仅有一句金句/CEO 理念 → `ink-research-note` 或 `clean-editorial`，不生成复杂时间线。

### 3. 参考图只提取视觉特征

用户给参考图时，记录“借鉴配色、构图、字体层级、材质、焦点、禁止项”，不复制第三方成图、角色、完整提示词或品牌标识。图片内的准确文字由当前选定的 Seedream 5.0 Pro 或 HTML 路径生成/排版，生成后人工逐字复核。

## 从腾讯 SkillHub / WorkRally 借鉴的工作流

腾讯 SkillHub 更适合作为 Skill 发现与安装入口，不是单一视觉标准。当前公开检索到的高相关条目包括：

- `Baoyu Infographic`：21 种布局、22 种视觉风格，强调先分析内容再组合 layout × style。
- `baoyu-xhs-images`（旧称 `baoyu-image-cards`）：强调系列图的一致性；本仓库使用当前名称，旧称只保留为兼容别名。
- `Aura Image Gen`：跨平台信息图卡片，提供多种 preset，包括 minimal、notion、ink-wash、bold、cute、retro。
- 社区 `infographic-generator`：12 个模板，其中企业科技信息图、知识卡片、等距全景最值得做中性化借鉴。

腾讯 `workrally` 更偏生图/生视频工具链：生图前动态获取模型，支持画幅、参考图和轮询，并把素材上传与生成结果分开。转译到本 Skill 后，结论是：当前 豆包工作 直接使用内置 Seedream 5.0 Pro 生成完整图，模型的 observable provenance 必须记录；不能再增加另一个模型或本地文字层。

安装任何 Skill 前都要检查来源、脚本、权限、是否需要 API Key；本轮没有把外部 Skill 直接安装进仓库，也没有复制第三方素材。

## 统一质量门

无论选择哪种模板，以下规则不变：

- 选定路径的最终 PNG 必须直接存在可读的文字、数字、日期、时间轴和 quote（如进入白名单）；不得存在按钮、CTA 胶囊、假链接或其他伪交互，不是只有背景插画。
- 图片内文字以 `visual_contract.functional_text` 和完整 `analysis.source_text` 为事实清单，并通过人工逐字复核；不使用 sidecar 叠字。
- 时间线至少有日期和动作的关系表达；图标不能替代文字。
- 风格变化不能改变原生 Card 的事实、按钮、quote、source hash 或 CardKit 导入边界。
- 文字放不下或 Seedream 5.0 Pro 生成错误时直接失败并重新生成；不通过缩小到不可读、裁切、转成 Emoji、叠字或让模型改写事实来“修复”。
