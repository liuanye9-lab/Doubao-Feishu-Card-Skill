# CLI、CardKit 与发送边界

## 状态

- `generated`：本地已生成 `.card`、`.spec.json` 和报告。
- `seedream_output_ready`：当前静态视觉路径的 `hero.png` 已由 Seedream 5.0 Pro 直出；需模型 provenance 并通过人工视觉复核门。
- `seedance_output_ready`：Seedance 2.5 已直接生成真实、至少两帧的 `hero.gif`，并通过 motion provenance 和人工视觉复核门。
- `visual_output_ready`：本次自动选择的 Seedream PNG 或 Seedance GIF 已完成对应门禁。
- `image_ready`：当前模式的 `hero.png` 或 `hero.gif` 已通过 `lark-cli im images create` 上传，回读到真实 `image_key`，且重新编译后的 `.card` 已包含 `<img>` 节点。只有本地有媒体或 provenance 都不算 `image_ready`。
- `cardkit_entity_created`：通过 CardKit OpenAPI 创建了 Card Entity，回读到 `card_id`。
- `sent`：通过 `lark-cli im +messages-send` 向明确目标发送成功，并回读到消息 ID。
- `preview_sent`：通过应用 Bot 向当前登录用户本人发送成功，并回读到预览消息 ID；卡片默认允许转发。
- `cardkit_imported`：CardKit CLI 返回 `template_id`，且 `template get` 成功、`template list` 命中同一模板；这是默认直导成功状态。
- `delivered`：CardKit 导入证据成立；如果用户明确要求 Bot 预览，还需另有 `preview_sent + message_id`，但 Bot 不是 CardKit 成功前置。
- `cardkit_import_pending`：CardKit CLI 因 Web session/导入失败，或网页导入因浏览器不可控、登录/CAPTCHA 而待处理。
- `cardkit_imported_bot_preview_pending`：CardKit 已验证，但用户明确要求的 Bot 预览尚未完成。

`configured` 只代表 CLI 有可用身份或权限，不代表远程写入已经成功。

## CardKit API 与编辑器

本 Skill 的 CLI 封装使用：

```text
POST /open-apis/cardkit/v1/cards
body: {"type":"card_json","data":"<stringified Card JSON 2.0>"}
```

它创建的是可由 API 使用的临时 Card Entity，返回 `card_id`，用于后续发送或更新；它不会自动成为网页“我的卡片”里的可编辑资源。默认 CardKit 交付走 Byte CLI 的 Web-backed template import：裸 `.card` 作为输入，成功后回读 `template_id`、`template get` 和 `template list`。若该会话不可用，官方网页编辑器入口是 `https://open.larkoffice.com/cardkit`，再在“导入卡片”入口上传生成的 `.cardkit.card` wrapper。两种文件由同一份最终 DSL 生成。Skill 不读取浏览器 cookie、不伪造网页导入成功，也不把本地 HTML 预览当成正式 CardKit 结果。

接口要求应用的 `tenant_access_token`。因此 `create-cardkit` 默认使用 `--as bot`；当前用户身份的 UAT 不支持该接口，返回 `user access token not support` 时应直接报告身份边界。这里的 API Entity 与 Byte CLI 的 Web-backed 模板资源是两种不同实体。

## Byte CLI CardKit 模板直导（默认路径）

当前 Byte CLI 提供 CardKit 模板的 Web-backed 生命周期命令。对本 Skill 生成的裸 Card 2.0，使用 Skill 适配器先执行只读预检：

```bash
bytedcli -j auth status
python3 scripts/feishu_cli.py push-cardkit \
  --card outputs/demo/demo.card \
  --name "<card_name>" \
  --dry-run
```

适配器内部调用的原始命令是：

```bash
bytedcli -j feishu cardkit template import \
  --file outputs/demo/demo.card \
  --name "<card_name>" \
  --dry-run
```

这条命令使用的是 CardKit Web session，不等同于 ByteCloud 身份，也不等同于 `create-cardkit` 返回的运行时 API `card_id`。真实 `template import` 属于远程写入，必须纳入一次确认；成功后要回读 `template_id`，并用 `template get/list` 证明模板资源存在。若状态返回 `FEISHU_CARDKIT_WEB_AUTH_REQUIRED`，保留 dry-run 结果并回退到已登录浏览器导入 `<name>.cardkit.card`，再用“我的卡片”精确名称 + 编辑页双证据验收。

报告会同时保留 `delivery_workflow.cardkit_import`，明确 raw `.card`、dry-run 命令、session 前置、浏览器 wrapper 兜底和“runtime `card_id` 不等于 template_id”的边界。

## 身份与权限

