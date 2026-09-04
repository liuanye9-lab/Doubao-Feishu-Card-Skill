# 预制提示词与自动触发

主 Skill 已内置一套路由器。用户不需要学习提示词，也不需要填写 JSON；只要把卡片文案粘进来，Skill 会先识别内容关系，再自动选择最合适的本地“视觉能力包 + 内容版式 + 媒体模式 + 风格”提示词。

机器可读注册表是 [`presets/prompt-presets.json`](../presets/prompt-presets.json) 和 [`presets/visual-skill-packs.json`](../presets/visual-skill-packs.json)，路由实现是 [`scripts/prompt_router.py`](../scripts/prompt_router.py)。它们只负责选择生成策略，不会改变原文事实。日期、数字、姓名、URL、按钮和寄语仍以用户原文为唯一来源。

## 自动触发规则

| 文案中出现的信号 | 自动命中的预制策略 | 默认图片任务 |
| --- | --- | --- |
| 时间线、时间轴、阶段、节点、里程碑、日程、时间表、流程 | `timeline` 时间线流程 | 同一次 Seedream 5.0 Pro 生成中直接绘制日期、阶段和动作文字，以及它们之间的连接关系；不再生成无字底图 |
| 培训、课程、开营、学习、课堂、讲师、作业、workshop | `training` 培训课程 | 同一次 Seedream 5.0 Pro 生成中组织“学什么、何时学、怎么参与”的完整信息区，Card 原生层同时保留可编辑事实 |
| 案例、背景、问题、做法、结果、成果、复盘、前后对比 | `case-study` 案例复盘 | 用“背景/问题 → 做法 → 结果”的关系表达价值，不编造指标 |
| 数据、指标、看板、增长、转化、同比、环比、KPI、统计 | `metrics-dashboard` 数据看板 | 用真实指标分组或输入—分析—结果关系表达信息，不生成假数字 |
| 截图、界面、功能演示、看板截图、UI | `screenshot-explainer` 界面解释图 | 让截图成为证据，与短解释相邻，不重绘准确界面文字 |
| CEO、赵总、理念、寄语、金句、愿景 | `quote-anchor` 理念寄语 | 为原文寄语保留显著、安静的 quote 区，不自动补励志话 |
| 多图、组图、图集、系列作品、作品集、图片对比 | `gallery` 静态图集 | 统一裁切和网格，每张图承担一个明确的信息角色 |
| 动图、GIF、动画、动态效果 | `gif-motion` GIF 动效 | 先准备可读的静态首帧，动效只承担节奏，不承载唯一事实 |
| 轮播、图片切换、上一张、下一张、图集切换 | `image-switcher` 图片切换 | 生成 application Bot callback + `card.update` 契约；没有应用 Bot 时降级为首图或静态图集 |
| 蓝图、工程线、科技蓝、流程图风格 | `blueprint-style` 蓝图流程风格 | 改变 Seedream 5.0 Pro 整图的材质、色板和路径语言，不改变信息版式或事实 |
| 极简、企业感、产品卡片、干净、编辑感 | `clean-editorial-style` 极简编辑风格 | 保持严格对齐、单一强调色和充足但有任务的留白 |
| 手绘、亲和、社群感、教育风、板书 | `handdrawn-education-style` 手绘教育风格 | 适合开营、社群和新人培训，控制装饰数量 |
| 墨色、水墨、东方、研究札记、纸张 | `ink-editorial-style` 墨色研究札记 | 适合案例复盘和理念寄语，维持移动端高对比 |
| 小红书、科技杂志、杂志感、传播感 | `magazine-style` 科技杂志风格 | 只采用短标签和单一认知焦点，不把长通知压成封面 |

## 组合和优先级

路由器会自动组合策略，但有预算，避免一个卡片同时变成时间线、海报、图集和动效墙：

