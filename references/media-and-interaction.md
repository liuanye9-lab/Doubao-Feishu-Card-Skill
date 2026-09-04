# 媒体与交互契约

这份契约把案例图里的“图片、信息块、按钮”拆成可以复用的 Card 2.0 结构。它回答三个问题：图片要传递什么、卡片原生文字要兜底什么、点击之后由谁更新状态。

每个媒体资产还必须标记来源：`real_image` 表示用户提供的真实截图、看板、Logo、照片或案例证据；`ai_generated` 表示 豆包工作 内置 Seedream 5.0 Pro 一次性生成的当前模式最终图片（默认竖版信息图，也可为横幅首图；只包含信息分工选中的图片文字）。AI 图片需要 `hero-generation.json` 溯源，真实图片需要媒体 manifest；两者都不能只凭“看起来像生成过”进入远程 Card。

三个默认图片角色是：`cover`（主题/状态）、`information_carrier`（路径/节点/分区/短文字）和 `text_companion`（与原生事实块配对）。历史 `cta_companion` 仅保留为兼容元数据，不能让图片绘制按钮或 CTA。一个图片可以有多个角色，但每个角色都必须在报告中有信息任务。

## 从案例图提取的卡片语法

案例图不是“长文 + 一张海报”，而是一个可扫描的内容节奏：

```text
主题首图 / 状态
    ↓
一句价值说明
    ↓
事实、指标或时间轴
    ↓
图文并排的案例/课程模块
    ↓
一个主 CTA + 少量次级动作
    ↓
寄语、来源或补充说明
```

| 案例视觉 | 信息任务 | Card 2.0 表达 | 图片模式 |
| --- | --- | --- | --- |
| 大幅渐变首图 | 让人一眼知道主题与当前状态 | `hero` + `lead`/`status_tag` | `static` 或 `gif` 首帧 |
| 指标横排 | 快速比较 2–4 个事实 | `facts` / `metrics` | 静态事实图或原生文本 |
| 三段项目里程碑 | 表达顺序、阶段和交接 | `timeline` | 功能性时间轴图片 |
| 两列课程/能力卡 | 对比两个系列或两种路径 | `column_set` + 原生文字 | 静态 `img_combination` 或两张配对图 |
| 文案左、截图右 | 说明“做了什么、看到什么结果” | `section` + `img` | 文字与截图相邻，不让截图孤立 |
| 底部按钮 | 让读者完成一个动作 | Card 2.0 直接 `button` | 按钮负责交互，图片不绘制按钮或 CTA |

默认移动端顺序是“首图 → 事实 → 时间轴/案例模块 → CTA”。如果原文是截止提醒或日程，时间轴可前置；如果原文是复盘或案例，指标和“问题—做法—结果”优先。不要把所有模块都强行塞进一张图片。

## 四种媒体模式

### 1. `static`：一张信息型首图

只输入文案时默认使用此模式。豆包工作 的 `image_gen` 让 Seedream 5.0 Pro 通过 Seedream 5.0 Pro 一次生成有文字、有信息结构、无水印的选定图片资产；默认是竖版完整信息图，也可显式选择约 3:1 横幅首图。只有 `information_allocation.image.include` 中的标题、日期、阶段动作、指标和短 quote 直接进入 `hero.png`，按钮、CTA 标签、URL 和其他真实交互一律留在 Card 原生层。Card 原生层只保留摘要、3–5 个关键点、来源图表和真实行动，完整事实保留在 `source.txt`。

### 2. `gif`：Seedance 2.5 直出动图

当流程、时间线、状态变化或前后对比确实更适合动态表达时，自动路由到 Seedance 2.5。动图可以承担“阶段推进、状态流转、操作节奏”等解释任务，但不承担唯一事实。Seedance 必须直接生成循环 `hero.gif`，禁止先生成视频再本地转码。生成后先登记 provenance，再运行媒体检查：

```bash
python3 scripts/register_motion_generation.py \
  --asset outputs/my-card/hero.gif \
  --prompt outputs/my-card/my-card.motion-prompt.md
```

```bash
python3 scripts/media_assets.py \
  --input outputs/my-card/hero.gif \
  --role hero \
  --output outputs/my-card/hero.media-manifest.json
```

通过条件：文件是可读的真实 GIF、至少两帧、资产哈希与提示词哈希匹配、关键文字不只存在于动画中。CardKit 支持上传后的 GIF `img_key` 直接作为图片节点，因此不强制另做静态伴随图；客户端不播放时仍应依靠 GIF 首帧和原生 Card 摘要理解核心信息。本 Skill 不截帧、不补帧、不叠字，也不对动图做后期改写。

### 3. `gallery`：静态多图组合

多张图片用于对比、系列作品或两个课程系列时，用 Card 2.0 的 `img_combination`，不是伪装成轮播。每张图片都要有真实的 `img_key`，每张图的 `alt` 要说明它传递的事实。

