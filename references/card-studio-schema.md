# Card Studio Schema 与组件路由

本文件把 `lark-card-studio-full.zip` 的 Schema 层压缩成统一 Skill 的可读路由。完整机器可读快照在 [`card-schema.json`](./card-schema.json)，可执行结构校验器在 [`../scripts/validate_card_schema.ts`](../scripts/validate_card_schema.ts)；远程发送前仍必须先通过 [`../scripts/validate_card.py`](../scripts/validate_card.py) 的公开安全门禁。

## 根对象

默认输出是裸 Card 2.0 对象：

```json
{
  "schema": "2.0",
  "config": { "update_multi": true, "summary": { "tag": "plain_text", "content": "来源锁定的卡片摘要" } },
  "header": { "title": { "tag": "plain_text", "content": "卡片标题" } },
  "body": { "direction": "vertical", "elements": [] }
}
```

网页 CardKit 编辑器导入另使用同源 `{ "name", "dsl", "variables" }` wrapper。不要把 webhook/OpenAPI 外层、运行时 Card Entity 或 wrapper 混进默认 Card JSON。

## 组件路由

| 类别 | 组件 tag | 典型用途 |
| --- | --- | --- |
| 内容 | `div`, `markdown`, `lark_md`, `plain_text` | 事实、段落、轻量 Markdown、兜底文字 |
| 内容 | `img`, `img_combination` | 已上传图片、静态图集；必须是真实 `img_key` |
| 内容 | `person`, `person_list` | 真实成员展示；没有有效 ID 就用文字 |
| 内容 | `chart`, `table` | 真实趋势/对比/占比/排行；不能用 ASCII 伪造 |
| 内容 | `audio`, `video`, `avatar`, `fallback_text` | 媒体或兼容/降级场景，先确认客户端支持 |
| 内容 | `hr`, `collapse_divider` | 结构分隔，避免用空容器凑版面 |
| 层级 | `highlight`（Skill DSL） | 重点、结论、价值、风险等少量显著信息；编译为 `column_set` 内的 `column.background_style`，不是新的 Card tag |
| 交互 | `button`, `overflow`, `checker` | 真实跳转、回调、表单动作、状态切换 |
| 交互 | `input`, `select_static`, `multi_select_static` | 文本或固定选项输入 |
| 交互 | `select_person`, `multi_select_person` | 真实成员选择 |
| 交互 | `picker_date`, `picker_time`, `picker_datetime`, `date_picker` | 日期/时间选择器（按目标客户端确认兼容） |
| 交互 | `select_img` | 从真实图片资源中选择 |
| 布局 | `column_set`, `column` | 指标、对比、等宽按钮和响应式分栏 |
| 布局 | `form` | 交互字段与提交/重置按钮的组合 |
| 布局 | `interactive_container` | 有真实点击行为的整块入口，或非交互视觉 surface |
| 布局 | `collapsible_panel` | 长日志、补充说明、次要明细的渐进披露 |

`note` 和 `action` 是废弃结构：备注用 `div` / `markdown`，操作用原生 `button` / `overflow`。

## 稳定嵌套子集

- `body.elements` 可放根级内容、交互和容器。
- `column_set.columns[].elements` 放内容和支持的交互子组件；表格只放 `body.elements` 顶层，列内表格改用左对齐 Markdown 表格。
- `form.elements` 只收集表单字段和提交/重置动作；每个字段有唯一 `name`，提交要有真实 application Bot 处理。
- `interactive_container.elements` 不放 `form` 或原生 `table`；它只有在整块点击行为真实时才挂 `behaviors`。
- `collapsible_panel.header` 必须带统一箭头：`standard_icon` + `down_outlined` + `grey`、`icon_position: "right"`、`icon_expanded_angle: -180`。
- 内容分栏默认 `weighted` + `weight: 1`；窄屏阅读顺序和文本长度不确定时使用 `flex_mode: "stretch"`。
- `highlight` 只允许作为高层布局意图；编译结果必须是可编辑的 `column_set` → `column`，色面使用受限的 `grey-50`、`grey-100`、`blue-50`、`green-50`、`yellow-50` 或 `red-50`，不得注入 HTML/CSS。
- 每张卡默认最多 1–3 个高亮块；`markdown`/`div`/`section` 只保留摘要与关键点，长时间线和完整事实留在 `source.txt` 或真实来源链接，避免用色面或折叠区代替信息结构。
- 自定义图标的 `img` 必须直接放在有边框、非默认背景色的图标底座内；大幅封面图不套图标底座。

## 行为路由

| behavior | 能力 | 发送边界 |
| --- | --- | --- |
| `open_url` | 打开真实 URL，可按端提供 URL | 原生 Card 与 custom-bot 都可按实际能力使用 |
| `callback` | 将业务动作回传处理服务 | 只在 application Bot + 已部署处理服务时使用 |
| `event` | 事件与即时 toast/卡片响应 | 需要 application Bot 与事件处理；不能只写一个空事件 |
| `client_message` | 下发到已注册客户端通道 | 需要真实通道；未注册时不生成 |

`behaviors` 是动作数组，但本 Skill 的稳定发送子集对一个按钮只保留一个真实行为。回传值只携带业务状态，不携带用户身份、token、secret、webhook 或权限凭据。

## Schema 校验顺序

1. `validate_card_schema.ts`：源包提供的 Card 2.0 结构、字段、枚举和额外属性校验。
2. `validate_card.py`：公开安全规则，包括真实按钮、占位符、表面能力、图片 key、折叠箭头和移动端布局风险。
3. `references/content.md` 与 `references/beauty-review.md`：事实、摘要、图片 CTA 分离和人工视觉验收。

Schema 校验通过不等于可以发送：它不会替你验证 URL 是否属于真实业务、callback 是否有后端，也无法从 JSON 判断 PNG 是否误画了按钮。
