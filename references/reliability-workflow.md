# 可靠性闭环（2026-09）

## 调用方必须执行，而不是只返回提示词

Python 负责解析、提示词与编译，不会自行调用宿主模型。Skill 调用方读取
`media_task.next_action` 和 `next_steps`，在同一轮主动执行真实的宿主工具。
`needs_image` / `needs_gif` 不是完成；若宿主工具不可用，保留草稿并准确报告缺失能力。
不得拿占位 PNG、手工编造 manifest 或测试 img_key 绕过门禁。

先发现宿主实际工具及其输入/输出能力，再调用。runtime profile 的名称只是适配标签，
不是已经调用模型的证据。图片/动图返回文件后读取验证；登记实际工具，模型 ID 未暴露时
用 `platform-managed`。Pillow 只用于只读解码检查，不用于绘图或后处理。

## 默认视觉质量

- 原生正文目标约 200–350 字，必要时可更短；900 字是拒绝线，不是填满指标。
- 一句摘要 + 3–5 个要点；全文留在 source.txt。不得通过切碎或折叠全文规避预算。
- 信息图必须带来源中的指标或步骤；案例模式不能只把标题传给模型。
- 信息优先；装饰面积不超过约 20%；长标题换行，指标标签与大数字分层。
- “以上、至少、约、缩短、减少、提升、pct”逐字保留；区间和变化率不当绝对值比较。
- 饼图只用于同一整体的完整非负百分比，合计 100%；跨单位数据不拼同一图。
- 单纯格式词如“3D 导览”“v3.2”不是业务数值。
- Emoji 跟随模块含义，不能每个段落都用同一个警告图标。
- 原生按钮使用真实动作目标，图片中不画按钮；缺链接先单问用户。

## 修改已有卡片

编辑保存的 `.spec.json` 后，从它继续编译，不重新从原文路由覆盖用户改动：

```bash
python3 scripts/stable_card.py --resume outputs/my-card/my-card.spec.json \
  --hero-img-key '<real_img_key>'
```

该命令保留 scene、preset、布局、文案与按钮。图片文字/视觉结构变更时，
先同步图片提示词并重新生图、登记和上传；只改原生文案或按钮无需重画图片。
不得复用与当前提示词哈希不符的旧图。

编译后若是 `needs_visual_review`，调用方打开最终 PNG/GIF 和原生卡片预览，
逐字核对中文、数字、单位、布局、移动端可读性与真实按钮。确实检查后才执行：

```bash
python3 scripts/finalize_card.py --spec outputs/my-card/my-card.spec.json \
  --record-review --desktop-screenshot outputs/my-card/desktop.png \
  --mobile-screenshot outputs/my-card/mobile.png --review-surface local_preview \
  --notes '填写实际检查结果，不写尚未做过的验收'
```

验收记录绑定当前 Card 和媒体文件哈希；文件改变后旧验收自动失效。
只有就绪门通过，才能进入已授权的上传/导入链。网页导入也必须先检查同一 report，
不得因使用浏览器而跳过本地门禁。

## 安装与回归

在 Skill 根目录运行，建议使用隔离的 Python 虚拟环境：

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -q
python3 scripts/package_skill.py
```

ZIP 仅包括 Skill 维护目录、依赖清单和 outputs/.gitkeep，不含用户 inputs、
凭据文件、缓存、历史产物或 Git 元数据。压缩包解压后还要重新跑测试；
仓库测试通过不能代替发布包验证。

单元测试中的媒体与 img_key 是明确标注的合成夹具，远程接口是 mock。
它们能验证契约和失败路径，不能证明平台生图、GIF 播放或 CardKit 二次编辑已实测。
这些能力必须在相应宿主与真实 CardKit 编辑器中单独验收并回读。
