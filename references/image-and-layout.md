# 图片与版式契约

主 Skill 负责选择图片策略、抽取事实，并把 `information_allocation.image.include` 与完整源文案参考交给同一 Skill 的视觉模块。默认输出是 Seedream 5.0 Pro 一次性生成的当前模式最终 PNG（默认竖版信息图，也支持横幅首图）。文字密集内容由原生 Card 高亮块、层级标题和短句承载，不经过 HTML 转图或浏览器截图。

豆包工作 版把图片当成“信息关系 + 直接可读文字”图层，而不是把卡片做成一张不可编辑海报。对于时间线，最终 PNG 必须在视觉关系区内显示日期、阶段和动作；图片帮助回答“这些内容之间是什么关系、先扫到哪个节点”，卡片原生文字再回答“精确是什么、何时发生、下一步做什么”。真实按钮、URL 和回调永远不进入图片。

默认图片方法链是：先尝试调用或读取可用的 Guizang Social Card Skill，再尝试 baoyu-skills，吸收内容分型、信息关系、视觉系统和质量门，最后执行 豆包工作 Seedream 5.0 Pro 整图生成。上游 Skill 未在当前运行环境暴露时，使用本地等价映射并在路由产物中记录降级；没有可观察的调用证据时不得声称上游已经执行。

## 图片来源与四种角色

每张图片都要在 spec 中声明 `image_source`：

- `real_image`：用户提供的 Logo、照片、截图、看板或案例证据。保留原始像素、尺寸、来源、哈希和 `alt`；截图中的准确 UI 文字不交给 AI 重绘。
- `ai_generated`：豆包工作 内置 `image_gen` 的 Seedream 5.0 Pro 一次性生成的当前模式最终图片资产。必须登记 `hero-generation.json`，生成家族记录为 `seedream-class`；平台不暴露具体模型 ID 时使用 `platform-managed`，不虚构模型名称。

图片还可以声明以下角色，角色必须对应实际的信息任务：

| 角色 | 可验收的问题 |
| --- | --- |
| `cover` | 读者一眼能知道主题/状态是什么吗？ |
| `information_carrier` | 图片内的路径、节点、分区或短文字直接传递了什么信息？ |
| `text_companion` | 它是否紧邻并解释对应的原生 facts/timeline/section？ |
| `cta_companion` | 历史兼容角色；仅可记录“图片与原生行动相邻”的元数据，不得触发 CTA 或按钮绘制。 |

默认 AI hero 只使用 `cover`、`information_carrier`、`text_companion` 三种角色。历史 `cta_companion` 不得触发 CTA 或按钮绘制。不能只写“好看、科技感、氛围感”作为任务；真实图片通常承担证据和文字协同，不能被当作无来源装饰图。

提示词不要求用户手工编写：主流程会先用 [`scripts/prompt_router.py`](../scripts/prompt_router.py) 从文案中选择预制的内容版式、媒体模式和视觉风格，再由 `information_allocation` 划出图片白名单、原生 Card 事实和按钮目标，最后写入 `<name>.image-prompt.md`。先判断信息关系，再让 Seedream 5.0 Pro 一次生成整张信息图；不要因为用户说“漂亮一点”就把功能性时间线替换成纯装饰海报。

## 内置模型生图提示词模板（默认路径）

调用内置 `image_gen` 时，把管线写出的 `<name>.image-prompt.md` 原样作为基础，让 Seedream 5.0 Pro 直接生成当前模式的完整最终 PNG。不要使用任何本地绘制、文字叠加、图片拼接、合成、后处理或第二个图片模型：

```text
Use case: infographic-diagram
Asset type: final Feishu Card 2.0 bitmap, generated as one complete image
Generation model: Seedream 5.0 Pro visual generation through 豆包工作 built-in image_gen; record the actual observable tool/model provenance in hero-generation.json
Primary request: one coherent information-bearing card that makes the topic, sequence, key facts, quote and next action understandable at a glance
Scene/backdrop: calm enterprise editorial space with a light background and a clear visual metaphor
Subject: the user's theme, expressed through paths, nodes, objects, modules or scene relationships; every visible object must reinforce a source concept
Style/medium: polished enterprise infographic with Chinese typography, crisp rounded modules and restrained semantic icons
Composition/framing: portrait mobile-safe complete card; clear title, readable timeline/fact modules and quote area when present; reserve action space only in the native Card, never draw an image-side action control; no giant empty panel
Typography: Seedream 5.0 Pro must render every character in the image-text whitelist sharply and legibly; preserve the exact source wording, dates, numbers, punctuation and order for those selected items
Image text whitelist (verbatim): BEGIN IMAGE TEXT WHITELIST / only source-backed title, relationship labels, metrics and short quote; no button label, CTA or clickable-looking control / END IMAGE TEXT WHITELIST
Native Card source (reference only): BEGIN SOURCE COPY / the complete source copy from the pipeline / END SOURCE COPY; keep long prose, rules, caveats and exact full details in the editable Card
One-pass rule: all permitted visible text, layout, timeline, information graphics and quote treatment come directly from this Seedream 5.0 Pro generation; no button-like artwork is allowed
Native pairing: Card 2.0 separately preserves editable facts and real button behaviors; only native buttons may expose URLs, callbacks or forms
Constraints: no base-image stage, no post-generation text layer, no HTML, CSS, SVG, Pillow, deterministic overlay, compositing, or second image model
Avoid: blank white rectangles, unreadable microtype, repeated emoji, random icons, fake brand marks, watermarks, contradictory dates, missing lines, pseudo-text, gibberish, generic mood art, and decorative imagery that carries no information
```

