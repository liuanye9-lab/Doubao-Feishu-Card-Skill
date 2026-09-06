# HTML 信息图 fallback 路径

本路径服务于一个明确问题：当卡片既需要图片，又包含较多精确中文、指标、关系节点或真实图表时，直接让图片模型排版容易出现错字、漏字和拥挤。默认仍优先调用豆包工作内置 Seedream 5.0 Pro；只有路由器判断“文字密集 + 结构化”时，才选择 `html_infographic_to_png`。

## 设计原则

- 保留当前选定模板和共享的 Apple 官网式现代主义极简基线：大字号、1.5 倍留白、通栏/细线分隔、克制色板、中等字重标题、轻盈数字；模板只改变网格、锚点和内容节奏，不引入装饰性渐变或卡片墙。
- 先从 `information_allocation.image.include` 取有限的标题、指标、关系和短句；完整原文仍只在 `source.txt` 与原生 Card 事实层中保存。
- 真实图表只消费 `.visual-spec.json` 中已经解析出的数据，不为填满版式补造比例、单位或结论。
- HTML 只承载静态视觉排版，不绘制按钮、CTA、链接、回调或伪交互；真实行动永远由原生 Card 2.0 承载。
- 产出固定视口的自包含 HTML，再由本机 Chrome-family 导出 `hero.png`；HTML、PNG、提示词和 source hash 必须登记到 `hero-generation.json`。

## 路由与恢复

`render_strategy` 有三类值：`auto_model_first`（入口默认）、`native_model`（Seedream 直接生成）和 `html_infographic_to_png`（确定性文字排版 fallback）。已保存的 spec 在 `--resume` 时沿用原策略，不因为环境或文案重排。

HTML 源可继续编辑，但修改后必须按以下顺序重新导出和登记，再上传最终 PNG：

```bash
python3 scripts/render_html_infographic.py \
  --html outputs/<name>/<name>.infographic.html \
  --output outputs/<name>/hero.png
python3 scripts/register_html_render.py \
  --image outputs/<name>/hero.png \
  --html outputs/<name>/<name>.infographic.html \
  --prompt outputs/<name>/<name>.html-prompt.md
```

若 HTML 源、提示词、PNG 或 provenance 任一哈希不一致，上传门禁必须拒绝；不要改后缀或手改 manifest 绕过门禁。

## 参考方法

本地实现吸收了 [baoyu-design](https://github.com/JimLiu/baoyu-design) 关于加载设计方法、复用视觉词汇、预览 HTML 和保持设计系统一致性的公开方法；没有复制它的运行时脚本或外部素材。HTML 路径仍是本 Skill 的受控内部 fallback，不是独立 HTML 设计交付。
