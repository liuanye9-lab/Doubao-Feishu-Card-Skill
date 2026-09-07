# 文字与验收更新（2026-09-07）

正文必须保持短而完整，放进原生可编辑高亮面。并列项使用圆点；原文的步骤编号与缩进保留。
压缩只选择完整句子，禁止加省略号截断。无法在预算内保留完整含义时先重写 spec，保留源文和限定条件；不要通过删除限定词让校验通过。
标题适度加粗，长引用正常字号；长日期/说明使用单列高亮，只有短数值使用大字指标格。
制作备注、按钮文案说明留在源/制作记录中，不进入读者正文。无 URL 的按钮仍待补，不生成伪链接；用户确认仅预览时应另行提供明确的禁用态实现。

## 验收证据分层

- 结构通过：JSON、事实长度和行为契约检查。
- 本地视觉通过：逐字检查图片和整卡桌面、手机预览，记录两张真实截图及其哈希。仅备注不再通过。
- CardKit 导入通过：template get/list 与内容回读；不意味着编辑器已验证。
- 编辑器验收：打开精确模板，确认渲染、编辑保存、刷新回读；未执行则 `editor_edit_save_verified=false`。本地近似预览不能代替这一项。

```bash
python3 scripts/finalize_card.py --spec outputs/demo/demo.spec.json --record-review \
  --desktop-screenshot outputs/demo/desktop.png --mobile-screenshot outputs/demo/mobile.png \
  --review-surface local_preview --notes '填写实际发现'
```

`--review-surface cardkit` 只用于真实 CardKit 截图，不能将本地截图标记为 CardKit。
截图存在仅证明证据文件存在，仍须调用方实际观察；合成测试夹具不算生产验收。

更新已有草稿必须使用精确 ID：

```bash
python3 scripts/feishu_cli.py push-cardkit --card outputs/demo/demo.card \
  --template-id ACTUAL_TEMPLATE_ID --name '已确认名称' --confirm --record outputs/demo/delivery.json
```

更新先回读草稿版本再写入，写后比对正文；失败不自动新建。省略 ID 才创建新模板。
已授权的同一任务继续执行，不重复确认；发布、发群和删除仍依用户明确意图。

## 两端同步与发布

共用排版与校验脚本用 `check_shared_core.py --peer <另一仓库>` 比对；投递与验收脚本只比较共享函数。
auto_layout、媒体校验及恢复流程保留 provider 差异，两端运行相同内容行为测试。Seedream/Seedance 的宿主能力和 runtime-profile 不被 Codex 配置覆盖。
分别跑测试，再用 package_skill.py 打包，解压复测。测试通过不代表豆包宿主生图或 GIF 播放已经实测。
每次发布只提交维护文件；真实案例、截图和授权数据不进入公开仓库或 ZIP。
