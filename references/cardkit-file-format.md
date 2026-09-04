# CardKit 文件格式与双轨输出

v2 把“可发送的 Card JSON”和“可导入 CardKit 网页编辑器的文件”明确分开。

| 文件 | 顶层结构 | 用途 |
| --- | --- | --- |
| `<name>.card` | 裸 Card 2.0：`schema/config/body/header` | Byte CLI Web-backed CardKit 模板直导、`lark-cli` API/Bot 预览/发送 |
| `<name>.cardkit.card` | `{ "name", "dsl", "variables" }` | CardKit 网页“导入卡片”入口 |
| `<name>.cardkit.json` | 与上行相同 | 只接受 `.json` 的传输/上传环境 |
| `<name>.cardkit-import.json` | 本地导入清单 | 记录 CardKit 直导命令、网页兜底 wrapper、名称和验证方式 |

`dsl` 的值就是裸 Card 2.0 对象。CardKit wrapper 不是 API Card Entity；
`create-cardkit` 创建的 `card_id` 也不会自动出现在网页的“我的卡片”。
默认进入 CardKit 模板资源先走 Byte CLI Web-backed `template import`，并回读
`template_id`、`template get` 和 `template list`。需要可见编辑验收或 CLI session 不可用时，
再在已登录浏览器中走“导入卡片 → 新建卡片 → 开始导入”，并同时验收列表名称和可视化编辑页。

## 自动转换

```bash
python3 scripts/convert_to_card.py outputs/demo/demo.card \
  --outdir outputs/demo --name demo
```

转换器支持裸 JSON、已有 wrapper、`dsl` JSON 字符串和数组包裹输入；只做可解释的
结构修复：`schema` 统一为字符串 `"2.0"`、补齐 `config.update_multi=true`、删除空
`card_link`，不改写正文、图片 key、URL 或按钮行为。校验失败仍会输出文件，但命令会
以非零退出并显示原因。

兼容说明：独立转换器沿用 importer Skill 的历史文件名，输出的 `<name>.card` 和
`<name>_card.json` 都是 CardKit wrapper；主流水线则明确输出 `<name>.card`（裸 API/Bot
卡片）与 `<name>.cardkit.card`（网页导入 wrapper）。通过主流水线生成时，网页导入始终
以 `.cardkit.card` 为准。

CardKit 文件大小门槛按 300 KB 检查。原始卡片路径用于 API/Bot/Byte CLI，wrapper 路径用于网页导入，
不要把两者混用，也不要把本地 HTML 预览当作网页导入证据。

## 编辑器兼容性

CardKit 编辑器会在保存时规范化 DSL，并可能移除 `config.style.color` 中的自定义色板定义。
因此正文 `text_color` 不得引用 `brand_accent`、`brand_gold`、`brand_ink` 等自定义别名，必须使用
CardKit 原生色名，例如 `grey`、`blue`、`green`、`yellow`、`red` 或 `turquoise`。否则首次导入
可能正常，但再次在编辑器中修改时会出现 `invalid color`。兼容转换器会把历史 `brand_*` 引用清洗
为原生色名；修改源文件后仍须重新生成 raw `.card` 和 `.cardkit.card`。