```json
{
  "type": "image_combination",
  "id": "case_gallery",
  "combination_mode": "double",
  "images": [
    {"img_key": "<real_img_key_1>", "alt": "改造前：反馈分散"},
    {"img_key": "<real_img_key_2>", "alt": "改造后：统一看板"}
  ]
}
```

尖括号只是模板占位符，不能直接发送。生成前要通过 `scripts/feishu_cli.py upload-image` 获取真实 `img_key`，然后编辑同源 `.spec.json` 再编译。

### 4. `switcher`：按钮驱动的图片切换

Card 2.0 没有一个可以在客户端自动切换图片的通用 carousel 组件。本 Skill 的 `media_switcher` 是一个明确的 application Bot 契约：

1. 首张图片作为静态初始状态；
2. 每个标签按钮带 `card.action.trigger` callback；
3. 后端校验 `media_id` 与 `target_id`，再用 `card.update` 替换当前 `img_key`；
4. 无 callback、无权限或客户端不支持更新时，卡片仍显示首张图片和原生文字。

示例（只放已上传的真实 key）：

```json
{
  "type": "media_switcher",
  "id": "course_visuals",
  "active_index": 0,
  "callback_action": "switch_media",
  "items": [
    {"id": "overview", "label": "课程总览", "img_key": "<real_img_key_1>", "alt": "课程总览"},
    {"id": "path", "label": "学习路径", "img_key": "<real_img_key_2>", "alt": "学习路径"}
  ]
}
```

该模式只能通过 application Bot 发送；自定义 Bot/Webhook 不支持 callback，校验器会拒绝。回调值只传业务状态标识，不传用户身份、token、secret 或 webhook；点击者身份由飞书事件上下文和后端权限校验获得。

## Seedream 5.0 Pro 图片生成与功能性文字

当前默认不把图片生成拆成“关系底图 + 文字层”。`image_gen` 的 Seedream 5.0 Pro 一次完成关系和氛围（路径、节点、屏幕、仪表盘、课程对象、光路），同时直接生成 `information_allocation.image.include` 白名单中的中文、数字、日期、quote 和卡片排版；严禁生成按钮、CTA 标签、URL 或伪交互。`visual_contract.functional_text` 作为提示词事实清单和人工复核清单，不是本地叠字输入；长文和完整事实留在 `source.txt`。

当用户要求“时间线图片”“课程日历图片”或“图片里直接有信息”时，Seedream 5.0 Pro 必须在同一张完整图片里生成分工清单选中的日期、阶段和动作；不能用一张漂亮但无事实的氛围图代替。Card 原生文字继续作为精简、可访问和可编辑的摘要层，完整事实由 `source.txt` 保底。

如果需要多帧动效，调用豆包工作内置 Seedance 2.5 直接生成 GIF，或使用用户提供的真实 GIF。不要让动画帧承载唯一的逐字事实；Skill 不从静态图制作动效、不从 GIF 导出替代帧，也不把视频本地转为 GIF。动画、图集和切换状态都要有只读 manifest，记录路径、哈希、尺寸和格式；Seedance 资产还必须有独立的 `hero-motion-generation.json`。

## 交互状态

```text
initial
  ├─ 点击静态 URL → open_url
  └─ 点击切换按钮 → pending → 校验 media_id/权限
                           ├─ confirmed → card.update 当前图片
                           └─ error → 保留当前图片 + 错误提示
```

卡片的 `config.update_multi` 应保持为 `true`。callback 不是“按钮看起来可点击”就算完成：必须有事件订阅、application Bot、后端 handler、权限判断和幂等策略。没有这些条件时，只生成静态图集或首图 fallback，并在报告里标记 `requires_application_bot`。

## 统一入口内的相关能力

| 能力 | 在本体系里的职责 |
| --- | --- |
| Seedream 5.0 Pro | 宿主内置静态图能力；由主 Skill 约束为一次整图生成和人工视觉复核 |
| Seedance 2.5 | 宿主内置动效能力；按来源关系自动路由并直接输出循环 GIF |
| 主 Skill Card 2.0 模块 | 组织原生结构、组件、按钮、callback、表单和更新状态契约 |
| 主 Skill 内置媒体模块 | Seedream 整图与 Seedance GIF 提示词、自动路由、溯源和人工视觉 QA |
| `skill-creator` | 保持 Skill 入口、示例、测试和 quick validation 可复用 |
| 主 Skill 内置 CardKit 模块 | 已登录 CardKit 网页“我的卡片”导入与编辑页双证据 |

外部项目只借鉴方法，不复制第三方品牌或资产：小红书 Visual Director 的视觉分流与样例确认、WorkBuddy 的封面/解释图分流、XHS Cover 的 preset 管理、AntV 的声明式信息图和腾讯 WorkRally 的 provider 可替换思路，均已转译为本仓库自己的 source-locked 规则。
