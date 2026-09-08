# Badcase 复盘：文字信息没有真正转成信息承载图

日期：2026-09-08
范围：清华附中「AI先锋·智教焕新」教师报名邀约，豆包 Seedream / Seedance 路径

## 1. 现象

用户要求“文字信息转化为图片形式的卡片”，并明确图片必须承载可解释的信息，而不是抽象概念图。反馈截图显示，活动定位、活动介绍、教师权益、六大赛道和活动节奏仍以连续原生文字与时间线块展开；图片没有替长文承担信息结构，首图也没有把主题、身份和核心关系说清楚。

截图是本次反馈的渲染证据，不是新的活动事实。活动事实仍以生成包的 `source.txt` 和用户确认的原始文档为唯一来源。

此前还出现过两类并行风险：模型自由生成的视觉曾偏向抽象科技氛围，且容易把学校身份误作其他高校；在改用来源锁定的真实信息图后，图片可以正确承载清华附中身份，但旧报告的 `card_image_contract` 仍残留 `ai_generated`、Seedream 和旧 `media_task` 元数据。

## 2. 根因

| 根因 | 证据 | 影响 |
| --- | --- | --- |
| 视觉门禁只检查 visual-spec 存在 | 旧 `visual_strategy` 没有 `information_purpose`、`visual_job`、来源节点门槛 | 抽象图也可能通过结构门禁 |
| 通知场景自动切横幅 | 横幅压缩为标题和极少短标签 | 长文的活动介绍、权益、赛道等信息被回原生 Card，首图失去信息价值 |
| 只抽取日期/严格流程节点 | 普通 Markdown 标题和段落未进入 visual-spec | “活动介绍 / 教师可以获得什么 / 六大赛道”等分组没有图像表达 |
| 品牌身份没有成为契约 | prompt 只有一般性的“不要伪造品牌” | 模型可能绘制相似校徽、错误高校身份或臆造 Logo |
| 真实图片回写后报告未完全刷新 | 外层 `image_source` 已变为 `real_image`，嵌套 `card_image_contract` 仍保留旧 AI 字段 | 运行时已修复，交付报告却无法准确说明媒体来源 |

## 3. 本次修复

- `visual_spec.py` 新增 `information_purpose`、`visual_job`、`source_spans`、`content_nodes`、`must_show`、`must_not_show`、`brand_asset_policy`、`mobile_readability` 和 `recommended_panels`。
- 长文且有多个分组、阶段或“文字转图片 / 信息可视化”意图时，`preferred_render` 为 `information_infographic`，自动选择竖版信息图；显式选择横幅时仍尊重用户选择。
- 普通章节标题、首个来源主张和列表要点进入信息图片候选，但完整原文仍保留在原生 Card 与 `source.txt`，不会把整张 Card 截图成不可编辑海报。
- 新增必过的 `image_information_contract`：没有信息目的、视觉任务或来源节点时，图片型卡片不能进入后续交付。
- Seedream / Seedance 提示词明确要求“信息承载，不是抽象概念图”；提供校徽、Logo 或品牌资产时只使用原始资产，不重绘、不替换、不猜测。
- `finalize_card.py` 在 `real_image` 路径清除旧的 AI 工具、模型、generation manifest 和 Seedream / Seedance 状态，并统一写入 `source_locked_information_graphic`；豆包版真实图片 manifest 使用 `doubao-feishu-media/2` 门禁。
- Codex 与豆包共用同一信息契约，但保留各自的 Image2 / Seedream 运行时、provenance schema 和 CardKit 报告方言。

## 4. 可验收标准

1. 每张图片都能回答“这张图具体要帮助读者看懂什么”，并在 visual-spec 中留下来源节点。
2. 首图承载主题、身份和一条核心关系；时间线、权益、赛道、安全边界等信息按需要进入后续信息面板或原生可编辑模块，不用微型字硬塞一张图。
3. 原始校徽、Logo、校名资产优先；没有原始资产时不生成相似标志，不把清华附中替换成清华大学或其他学校。
4. 图片不得出现按钮、CTA、二维码、URL 或伪交互；真实报名动作只在原生 Card 按钮中承载。
5. 以 360px 展示宽度复核标题、日期、单位、限定词和节点；不清晰就拆图或回原生文本，不拉伸、不叠字修补。
6. 本地生成、真实媒体 manifest、上传 `img_key`、重新编译、CardKit 导入和 `template_id` / get / list 回读分别留下证据；`needs_image`、dry-run、预览和未发布草稿不能冒充正式完成。

## 5. 回归用例

- 清华附中长通知必须得到 `preferred_render=information_infographic` 和非空 `source_spans`。
- Codex 选择 `image2_direct_full_card`；豆包选择 `seedream_5_pro_direct_full_card`。
- 缺少 `information_purpose` 或来源节点时，`image_information_contract` 必须阻断结构交付。
- 提供品牌上下文时，`brand_asset_policy.exact_asset_required=true`，提示词必须包含原始资产优先和禁止重绘。
- `real_image` 回写后，嵌套 `card_image_contract` 不得再出现 AI generation tool/model/manifest。
