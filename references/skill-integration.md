# 历史能力的统一合并映射

| 原能力 | v2 统一位置 | 处理原则 |
| --- | --- | --- |
| Studio 内容模式/摘要抽取 | `scripts/summary_extraction.py`、`plan.json`、`spec.analysis` | 源锁定分组，不自动虚构事实 |
| Studio CardKit 文件外壳 | `scripts/cardkit_format.py` | raw 与 wrapper 并行，幂等转换 |
| Importer 的 `.card`/`.json` 转换 | `scripts/convert_to_card.py` | 结构修复可报告、校验失败不谎报 |
| Studio 结构校验规则 | `scripts/validate_card.py` | 合并折叠箭头、分栏权重、表格对齐规则 |
| 原有 Seedream 5.0 Pro 图片层 | 主 Skill 的内置图片模块 + `references/image-*.md` | 一次性生成完整图片，禁止后处理 |
| 原有 Bot/CLI 发送层 | `scripts/feishu_cli.py` | raw 或 wrapper 均可读；写入仍 dry-run/确认 |
| 原有 Card 2.0 编译器 | `scripts/generate_card.py` | 保持按钮、回调、媒体与源编辑能力 |

## Guizang / Baoyu 视觉能力包

| 上游方法 | 本地能力包 | 自动触发 | 运行时边界 |
| --- | --- | --- | --- |
| [Guizang Social Card Skill](https://github.com/op7418/guizang-social-card-skill) Editorial | `guizang-social-editorial` | 主视觉、案例、CEO 寄语、短 quote | 默认先尝试调用/读取；不可用时用本地映射；不执行 HTML/CSS/Playwright |
| Guizang Swiss | `guizang-social-swiss` | 时间线、培训、指标、案例 | 只吸收网格、单路径、规则线和密度门；不复制品牌与素材 |
| [baoyu-infographic](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-infographic/SKILL.md) | `baoyu-infographic` | 时间线、对比、分层、看板、流程 | 默认在 Guizang 方法后尝试调用/读取；不可用时用本地映射；不调用 Baoyu provider 作为位图渲染器 |
| [baoyu-xhs-images](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-xhs-images/SKILL.md) | `baoyu-xhs-images` | 多图、系列作品、静态图集 | 只吸收系列一致性和主视觉锚点；旧 `baoyu-image-cards` 仅作别名 |
| [baoyu-article-illustrator](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-article-illustrator/SKILL.md) | `baoyu-article-illustrator` | 机制图、流程图、对比、框架、受控场景 | 只吸收图片角色判断，不能让场景图替代功能文字 |

默认方法链是 Guizang Social Card Skill → baoyu-skills → 豆包工作 Seedream 5.0 Pro；调用/读取结果与不可用降级都写入 `upstream_method_pass`。上游能力包不会改变飞书 Card 2.0 的事实、按钮和 CardKit 投递边界。实际位图 provider 固定为 `doubao.image_gen` / `seedream-class`，所有图片文字和排版在同一次 Seedream 5.0 Pro 生成中完成，`post_processing` 必须是 `none`。

没有把 Studio 的 393 个源包条目原样复制进来；只抽取公开安全的 Schema 快照、组件路由、内容模板和校验入口，过滤内网 `$id`、私有实现、第三方素材与令牌。需要运行时的能力被转译为小型脚本、参考规则和可测试契约，避免两个入口继续产生冲突。

## 内网 Card Studio 能力的公开兼容契约

本节是通过 Feishu CLI、Byte CLI 内网检索和 AgentBuddy 能力目录核验后留下的可公开行为契约。只沉淀方法、输入输出和失败边界，不包含私有消息 ID、内网链接、令牌或实现源码。

| 内网能力模式 | 本仓库的融合位置 | 兼容策略 |
| --- | --- | --- |
| `create-lark-card`：自然语言生成、结构校验、本地预览、可选编辑器 | `scripts/doubao_pipeline.py`、`scripts/generate_card.py`、`scripts/validate_card.py` | 保留“AI 先生成 0→80%，CardKit 做 80→100% 微调”的分工；源事实仍落在可编辑 `spec.json` |
| “材料 + 用途 + 发送对象”即可开始 | `scripts/card_studio_contract.py` 的 `input_brief` | 用途和对象只作为布局/交付上下文；不会把“群”自动解析成远程目标，群发送仍须显式 `chat_id` 和确认 |
| UX → RD → QA 三节点协作 | `generation_workflow` + `quality_gates` | 生成 bundle 记录 UX、Card 2.0 编译和 QA 的状态、证据与修复路径；图片对比度和 PNG 是否像按钮仍标为人工复核 |
| `.card` / `.json` 导出后拖入编辑器 | `scripts/cardkit_format.py` | 裸 `<name>.card` 保持 Card 2.0 API/Bot 方言；网页导入另生成同源 `<name>.cardkit.card` / `.cardkit.json` 外壳，并做 parity 校验 |
| 在线模板配置、mock/发给自己、发送记录 | `references/delivery.md`、`scripts/feishu_cli.py` 的 dry-run/record 记录 | 公开包记录可观测的预览、导入和回读证据；不虚构模板注册、撤回或私有服务 API |
| CardKit Web-backed 模板直导 | `delivery_workflow.cardkit_import`、`scripts/feishu_cli.py push-cardkit`、主 Skill 的 CardKit 交付模块 | 默认用 Byte CLI 对裸 `.card` 走 `template import` 并回读 `template_id + get/list`；未认证或失败时回到已登录浏览器导入 wrapper，仍须名称 + 编辑页双证据 |
| `lark-card-studio-full.zip` 的 Schema/组件注册表 | `references/card-schema.json`、`references/card-studio-schema.md`、`scripts/validate_card_schema.ts`、`presets/card-studio-registry.json` | 只保留公开安全的结构参考和可执行校验；过滤内网 `$id`、私有实现、素材与令牌；Schema 通过仍不能替代 Python 安全门禁 |
| 三类常用视觉主题/场景路由 | `presets/visual-skill-packs.json`、`presets/image-style-index.json`、`references/prompt-presets.md` | 复用内容模式、风格和版式的分离模型；Guizang/Baoyu 只作为方法路由，不作为位图渲染器 |

### 两个容易混淆的边界

1. 内网工具包的 `.card` 可能是 `{name, dsl, variables}` 外壳，而本仓库把裸 Card 2.0 JSON 保留为 API/Bot 文件；网页导入外壳使用 `.cardkit.card`。转换器可读取两种方言，但不会覆盖原始文件。
2. 内网旧规则可能允许“暂时没有行为的 button”作为视觉占位；本仓库沿用更严格的安全规则：原生按钮必须有真实 URL 或已实现的 application-bot callback/form，图片内绝不出现按钮、CTA 胶囊、链接样控件或伪交互。

### Byte CLI 的可观测导入路径

生成报告会给出以下 Skill 适配器 dry-run 命令：

```bash
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/<name>/<name>.card \
  --name "<card_name>" \
  --dry-run
```

它内部调用 CardKit Web-backed 模板操作，不是 `create-cardkit` 的 API Card Entity。真实导入属于远程写入，只能在一次合并确认后执行，并且必须用模板响应及 `template get/list` 回读；若返回 `FEISHU_CARDKIT_WEB_AUTH_REQUIRED`，不得把 ByteCloud 登录误当成 Feishu Web session，应使用浏览器导入兜底。运行时消息返回的 `card_id` 也不能当作编辑器的 `template_id`。