1. 内容版式最多 2 个，例如 `timeline + training`。
2. 理念、CEO 或金句可以额外保留 1 个 `quote-anchor` 语义锚点，不会被内容版式预算挤掉。
3. 媒体模式最多 1 个，例如 `switcher` 优先于 `gif`。
4. 视觉能力包最多 2 个，通常一个负责信息结构、一个负责视觉系统或系列一致性。
5. 视觉风格最多 1 个，例如 `blueprint-style`；首次生成由内容规则自动选择，显式风格要求覆盖自动结果。
6. 用户在文案里明确说出的媒体要求优先于普通关键词；“需要图片切换”会强制 `switcher`。
7. 用户明确否定的词不触发，例如“不要轮播，也不需要动图”不会命中 `gallery`、`gif-motion` 或 `image-switcher`。
8. 没有命中内容策略时，自动使用 `general-information` 和 `clean-editorial`，不会因为缺少关键词而停住。

可理解为：先尝试调用或读取 Guizang Social Card Skill，再尝试 baoyu-skills，决定“信息是什么关系”，再决定“用什么能力包和版式承载”，最后把它们一次性组合成 Seedream 5.0 Pro 整图提示词。上游不可调用时使用本地映射并记录透明降级；这里没有“底图 + 叠字”第二阶段，且不会把上游当作位图渲染器。风格不会覆盖时间线、指标或案例的事实。

## 用户怎么说最省事

最短调用只需要一句：

```text
把下面文案做成飞书卡片，按 Skill 自动选择信息型图片和版式；不改事实，不重复 emoji，生成可以直接导入 CardKit 的卡片包。
```

然后直接粘贴原文即可。需要特殊能力时只补一句自然语言：

```text
把下面的课程通知做成飞书卡片，默认先调用或读取 Guizang Social Card Skill 与 baoyu-skills，再用 Seedream 5.0 Pro 一次生成整张能读懂培训时间线的功能性图片；信息文字和排版直接放进图片，按钮只放原生 Card 且必须有真实 URL 或已实现回调。
```

```text
把下面的案例做成飞书卡片，图片切换按按钮查看不同案例，并保留静态首图兜底。
```

```text
把下面的活动文案做成飞书卡片，使用极简企业感；不要动图，不要轮播。
```

用户不需要写“请使用 timeline prompt”或记住 preset ID。普通的“生成得漂亮一点”也不会覆盖功能性版式，系统会自动把内容关系、能力包、风格、图片文字白名单和完整源文案参考组合进同一次 Seedream 5.0 Pro 生成；只要形成真正的时间序列，图片就直接承载被选中的日期、阶段和动作文字。

## 每次生成会留下什么

在 `outputs/<name>/` 中会生成：

- `<name>.prompt-routing.json`：本次命中的 profile、Guizang/Baoyu 能力包、触发词、组合顺序、负向约束和自动动作。
- `<name>.image-prompt.md`：已经组合好的 豆包工作 `image_gen` Seedream 5.0 Pro 整图提示词，含逐项 `Image text whitelist` 和仅供核对的完整源文案；用户无需手工拼接。
- `<name>.spec.json` 中的 `prompt_routing`：与卡片源文件绑定的同一份路由结果。
- `<name>.report.json` 中的 `prompt_routing`：方便检查最终卡片为什么选择某个图片任务。

如果需要改策略，优先修改 `.spec.json` 或在文案中补充一句明确要求，再重新编译；不要直接改最终 PNG。若要扩展预制词，修改注册表并为新规则补一个测试。

## 能力边界

预制提示词降低的是“选择和表达成本”，不是绕过飞书能力边界。`gallery` 需要真实图片和 `img_key`；`gif-motion` 需要静态首帧；`image-switcher` 需要 application Bot、回调服务和 `card.update`。CardKit 默认用 Byte CLI 对裸 `.card` 直导并回读模板证据；CLI 不可用时才用已登录浏览器导入 `.cardkit.card`，不能用提示词、HTML 预览或 `lark-cli` 的 Card Entity 接口伪装成模板导入。
