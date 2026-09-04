# 开源项目调研与本地取舍

本 Skill 参考了几类成熟的 GitHub 项目，但没有把它们的外部依赖直接引入主流程：

- [vercel/satori](https://github.com/vercel/satori)：用 JSX/CSS 做确定性布局，显式传入字体，输出固定尺寸 SVG。这里仅借鉴“布局和字体需要被明确描述”的思想；当前 豆包工作 版本不调用 Satori、Pillow 或 SVG 后端，完整图片由 Seedream 5.0 Pro 一次生成。
- [ryanbaumann/infographic-agent](https://github.com/ryanbaumann/infographic-agent)：把流程拆成结构化 Prepare、schema/eval gate、Render、Review、Refine，并保存精确文本字符串和来源信息。这里落地为 `visual_contract`、source hash、sidecar 和 overflow gate。
- [jessepike/diagram-forge](https://github.com/jessepike/diagram-forge)：用模板、颜色系统、明确布局规则和可替换 image provider 生成不同类型的图。这里借鉴模板、颜色和关系图命名，并把这些约束写入 Seedream 5.0 Pro prompt；不再增加本地文字层。
- [remotion-dev/template-still](https://github.com/remotion-dev/template-still)：让设计预览和无头渲染使用同一套组件，并支持根据参数生成 still image。这里借鉴“预览和交付使用同一资产”的原则；当前预览直接显示 Seedream 5.0 Pro 生成的 `hero.png`。
- [bensblueprints/og-image-studio-mvp](https://github.com/bensblueprints/og-image-studio-mvp)：把模板编辑、变量、自动换行/缩放、固定尺寸和渲染 API 组合起来。这里借鉴“模板变量/文字 fit/输出尺寸是契约”，但保留本仓库的 source-locked 原则，不开放自由拖拽来破坏 Card 信息顺序。

## 本轮 GitHub / 小红书 / SkillHub 调研

本轮调研重点不是把外部项目整包复制进来，而是提取三类可迁移机制：内容关系先于风格、样例确认先于批量生成、完整源文案和人工复核优先于装饰。

### 小红书 Skill

- [ziguishian/xhs-visual-director-skill](https://github.com/ziguishian/xhs-visual-director-skill)：把视觉工作拆成内容判断、风格判断、三套方案、统一视觉母版、1 张确认图和最终批量图；还明确要求参考图拆成配色、构图、字体层级、材质和禁止项。这里转译为“飞书图片先提供三套候选，不确认不切换默认风格”。
- [jackbauerxu/workbuddy-xhs-skills](https://github.com/jackbauerxu/workbuddy-xhs-skills)：把视觉需求分流为 3:4 完成封面、16:9 单认知锚点手绘图、材质/图表解释图，并在生成前检查标题、证据和事实边界。这里转译为“活动时间线、机制图、金句卡分别走不同图片任务”，不把封面审美直接套到飞书卡片。
- [Vivixiao980/xhs-cover-skill](https://github.com/Vivixiao980/xhs-cover-skill)：提供可命名的 18 种封面预设和命令行风格参数。这里借鉴“风格 ID + 预览目录 + 一句话选择”，但只迁移 `professional-clean`、`dark-glow`、`multi-layer-layout` 等气质，不复制其封面版式或人物素材。
- [iamzifei/xiaohongshu-images-skill](https://github.com/iamzifei/xiaohongshu-images-skill)：使用 HTML/CSS 处理文字层，再按 3:4 截图并检查文字边界。这里仅借鉴“生成前拆解内容、生成后检查文字边界”；按用户要求，飞书版本不调用 HTML/CSS 截图或后处理。

### 信息图与确定性渲染

- [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills)：`baoyu-infographic` 和 `baoyu-xhs-images` 将 layout、style、palette 分成独立维度；SkillHub 当前条目也提供了技术蓝图、手绘教育、莫兰迪手记、企业孟菲斯等可检索风格。这里借鉴“风格 × 版式”的组合模型。
- [antvis/Infographic](https://github.com/antvis/Infographic) 与 [chart-visualization-skills](https://github.com/antvis/chart-visualization-skills)：提供声明式信息图语法、丰富的时间线/流程/关系模板，以及手绘、渐变、纹理主题。这里只借鉴结构命名和主题分离，并把它们翻译为 Seedream 5.0 Pro 的信息架构描述；最终 PNG 由 Seedream 5.0 Pro 直接生成。
- [ryanbaumann/infographic-agent](https://github.com/ryanbaumann/infographic-agent)：将 Prepare、schema/eval、Render、Review、Refine 拆成可检查阶段。这里已经落地为 source hash、功能文字计划、sidecar 和 overflow gate。

### 腾讯 SkillHub / WorkRally

- [腾讯 SkillHub](https://skillhub.tencent.com/) 是 Skill 的发现、安装和版本入口，不是单一设计规范。通过公开检索，本轮记录了 `baoyu-infographic`、`baoyu-image-cards`、`aura-image-gen` 和社区 `infographic-generator` 等相关条目；条目的风格、脚本和权限仍需逐个审查，不能因为出现在市场就自动信任。
- [Tencent/workrally](https://github.com/Tencent/workrally)：更偏 AIGC 生图/生视频工具链，强调生成前动态获取模型、画幅/参考图配置、任务提交与结果查询分离。这里借鉴生成任务与结果溯源分离；当前 豆包工作 只使用内置 Seedream 5.0 Pro，不叠加其他模型或本地文字渲染器。
- SkillHub 社区的“腾讯云科技信息图”模板适合作为企业蓝图的参考来源，但本项目中性化为 `enterprise-tech-blue`，明确禁止第三方 Logo、角色和品牌文案进入底图。

这些外部来源只贡献方法和公开风格名称；本仓库没有复制第三方图片、角色、完整提示词、未授权素材或外部 Skill 的可执行脚本。

这些外部项目贡献的是内容拆解、模板分流、视觉一致性和评估门。本 Skill 当前执行链是“结构化内容 → 模板选择 → 图片文字白名单 + 完整源文案参考 → Seedream 5.0 Pro 一次生成最终信息图 → 人工逐字复核 → provenance/上传门禁”，不使用无字关系底图、确定性叠字或第二个图片模型。

## Guizang 与 Baoyu 的本地能力包化

本轮把两个上游来源单独登记为能力包，避免“参考过”变成无法解释的黑盒：

- [Guizang Social Card Skill](https://github.com/op7418/guizang-social-card-skill) 的核心启发是先回答“一眼要看懂什么”，再区分证据图、短文案和 Card 原生事实；Editorial 更适合主视觉/quote，Swiss 更适合网格、数字、时间线和单条主路径。
- [baoyu-infographic](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-infographic/SKILL.md) 的核心启发是先选信息关系，再独立选择 layout、style 和 palette；时间序列不与 bento/对比/分层关系混用。
- [baoyu-xhs-images](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-xhs-images/SKILL.md) 的核心启发是系列图先确定一个视觉锚点、统一色板和每张图的信息任务；它不是把长通知变成多张装饰封面。
- [baoyu-article-illustrator](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-article-illustrator/SKILL.md) 的核心启发是先决定图片角色是 infographic、scene、flowchart、comparison 还是 framework，再谈审美。

这些做法已经落在 [`presets/visual-skill-packs.json`](../../presets/visual-skill-packs.json) 和 [`references/visual-skill-catalog.md`](../../references/visual-skill-catalog.md)：内容路由器默认按 Guizang Social Card Skill → baoyu-skills 尝试调用/读取，最多选两个能力包，显式风格覆盖自动风格，且每次留下来源、理由、版式、上游方法通行记录和运行时信息。上游不可用时使用本地映射并记录降级；真正生成位图只有 豆包工作 内置 `image_gen` 的 Seedream 5.0 Pro 一次生成，禁止复制上游 HTML/CSS/SVG/Playwright 文字渲染和 Baoyu 的 alternate provider。
