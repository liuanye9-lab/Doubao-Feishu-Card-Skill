# 稳定流程契约：stable-v1

这是统一飞书卡片 Skill 的唯一执行顺序。每次调用都通过同一套规则生成，不根据临时审美或模型自由发挥改变卡片结构。

## 固定顺序

```text
source_text
  → input_brief
  → 场景路由
  → 场景默认风格
  → 图片 / 原生 Card / 原生按钮 / 原生高亮块分工
  → raw .card + .cardkit.card 同源编译
  → 结构、源文案、动作、图片和 CardKit 门禁
  → 自动选择 Seedream 5.0 Pro 静态图或 Seedance 2.5 直出 GIF + 人工视觉复核
  → 上传真实 img_key 后重新编译
  → 用户明确要求时：直接 CardKit 导入 → template get/list 回读
  → 如明确要求 Bot：追加本人预览并回读 message_id
```

## 路由优先级

从高到低固定为：

1. 调用方明确传入的 `--scene`。
2. 文案的结构信号。例如同时出现“背景/问题”“做法/方法”和“结果/成效”的来源标题，固定路由到 `case-showcase`。
3. 具体关键词。单个泛词（例如“结果”）不能单独把案例路由成 `result-announcement`。
4. `custom` 保守兜底，并在 `route_contract` / `analysis.route_fallback` 记录原因。

场景确定后，预设优先级固定为：显式 `--preset` → 场景注册表 `default_preset` → 规划器 archetype。比如 `case-showcase` 默认使用 `olive-editorial`，不会因为文案长短随机切到另一种风格。

## 输出不变量

- `source_text` 保持原文和 SHA-256；所有展示性变换都写入 `analysis.transformations`。
- raw `.card` 和 `.cardkit.card` 的 `dsl` 来自同一份最终 spec；修改必须改 `.spec.json` 后重新编译。
- 案例的 `quote` 是有来源时的增强位：文案提供“为什么值得看/可复用经验/核心价值”等内容就提升为原生 quote；没有来源时不编造，也不因此把完整案例错误降级成普通 custom 卡。
- 按钮只能是原生 Card 2.0 `button` + `behaviors`，且必须有真实 URL 或已实现的 application Bot callback/form。
- 图片和 GIF 永远是非交互信息层：Seedream/Seedance 提示词明确禁止按钮、CTA 胶囊、箭头动作控件、假链接和按钮形状。媒体中出现类似按钮不算通过，必须重新生成。
- 静态模式没有真实 `img_key` 时状态为 `needs_image`；动态模式为 `needs_gif`。显式 `--no-image` 才能走可发送的原生 Card fallback。
- 高亮块是高层 `highlight` DSL，最多挑 1–3 个来源明确的重点/结论/价值/风险区块，编译为原生 `column_set` + `column.background_style`；普通段落不全部套色。
- 远程动作默认不执行。用户明确要求交付时，一次预检、一次确认，按直接 CardKit 导入 → template get/list 回读连续执行；Bot 预览只有在用户明确要求时追加。

## 状态含义

| 状态 | 含义 | 下一步 |
| --- | --- | --- |
| `ready` | 本地结构、源锁定、动作和 wrapper 门禁通过 | 可本地预览；远程交付仍需明确授权 |
| `needs_image` | 需要 Seedream 5.0 Pro 图片或真实 `img_key`，其余结构已通过 | 生成/复核图片，上传后用真实 key 重新编译 |
| `needs_gif` | 需要 Seedance 2.5 直出 GIF 或真实 `img_key`，其余结构已通过 | 生成/复核 GIF，登记 provenance，上传后用真实 key 重新编译 |
| `blocked` | 结构、占位 URL、场景契约或 CardKit 同源门未通过 | 只修改 source/spec，重新运行固定入口 |
| `cardkit_import_pending` | CardKit 尚未完成，或 CLI/网页会话被阻断 | 继续 Byte CLI 或网页导入并回读 |
| `cardkit_imported_bot_preview_pending` | CardKit 已验证，但用户明确要求的 Bot 预览未完成 | 继续 Bot 预览并回读 `message_id` |

## 唯一稳定入口

调用方优先使用 `scripts/stable_card.py`，不要在多个脚本之间自行拼接不同版本的参数：

```bash
python3 scripts/stable_card.py \
  --text-file ./case.txt \
  --scene case-showcase \
  --purpose "作品提交案例展示" \
  --recipient "大赛群" \
  --output-dir outputs \
  --name case-showcase
```

只粘文案且不确定场景时也可以省略 `--scene`；稳定路由器会先看结构，再看具体词。需要无图快速验证时显式加 `--no-image`。`stable_card.py` 只负责编译和门禁，不擅自发送消息或写入 CardKit。

## 回归门

发布前必须通过：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 "${SKILL_CREATOR:-$HOME/.codex/skills/.system/skill-creator}/scripts/quick_validate.py" .
```

至少检查一个案例文案的场景、预设、quote、真实按钮和两次运行结构快照是否一致。任何图片都必须人工检查：中文、数字、日期、裁切、信息关系，以及是否误画出按钮或 CTA。