## 视觉决策

如果用户没有指定风格，首次生成由 [`presets/visual-skill-packs.json`](../presets/visual-skill-packs.json) 按内容关系自动选择能力包、风格和版式。用户提出“换一种风格”或要求查看模板时，先读取本 Skill 的[视觉模板目录](./image-style-catalog.md)，把能力包、风格和版式分开给出三套候选组合。风格候选影响 Seedream 5.0 Pro 整图的材质、配色和插画语言，不改变源事实、图片文字、Card 原生按钮、CardKit 导入流程或内容关系；用户确认后才切换。

- `case-showcase` / `event-recap`：优先用关系图、场景化构图或案例对象表达“问题—做法—结果”。
- `activity-timeline` / `training-notice`：优先用路径、节点、蓝图和阶段分区表达结构；日期和动作必须同时出现在最终图片的时间轴节点卡和原生文字。
- `task-reminder` / `submission-call`：用少量红/金信号表达注意力；不要把“截止”字样画进图片。
- `result-announcement` / `finals-stage`：可用黑金舞台或聚焦光路，但结果、名单、时间仍在 Card 文本。

每张自动卡都要写入 `visual_contract`：`not_decorative=true`、图片的 `job`、来源片段、与原生事实块的 `pairing`，以及供 Seedream 5.0 Pro 使用的 `functional_text` 源清单。生成完整图片后，必须人工逐字检查它是否表现这些关系；发现错字、漏字或布局问题只能重新调用 Seedream 5.0 Pro，不能加入未声明的后处理器。

## 移动端验收

1. 先看首图缩到手机宽度是否仍有一个清楚的视觉焦点。
2. 中心主体不贴边，左右裁切后仍能表达主题。
3. 完整 PNG 内直接有可读的白名单标题、日期、数字、时间轴和必要关系文字；没有按钮、CTA 胶囊、箭头动作控件、假链接、伪 Logo、乱码或模型自行添加的事实。未进入白名单的长文不应被压进图片。
4. 图片加载失败时，Card 原生文字仍能回答“这是什么、最重要的是什么、下一步做什么”。

## 案例参考转译：从“长图”变成“信息节奏”

本仓库收到的案例图共同使用了几种稳定结构：顶部标题和状态标签、大幅主题图、指标/事实横排、阶段或课程路径、文字与界面截图配对、底部单一主动作。它们可以迁移为 Card 2.0 的原生结构，但不应直接把整张长图当成一个不可编辑图片。

推荐的转译关系：

- 课程/开营通知：主题首图 → 两到三个课程/目标模块 → 原生时间轴 → 一个预约/提交按钮。
- 企业案例/迁移复盘：关系首图 → 客户背景 → 指标 → 项目里程碑 → “问题—做法—结果”三列短卡 → 成果/寄语。
- 课程小结/产品能力：Seedream 5.0 Pro 生成带标题与能力标签的场景整图 → 一句价值说明 → 每个能力一组“功能文字 + UI 截图” → 原生查看路径按钮。
- 多个系列需要选择：静态图集用 `img_combination`；用户需要点击查看不同图才用 `media_switcher`，并且仅通过 application Bot callback 更新 `img_key`。

图片的任务必须写成一句可验收的话，例如“让读者先看懂三个阶段的顺序”“让读者看到看板从输入到结果的关系”“让读者区分两条课程路径”。如果只能写成“更好看、更有科技感”，就说明图片仍是装饰，应回到原生排版或补充信息型图形。

动图只改变节奏，不改变事实。使用 GIF 前先运行 `scripts/media_assets.py` 只读检查首帧信息，并确保日期、指标和阶段动作在静态首帧或原生 Card 中可读；CTA 只允许出现在原生 Card。图片切换同样必须保留初始静态状态；Card 2.0 没有通用客户端 carousel，不能承诺只靠 `.card` JSON 在客户端自动轮播。

十项优化点、参考图模板和图片角色的完整维护清单见 [`references/optimization-roadmap.md`](./optimization-roadmap.md)。
