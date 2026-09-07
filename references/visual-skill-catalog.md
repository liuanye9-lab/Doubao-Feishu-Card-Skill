# 内置视觉能力包与自动路由

更新时间：2026-09-01。

本目录把两个上游项目中适合飞书卡片的“判断方法”内置为本地能力包。每次需要图片时，默认先尝试调用或读取可用的 Guizang Social Card Skill 与 baoyu-skills，再把结果映射为本地路由规则；整张图片统一由 豆包工作 内置 Seedream 5.0 Pro 一次完成，文字密集结构化内容回到原生 Card 高亮块。上游不可调用时透明降级到本地映射；没有可观察调用证据时不声称上游已经执行。禁止 HTML/CSS/SVG/Canvas/Pillow 转图、叠字、拼接和第二个图片模型。

机器可读规则在 [`presets/visual-skill-packs.json`](../presets/visual-skill-packs.json)，普通提示词在 [`presets/prompt-presets.json`](../presets/prompt-presets.json)。每次路由都会写入 `<name>.prompt-routing.json` 的 `visual_skill_routing`，方便检查“为什么选这个能力包和风格”。

## 两个核心来源

| 来源 | 本 Skill 吸收的能力 | 在本地的落点 | 不直接搬入的部分 |
| --- | --- | --- | --- |
| [Guizang Social Card Skill](https://github.com/op7418/guizang-social-card-skill) | expression first、one-glance 信息、证据与文案分工、Editorial/Swiss 视觉系统、参考图候选和密度复核 | 默认方法链的第一步；可用时调用/读取，并落到 `guizang-social-editorial`、`guizang-social-swiss` | HTML/CSS 排版器、Playwright 渲染链、第三方品牌素材和完整实现 |
| [baoyu-infographic](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-infographic/SKILL.md) | 内容类型先行、layout × style × palette 分离、时间线/对比/分层/关系图选择、画幅和文字预算 | 默认方法链的第二步；可用时调用/读取，并落到 `baoyu-infographic` + `selection_rules` | Baoyu 的其他 provider、脚本运行时和可替换模型链 |
| [baoyu-xhs-images](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-xhs-images/SKILL.md) | 系列图一致性、一个主视觉锚点、统一色板、每张图独立信息任务 | `baoyu-xhs-images` | 小红书平台尺寸和封面钩子不直接套到长通知 |
| [baoyu-article-illustrator](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-article-illustrator/SKILL.md) | infographic / scene / flowchart / comparison / framework 的图片角色判断 | `baoyu-article-illustrator` | 纯场景图不能替代来源事实和关系信息 |

默认方法顺序是 Guizang Social Card Skill → baoyu-skills → 豆包工作 Seedream 5.0 Pro；路由器不再分流到本地转图器。上游不可调用时，`upstream_method_pass` 必须记录 `local_mirrored_method_mapping` 降级；实际 Seedream 5.0 Pro provider 不跟随 [baoyu-image-gen](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-image-gen/SKILL.md) 的多 provider 选择，原因是模型路径仍是 豆包工作 Seedream 5.0 Pro-only。

## 自动选择规则

用户只需要输入文案。主 Skill 先识别内容关系，再选择能力包、风格和视觉版式；用户明确说出的风格优先于自动结果。

| 文案信号 | 自动能力包 | 默认 Seedream 5.0 Pro 风格 | 图片信息结构 |
| --- | --- | --- | --- |
| 时间线、阶段、培训、提交、路演 | `baoyu-infographic` + `guizang-social-swiss` | `blueprint-timeline` | `linear-progression`，一条主路径、日期、阶段动作 |
| 案例、指标、看板、前后结果 | `baoyu-infographic` + `guizang-social-swiss` | `clean-editorial` | `dashboard` 或 `structural-breakdown` |
| CEO、理念、寄语、金句 | `guizang-social-editorial` + `baoyu-article-illustrator` | `ink-research-note` | `quote-anchor-with-path`，短 quote 与轻路径 |
| 多图、系列作品、图集 | `baoyu-xhs-images` + `guizang-social-editorial` | `xhs-editorial-magazine` | 统一母版的静态图集，每张图一个任务 |
| 课程、学习、开营但没有完整时间线 | `baoyu-infographic` + `baoyu-article-illustrator` | `handdrawn-edu` | 教学模块、目标和参与动作 |
| 没有强结构信号 | `guizang-social-editorial` + `baoyu-infographic` | `clean-editorial` | 一个主题信息锚点；Card 留精简摘要，完整事实留在 `source.txt` |

能力包最多选两个：一个负责信息结构，一个负责视觉系统或系列一致性。风格和版式始终是两个字段，不能因为选择了“小红书科技杂志”就把时间线改成封面海报。

## 当前文案的自动结果

对于“AI 先锋大赛开营”这类文案，路由器应记录：

```json
{
  "selected_packs": ["baoyu-infographic", "guizang-social-swiss"],
  "style_id": "blueprint-timeline",
  "visual_layout": "linear-progression",
  "runtime": "doubao.image_gen / seedream_5_pro_direct_full_card"
}
```

图片只承载三段日期/阶段动作和必要的短 quote；问候语、群内说明、提交规则和完整寄语保留在 `source.txt`，Card 原生文本只保留最关键摘要。若有真实按钮 URL，按钮使用 Card 原生 `behaviors`；图片中禁止 CTA、按钮标签、按钮形控件和假链接。

## 选择与换风格

- 首次生成：自动选择，不要求用户记住能力包名称。
- 用户说“使用蓝图/极简/墨色/小红书风格”：显式风格覆盖自动风格，但保留原内容结构。
- 用户说“给我三个风格看看”：返回三组“能力包 + 风格 + 版式”候选；确认后才重新生成和上传。
- 用户明确要求“不要图片/无图”：不调用 Seedream 5.0 Pro，仍可产出原生 Card；否则默认生成至少一张信息视觉。
- Seedream 5.0 Pro 生成失败或文字不清：从完整源文案和同一白名单重新生成整图；文字密集内容回到原生 Card 高亮块。不得缩小到不可读、叠字、OCR 修补、本地转图或换成其他模型。

## 版权与品牌边界

上游项目只提供公开的方法参考。本地能力包不复制上游图片、人物、Logo、水印、完整提示词或外部可执行脚本；用户提供的品牌资产仍需单独声明来源和使用范围。能力包中的 `source` URL 只用于审计与追溯，不会被写进最终图片。