- `--as bot`：默认用于应用拥有的图片、Card Entity 和机器人消息；需要应用后台开通相应 scope。
- `--as user`：只在用户明确要求以本人身份操作并且 UAT 已授权时使用。
- 图片上传通常需要 `im:resource`。
- 发送应用消息需要对应的 bot/user 消息权限，且 bot 必须已加入目标群或与目标用户建立会话。
- 权限不足时保留本地产物，报告 `missing_scope` 和 CLI 返回的修复提示，不自动执行授权、不切换目标。

## 写入门禁

默认媒体资产链为：先完成信息分工与视觉方法路由 → 静态内容由 Seedream 5.0 Pro 直出 `hero.png`，流程/时间线/状态变化等动态内容由 Seedance 2.5 直出 `hero.gif` → 写入对应 provenance（工具、模型、资产哈希、提示词哈希和模式）→ 人工视觉复核 → 获取真实 `img_key` → 重新编译 `.card`。图片只渲染图片文字白名单中的关系、排版、时间线和 quote，绝不绘制按钮或 CTA；原生 Card 保留精简摘要、来源图表和真实按钮，完整事实留在 `source.txt`。CLI 会拒绝没有匹配溯源的 `hero.png`/`hero.gif`，也不会接受本地路径、URL 或示例 key。

先 dry-run：

```bash
python3 scripts/feishu_cli.py upload-image --image outputs/demo/hero.png --as bot --dry-run
# 动态模式把上行路径改为 outputs/demo/hero.gif
python3 scripts/feishu_cli.py push-cardkit --card outputs/demo/demo.card --name "<card_name>" --dry-run
python3 scripts/feishu_cli.py send-card --card outputs/demo/demo.card --chat-id oc_xxx --as bot --dry-run
```

只有用户明确确认当前图片/目标、内容和身份后，才追加 `--confirm`。解析成功必须使用 CLI 的 `ok: true` 或进程退出码 0；不要用旧式 OpenAPI 顶层 `code: 0` 判断。

多图或 GIF 先运行 `python3 scripts/media_assets.py`，只读确认每个本地文件可读、格式受支持并记录动画帧信息。Seedance 动态模式直接上传通过 provenance 门禁的 `hero.gif`，不强制另做静态伴随图；关键事实必须在原生 Card 中可读。`media_switcher` 依赖 application Bot 的 `card.action.trigger` 事件和后端 `card.update`；没有后端时只走静态首图或图集。

如果用户明确要求 Bot 预览，使用当前用户的 `onBehalfOf.openId` 作为目标，不需要手填用户 ID：

```bash
python3 scripts/feishu_cli.py preview-card --card outputs/demo/demo.card --as bot --dry-run
python3 scripts/feishu_cli.py preview-card --card outputs/demo/demo.card --as bot --confirm --record outputs/demo/demo.preview.json
```

预览消息是普通飞书消息，用户可以在客户端使用转发；这不等同于 CardKit 网页资源导入。网页导入与预览的完整流程见主 Skill 的“统一自动交付：直接 CardKit 导入（Bot 预览可选）”章节及 [`cardkit-file-format.md`](./cardkit-file-format.md)。

## 统一交付事务：直接 CardKit，Bot 预览可选

用户要求 CardKit 时，远程动作按一条事务编排；Bot 预览只有在用户明确要求时才加入：

1. 一次预检最终 raw `.card`、同源 `.cardkit.card` wrapper、CardKit Web session/已登录浏览器；如需图片上传，把 `upload-image --dry-run` 一并纳入预检。若同时要求 Bot，再检查 Bot/本人目标。
2. 展示一次合并 dry-run，用户一次确认整条链的目标、身份、文件和顺序。确认后不在阶段之间再次询问。
3. 必要时上传最终图片并重新编译；随后直接执行 `push-cardkit --confirm --record`，读取真实 `template_id` 和 `template get/list`。
4. 如果 Web session 不可用，使用已登录浏览器的可见网页流程（`.cardkit.card`，精确匹配名称并打开编辑页）；浏览器路径再运行 `record-cardkit-import` 记录双证据。
5. 若用户明确要求 Bot 预览，在 CardKit 阶段之后执行 `preview-card --confirm --record` 并回读 `message_id`；Bot 失败不抹掉已经成立的 CardKit 证据。

CLI 和浏览器是不同的内部执行面，但对用户是一条自动化流程。`create-cardkit` 的 API Entity 不参与 CardKit 模板导入，除非用户另行明确要求创建 API Entity；不得以 `card_id`、本地 HTML 预览、只有列表名称或只有 `--dry-run` 的结果冒充完整成功。
