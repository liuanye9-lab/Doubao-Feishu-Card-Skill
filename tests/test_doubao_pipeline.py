import json
import hashlib
import sys
import tempfile
import unittest
from media_fixtures import write_test_png
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from auto_layout import build_auto_spec, infer_scene  # noqa: E402
from doubao_pipeline import run_pipeline  # noqa: E402
from content_intelligence import build_information_allocation, suggest_buttons  # noqa: E402


COPY = "产品发布\n9月4日 14:00 开始\n三项能力：自动整理、可视化表达、一步发送\n立即查看：https://open.feishu.cn"
CAMP_COPY = "Hello象上汇的朋友们大家好呀！\n感谢大家踊跃报名！我们AI先锋大赛开营啦[喇叭]\n0915-九月底：\n- 决赛辅导\n让我们一起践行赵总的理念：\n我们一起让行动发生，让美好发生。愛AI，让生活更美好[比心]"
FULL_CAMP_COPY = """Hello象上汇的朋友们大家好呀！

感谢大家踊跃报名！我们AI先锋大赛开营啦[喇叭]

本群内我们会

1. 通知2场培训的时间（多维表➕智能体）
2. 发放提交作品的模版
3. 搭建的过程中欢迎大家分享心得！同时如果遇到问题可以发群里，我们答疑哦！

本次大赛的时间线：

0824-0904：

- 0825多维表格培训
- 0904周智能体培训

0915：

- 提交初赛参赛作品
- 初赛通过之后，会拉决赛群！

0915-九月底：

- 决赛辅导
- 路演抽签+彩排

让我们一起践行赵总的理念：

我们一起让行动发生，让美好发生。愛AI，让生活更美好[比心]"""
CASE_COPY = """酒店各区域智能巡视图系统
AI先锋大赛 · 作品案例展示
主题：AI+门店管理
对象：新员工与门店服务
形式：3D 楼层导览 + 岗位视角
状态：覆盖 11 个重点区域
作品页面名称：酒店区域导览助手
地点：杭州曲水兰亭度假酒店
一句话价值：把酒店“带教靠人讲、区域靠记忆、服务靠经验”，变成可视化、可检索、可持续学习的门店空间管理助手。

# 背景
酒店区域多、岗位不同，新员工需要同时建立空间认知、岗位认知和服务知识。

# 做法
1. 交互式区域地图：支持 3D 楼层导览，降低新员工认路和带教成本。
2. 岗位视角：让学习内容更贴近真实岗位任务。

# 结果
作品页面已呈现 3D 楼层导览、岗位视角、知识中心和学习中心，共 11 个重点区域。

# 进阶构思
为什么值得看：这件作品把“门店空间”从静态信息，升级为可以被带教、被检索、被跟踪的经营入口。
点击查看：https://example.com/hotel"""

LONG_DENSE_COPY = """象上汇｜AI驱动的师徒带教数字化管理体系
一句话介绍：针对汤泉行业员工流失率高、师徒带教过程不可视的痛点，基于飞书多维表格与智能体搭建数字化管理体系。
带教完成率：95%以上
独立上岗周期：缩短30%
3个月留存率：提升20pct
人资管理耗时：减少70%
# 业务痛点
带教过程黑盒化，师傅每天教了什么、徒弟掌握多少没有记录；不同师傅带教内容、节奏和质量差异大；新人缺乏及时反馈，试用期流失率偏高。
# 核心功能模块
模块一：标准化带教计划模板，按岗位预置四周计划并自动匹配师傅。
模块二：师徒每日双向打卡，智能体自动提醒并识别评分差异。
模块三：每周生成带教复盘报告，汇总完成率、掌握度趋势和异常名单。
模块四：月底生成评估报告，给出转正、延长带教或重点关注建议。
# 核心价值
构建每日打卡、每周复盘、月度评估到转正建议的闭环，让带教进度可视、质量可量、问题可预警。
"""


class DoubaoPipelineTests(unittest.TestCase):
    def _run_with_seedream(self, text: str, temp_dir: str, name: str, **kwargs):
        bundle = Path(temp_dir) / name
        bundle.mkdir(parents=True, exist_ok=True)
        image_path = bundle / "hero.png"
        write_test_png(image_path)
        report = run_pipeline(text, Path(temp_dir), name=name, **kwargs)
        prompt_path = bundle / f"{name}.image-prompt.md"
        (bundle / "hero-generation.json").write_text(
            json.dumps({
                "schema": "doubao-feishu-image-provenance/1",
                "tool": "doubao.image_gen",
                "generation_family": "seedream-class",
                "model_id": "test",
                "asset": str(image_path),
                "asset_name": "hero.png",
                "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "prompt_file": str(prompt_path),
                "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
                "text_policy": "seedream_5_pro_direct_selected_text_and_layout",
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        report = run_pipeline(text, Path(temp_dir), name=name, **kwargs)
        if report["readiness"]["image_ready"]:
            from finalize_card import record_review
            report = record_review(report["editable_spec"], "Synthetic QA fixture; contract test only.")
        return report

    def test_default_run_is_seedream_direct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(COPY, Path(temp_dir), name="demo")
            bundle = Path(temp_dir) / "demo"
            card = json.loads((bundle / "demo.card").read_text(encoding="utf-8"))
            spec = json.loads((bundle / "demo.spec.json").read_text(encoding="utf-8"))
            plan = json.loads((bundle / "demo.plan.json").read_text(encoding="utf-8"))
            manifest = json.loads((bundle / "demo.cardkit-import.json").read_text(encoding="utf-8"))
            wrapper = json.loads((bundle / "demo.cardkit.card").read_text(encoding="utf-8"))
            wrapper_json = json.loads((bundle / "demo.cardkit.json").read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "needs_image")
        self.assertTrue(report["readiness"]["valid"])
        self.assertFalse(report["readiness"]["sendable"])
        self.assertFalse(report["doubao"]["card_image_contract"]["card_image_embedded"])
        self.assertFalse(any(str(key).startswith("base") for key in report["doubao"]["card_image_contract"]))
        self.assertEqual(report["doubao"]["card_image_contract"]["image_generation_mode"], "seedream_5_pro_direct_full_card")
        self.assertEqual(report["doubao"]["card_image_contract"]["image_text_layout"], "seedream_5_pro_direct_full_card")
        self.assertEqual(spec["visual_contract"]["text_in_image"], "seedream_5_pro_direct_selected_text_and_layout")
        self.assertEqual(spec["visual_contract"]["image_text_layout"], "seedream_5_pro_direct_full_card")
        self.assertEqual(spec["hero"]["image_source"], "ai_generated")
        self.assertEqual(spec["hero"]["image_roles"], ["cover", "information_carrier", "text_companion"])
        self.assertEqual(spec["hero"]["generation_family"], "seedream-class")
        self.assertTrue(report["ai_generation"]["required"])
        self.assertFalse(report["readiness"]["seedream_output_ready"])
        self.assertEqual(spec["analysis"]["source_text"], COPY)
        self.assertIn("14:00", json.dumps(spec, ensure_ascii=False))
        hero_plan = next(item for item in plan["component_strategy"] if item.get("component") == "hero")
        self.assertTrue(hero_plan["selected"])
        self.assertIn("feishu_cli.py push-cardkit", report["compile"]["cardkit_import_command"])
        self.assertIn("feishu_cli.py preview-card", report["next_steps"]["preview_bot"])
        workflow = report["delivery_workflow"]
        self.assertEqual(workflow["name"], "cardkit_direct_import")
        self.assertEqual(workflow["mode"], "cardkit_first")
        self.assertTrue(workflow["single_preflight"])
        self.assertTrue(workflow["single_confirmation_gate"])
        self.assertLess(
            workflow["order"].index("import_cardkit_directly"),
            workflow["order"].index("optionally_preview_card_via_feishu_cli"),
        )
        self.assertTrue(workflow["preview_optional"])
        self.assertTrue(workflow["preview_record"].endswith("demo.preview.json"))
        self.assertEqual(manifest["delivery_workflow"], workflow)
        self.assertEqual(
            manifest["automation"]["confirmation"],
            "single_confirmation_gate_for_all_remote_writes",
        )
        self.assertEqual(manifest["mode"], "cardkit_direct")
        self.assertEqual(Path(manifest["card"]).resolve(), (bundle / "demo.cardkit.card").resolve())
        self.assertEqual(Path(manifest["api_card"]).resolve(), (bundle / "demo.card").resolve())
        self.assertEqual(wrapper["dsl"], card)
        self.assertEqual(wrapper_json, wrapper)
        self.assertEqual(Path(report["cardkit_import_file"]).resolve(), (bundle / "demo.cardkit.card").resolve())
        self.assertFalse(report["readiness"]["cardkit_editor_ready"])
        self.assertEqual(card["config"]["enable_forward"], True)
        self.assertTrue(any(item.get("tag") == "button" for item in card["body"]["elements"]))
        self.assertFalse(any(item.get("action") for item in card["body"]["elements"]))

    def test_explicit_no_image_is_sendable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(COPY, Path(temp_dir), name="no-image", no_image=True)
            card_path = Path(temp_dir) / "no-image" / "no-image.card"
            card = json.loads(card_path.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["readiness"]["sendable"])
        self.assertTrue(report["readiness"]["cardkit_entity_ready"])
        self.assertFalse(any(item.get("tag") == "img" for item in card["body"]["elements"]))

    def test_source_level_no_image_request_overrides_default_visual(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline("简短公告\n不要图片，只保留文字。\n请查看详情。", Path(temp_dir), name="source-no-image")

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["doubao"]["image_required"])
        self.assertTrue(report["readiness"]["sendable"])

    def test_long_copy_is_compacted_and_full_source_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(LONG_DENSE_COPY, Path(temp_dir), name="dense")
            bundle = Path(temp_dir) / "dense"
            card = json.loads((bundle / "dense.card").read_text(encoding="utf-8"))
            source = (bundle / "dense.source.txt").read_text(encoding="utf-8")

        stats = report["validation"]["stats"]
        self.assertEqual(source, LONG_DENSE_COPY)
        self.assertLessEqual(stats["visible_text_chars"], 900)
        self.assertLessEqual(stats["max_text_block_chars"], 220)
        self.assertFalse(any(item.get("tag") == "collapsible_panel" for item in card["body"]["elements"]))
        self.assertEqual(stats["charts"], 0)

    def test_source_backed_metrics_create_editable_visual_spec_and_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(LONG_DENSE_COPY, Path(temp_dir), name="metrics")
            bundle = Path(temp_dir) / "metrics"
            visual_spec = json.loads((bundle / "metrics.visual-spec.json").read_text(encoding="utf-8"))
            card = json.loads((bundle / "metrics.card").read_text(encoding="utf-8"))

        self.assertEqual(visual_spec["schema"], "doubao-feishu-card-visual-spec/1")
        self.assertEqual(visual_spec["visual_type"], "thematic_information_visual")
        self.assertEqual([item["display"] for item in visual_spec["metrics"][:4]], ["95%以上", "缩短30%", "提升20pct", "减少70%"])
        self.assertIsNone(visual_spec["chart"])
        self.assertFalse(any(item.get("tag") == "chart" for item in card["body"]["elements"]))
        self.assertEqual(report["status"], "needs_image")

    def test_buttons_are_real_native_actions_and_capped_at_two(self) -> None:
        source = (
            "行动入口\n"
            "立即查看：https://open.feishu.cn/view\n"
            "立即报名：https://open.feishu.cn/register\n"
            "下载材料：https://open.feishu.cn/download"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(source, Path(temp_dir), name="buttons", no_image=True)
            card = json.loads((Path(temp_dir) / "buttons" / "buttons.card").read_text(encoding="utf-8"))

        buttons = [item for item in card["body"]["elements"] if item.get("tag") == "button"]
        self.assertLessEqual(len(buttons), 2)
        self.assertTrue(buttons)
        self.assertTrue(all(item.get("behaviors") for item in buttons))
        self.assertTrue(all(item["behaviors"][0].get("type") == "open_url" for item in buttons))
        self.assertEqual(report["validation"]["stats"]["buttons"], len(buttons))

    def test_semantic_highlights_compile_to_native_card_surfaces(self) -> None:
        case_source = (
            "AI先锋大赛·作品案例展示\n"
            "背景/痛点：员工需要一个一个数泡面，花费较多时间。\n"
            "做法：拍一张照片，识别各品种少了几包。\n"
            "结果/价值：员工可以直接按识别结果去补充。"
        )
        warning_source = "活动通知\n请务必在9月4日前提交报名信息。"
        with tempfile.TemporaryDirectory() as temp_dir:
            case_report = run_pipeline(case_source, Path(temp_dir), name="highlight-case", no_image=True)
            warning_report = run_pipeline(warning_source, Path(temp_dir), name="highlight-warning", no_image=True)
            case_bundle = Path(temp_dir) / "highlight-case"
            warning_bundle = Path(temp_dir) / "highlight-warning"
            case_spec = json.loads((case_bundle / "highlight-case.spec.json").read_text(encoding="utf-8"))
            warning_spec = json.loads((warning_bundle / "highlight-warning.spec.json").read_text(encoding="utf-8"))
            case_card = json.loads((case_bundle / "highlight-case.card").read_text(encoding="utf-8"))
            warning_card = json.loads((warning_bundle / "highlight-warning.card").read_text(encoding="utf-8"))

        result_section = next(block for block in case_spec["blocks"] if str(block.get("title") or "").endswith("结果/价值"))
        self.assertTrue(result_section["highlight"])
        self.assertEqual(result_section["tone"], "brand")
        case_highlight = next(
            element for element in case_card["body"]["elements"]
            if element.get("tag") == "column_set"
            and "员工可以直接按识别结果去补充" in json.dumps(element, ensure_ascii=False)
        )
        self.assertEqual(case_highlight["columns"][0]["background_style"], "grey-100")
        self.assertIn("员工可以直接按识别结果去补充", json.dumps(case_highlight, ensure_ascii=False))

        warning_block = next(block for block in warning_spec["blocks"] if block.get("type") == "highlight")
        self.assertEqual(warning_block["tone"], "danger")
        warning_highlight = next(
            element for element in warning_card["body"]["elements"]
            if element.get("tag") == "column_set"
            and any(column.get("background_style") == "red-50" for column in element.get("columns", []))
        )
        warning_json = json.dumps(warning_highlight, ensure_ascii=False)
        self.assertIn("请务必在9月4日", warning_json)
        self.assertIn("提交报名信息", warning_json)
        self.assertTrue(case_report["readiness"]["sendable"])
        self.assertTrue(warning_report["readiness"]["sendable"])

    def test_semantic_highlight_budget_is_bounded(self) -> None:
        source = (
            "层级测试\n"
            "# 重点\n第一条重点说明。\n"
            "# 结论\n第二条结论说明。\n"
            "# 结果\n第三条结果说明。\n"
            "# 下一步\n第四条行动说明。"
        )
        spec = build_auto_spec(source)
        highlights = [
            block for block in spec["blocks"]
            if block.get("highlight") or block.get("type") == "highlight"
        ]

        self.assertEqual(len(highlights), 3)
        next_step = next(block for block in spec["blocks"] if str(block.get("title") or "").endswith("下一步"))
        self.assertFalse(next_step.get("highlight", False))

    def test_generated_card_uses_cardkit_native_text_colors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_pipeline(CASE_COPY, Path(temp_dir), name="native-colors", no_image=True)
            card = json.loads((Path(temp_dir) / "native-colors" / "native-colors.card").read_text(encoding="utf-8"))

        serialized = json.dumps(card, ensure_ascii=False)
        self.assertNotIn("brand_accent", serialized)
        self.assertNotIn("brand_gold", serialized)
        self.assertNotIn("brand_ink", serialized)

    def test_studio_intake_and_ux_rd_qa_contract_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                COPY,
                Path(temp_dir),
                name="studio-contract",
                no_image=True,
                purpose="作品提交案例展示",
                recipient="大赛群",
            )
            bundle = Path(temp_dir) / "studio-contract"
            spec = json.loads((bundle / "studio-contract.spec.json").read_text(encoding="utf-8"))
            card = json.loads((bundle / "studio-contract.card").read_text(encoding="utf-8"))

        self.assertEqual(report["input_brief"]["purpose"]["value"], "作品提交案例展示")
        self.assertEqual(report["input_brief"]["recipient"]["value"], "大赛群")
        self.assertEqual(report["input_brief"]["recipient"]["role"], "delivery_context_only")
        self.assertTrue(report["quality_gates"]["required_passed"])
        self.assertEqual(
            [stage["id"] for stage in report["generation_workflow"]["stages"]],
            ["ux", "rd", "qa"],
        )
        self.assertEqual(report["generation_workflow"]["stages"][-1]["status"], "passed")
        self.assertEqual(spec["quality_gates"], report["quality_gates"])
        self.assertEqual(spec["generation_workflow"], report["generation_workflow"])
        self.assertEqual(
            report["delivery_workflow"]["cardkit_import"]["preferred"],
            "bytedcli_web_backed_template_import",
        )
        self.assertIn("feishu cardkit template import", report["next_steps"]["import_to_cardkit_cli"])
        self.assertIn("--dry-run", report["next_steps"]["import_to_cardkit_cli"])
        summary = card["config"]["summary"]["content"]
        self.assertGreaterEqual(len(summary), 8)
        self.assertLessEqual(len(summary), 60)

    def test_design_plan_can_disable_hero_without_cli_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                COPY,
                Path(temp_dir),
                name="planned-no-image",
                design_plan={"media_policy": {"need_hero": False}},
            )

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["doubao"]["image_required"])
        self.assertTrue(report["readiness"]["sendable"])

    def test_real_img_key_unlocks_image_led_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._run_with_seedream(COPY, temp_dir, "with-image", hero_img_key="img_v3_test_key")
            card_path = Path(temp_dir) / "with-image" / "with-image.card"
            card = json.loads(card_path.read_text(encoding="utf-8"))
            direct_file_exists = (Path(temp_dir) / "with-image" / "hero.png").is_file()

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["readiness"]["image_ready"])
        self.assertTrue(report["readiness"]["seedream_output_ready"])
        self.assertTrue(report["doubao"]["card_image_contract"]["card_image_embedded"])
        self.assertTrue(report["doubao"]["card_image_contract"]["final_asset_contains_functional_text"])
        self.assertEqual(report["doubao"]["card_image_contract"]["image_text_layout"], "seedream_5_pro_direct_full_card")
        self.assertEqual(report["doubao"]["card_image_contract"]["status"], "embedded_seedream_image")
        self.assertTrue(direct_file_exists)
        self.assertFalse(any(str(key).startswith("base") for key in report["doubao"]["card_image_contract"]))
        image = next(item for item in card["body"]["elements"] if item.get("tag") == "img")
        self.assertEqual(image["img_key"], "img_v3_test_key")

    def test_greeting_focus_date_range_and_prominent_quote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._run_with_seedream(CAMP_COPY, temp_dir, "camp", hero_img_key="img_v3_test_key")
            bundle = Path(temp_dir) / "camp"
            spec = json.loads((bundle / "camp.spec.json").read_text(encoding="utf-8"))
            card = json.loads((bundle / "camp.card").read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "ready")
        self.assertEqual(spec["title"], "AI先锋大赛开营啦")
        timeline_items = [item for block in spec["blocks"] if block.get("type") == "timeline" for item in block.get("items", [])]
        self.assertIn("9月15日—九月底", [item.get("date") for item in timeline_items])
        self.assertEqual(spec["blocks"][-1]["type"], "quote")
        self.assertTrue(report["doubao"]["image_required"])
        self.assertTrue(report["doubao"]["visual_output_ready"])
        self.assertEqual(spec["information_allocation"]["decision"], "image_plus_native")
        self.assertTrue(report["readiness"]["seedream_output_ready"])
        self.assertEqual(card["body"]["elements"][0]["tag"], "img")
        self.assertTrue(card["body"]["elements"][-1]["element_id"].startswith("quote_"))
        collapsed = [element for element in card["body"]["elements"] if element.get("tag") == "collapsible_panel"]
        self.assertFalse(any("quote_" in json.dumps(element, ensure_ascii=False) for element in collapsed))

    def test_forced_case_showcase_promotes_value_and_quote_before_folding(self) -> None:
        spec = build_auto_spec(
            CASE_COPY,
            requested_scene="case-showcase",
            requested_preset="olive-editorial",
        )
        quote_blocks = [block for block in spec["blocks"] if block.get("type") == "quote"]
        collapsed = [block for block in spec["blocks"] if block.get("type") == "collapse"]

        self.assertEqual(spec["scene"], "case-showcase")
        self.assertEqual(spec["type"], "story")
        self.assertEqual(spec["preset"], "olive-editorial")
        self.assertEqual(
            spec["lead"],
            "把酒店“带教靠人讲、区域靠记忆、服务靠经验”，变成可视化、可检索、可持续学习的门店空间管理助手。",
        )
        self.assertEqual(len(quote_blocks), 1)
        self.assertEqual(quote_blocks[0]["title"], "为什么值得看")
        self.assertIn("门店空间", quote_blocks[0]["text"])
        self.assertNotIn("为什么值得看：", json.dumps(collapsed, ensure_ascii=False))
        self.assertIsInstance(spec.get("hero"), dict)
        self.assertEqual(spec["prompt_routing"]["primary_content_profile"], "case-study")
        self.assertEqual(spec["prompt_routing"]["reference_template"], "case-showcase")
        self.assertEqual(spec["prompt_routing"]["visual_skill_routing"]["selection_rule"], "case-metrics-evidence")
        image_roles = [item.get("role") for item in spec["information_allocation"]["image"]["include"]]
        self.assertEqual(image_roles[:4], ["title", "relationship", "relationship", "relationship"])
        self.assertIn("quote", image_roles)
        self.assertEqual(
            next(item for item in spec["blocks"] if item.get("type") == "buttons")["items"][0]["url"],
            "https://example.com/hotel",
        )

    def test_case_showcase_uses_metadata_grid_and_three_reading_sections(self) -> None:
        source = (
            "案例展示｜泡面补货拍照识别\n"
            "选手：宋洋\n"
            "公司：杭州水裹汤泉酒店有限公司\n"
            "部门：运营部\n"
            "智能体方向：AI + 产供销协同-\n"
            "当前状态：已搭建出demo\n"
            "初赛作品链接：https://example.com/work\n"
            "案例拆解（根据报名原文整理，不增加新事实）\n"
            "背景/痛点：员工需要一个一个数泡面，花费较多时间。\n"
            "做法：拍一张照片，识别各品种少了几包。\n"
            "结果/价值：员工可以直接按识别结果去补充。"
        )
        spec = build_auto_spec(
            source,
            requested_scene="case-showcase",
            requested_preset="olive-editorial",
            design_plan={
                "fold_strategy": {
                    "mode": "none",
                    "use_collapsible_panel": False,
                }
            },
        )

        self.assertEqual([block["type"] for block in spec["blocks"]], ["text", "facts", "div", "section", "section", "section", "buttons"])
        self.assertEqual(
            [str(item["label"]).split(" ", 1)[-1] for item in spec["blocks"][1]["items"]],
            ["公司", "部门", "智能体方向", "当前状态"],
        )
        self.assertEqual(
            [str(block["title"]).split(" ", 1)[-1] for block in spec["blocks"] if block["type"] == "section"],
            ["背景/痛点", "做法", "结果/价值"],
        )
        self.assertNotIn("初赛作品链接", json.dumps(spec["blocks"], ensure_ascii=False))
        self.assertEqual(spec["blocks"][-1]["items"][0]["text"], "查看作品")
        self.assertEqual(spec["blocks"][-1]["items"][0]["url"], "https://example.com/work")

        multi_method = build_auto_spec(
            source.replace(
                "做法：拍一张照片，识别各品种少了几包。",
                "做法：\n1. 拍一张照片，识别各品种少了几包。\n2. 按识别结果去后面补充。",
            ),
            requested_scene="case-showcase",
            requested_preset="olive-editorial",
            design_plan={"fold_strategy": {"mode": "none", "use_collapsible_panel": False}},
        )
        self.assertEqual(
            [block["type"] for block in multi_method["blocks"]],
            ["text", "facts", "div", "section", "section", "section", "buttons"],
        )
        self.assertIn("2. 按识别结果去后面补充。", next(block for block in multi_method["blocks"] if str(block.get("title") or "").endswith("做法"))["body"])

    def test_structured_case_route_beats_generic_result_and_uses_scene_preset(self) -> None:
        source = (
            "酒店区域导览助手\n"
            "主题：AI+门店管理\n"
            "背景：区域多、岗位不同\n"
            "做法：交互式地图和岗位视角\n"
            "结果：覆盖 11 个重点区域"
        )
        scene, card_type, evidence = infer_scene(source)
        spec = build_auto_spec(source)

        self.assertEqual((scene, card_type), ("case-showcase", "story"))
        self.assertEqual(spec["scene"], "case-showcase")
        self.assertEqual(spec["preset"], "olive-editorial")
        self.assertEqual(spec["route_contract"]["precedence"], "explicit_scene > source_structure > specific_keywords > custom")
        self.assertEqual(evidence[0]["precedence"], "case_structure_over_generic_keyword")

    def test_stable_pipeline_is_reproducible_for_same_source(self) -> None:
        source = (
            "门店智能巡视案例\n"
            "主题：AI+门店管理\n"
            "背景：区域多、岗位不同\n"
            "做法：交互式地图和岗位视角\n"
            "结果：覆盖 11 个重点区域\n"
            "一句话价值：让新员工更快建立空间认知。\n"
            "为什么值得看：空间信息可以继续承接服务协同。\n"
            "点击查看：https://open.feishu.cn"
        )

        def snapshot(root: str) -> dict:
            report = run_pipeline(source, Path(root), name="stable", no_image=True)
            bundle = Path(root) / "stable"
            spec = json.loads((bundle / "stable.spec.json").read_text(encoding="utf-8"))
            card = json.loads((bundle / "stable.card").read_text(encoding="utf-8"))
            return {
                "status": report["status"],
                "workflow_profile": report["workflow_profile"],
                "scene": spec["scene"],
                "preset": spec["preset"],
                "blocks": spec["blocks"],
                "route_contract": spec["route_contract"],
                "stability_contract": spec["stability_contract"],
                "elements": card["body"]["elements"],
            }

        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_snapshot = snapshot(first)
            second_snapshot = snapshot(second)

        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(first_snapshot["status"], "ready")
        self.assertEqual(first_snapshot["workflow_profile"], "stable-v1")

    def test_default_emoji_policy_is_semantic_and_preserves_explicit_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._run_with_seedream(FULL_CAMP_COPY, temp_dir, "emoji", hero_img_key="img_v3_test_key")
            bundle = Path(temp_dir) / "emoji"
            spec = json.loads((bundle / "emoji.spec.json").read_text(encoding="utf-8"))
            card = json.loads((bundle / "emoji.card").read_text(encoding="utf-8"))

        rendered = json.dumps(card, ensure_ascii=False)
        self.assertEqual(report["status"], "ready")
        self.assertEqual(rendered.count("📣"), 1)
        self.assertEqual(rendered.count("🫶"), 1)
        self.assertNotIn("🚀", rendered)
        self.assertTrue(any(marker in rendered for marker in ("💬", "🗓️", "🧩", "🏁")))
        self.assertGreaterEqual(report["validation"]["stats"]["emoji_count"], 3)
        self.assertLessEqual(report["validation"]["stats"]["emoji_count"], 6)
        self.assertTrue(any(item.get("kind", "").endswith("_emoji") for item in spec["analysis"]["transformations"]))

    def test_timeline_bullets_stay_with_their_date(self) -> None:
        spec = build_auto_spec(FULL_CAMP_COPY)
        timelines = [block for block in spec["blocks"] if block.get("type") == "timeline"]
        self.assertEqual(len(timelines), 1)
        items = timelines[0]["items"]
        self.assertEqual(len(items), 3)
        self.assertIn("多维表格培训", items[0]["body"])
        self.assertIn("提交初赛参赛作品", items[1]["body"])
        self.assertIn("路演抽签+彩排", items[2]["body"])
        self.assertTrue(any(item.get("kind") == "timeline_detail_group" for item in spec["analysis"]["transformations"]))

    def test_timeline_detail_group_stops_after_plain_text(self) -> None:
        spec = build_auto_spec("活动安排\n9月1日：\n- 开营\n补充说明\n- 9月2日闭营")
        timelines = [block for block in spec["blocks"] if block.get("type") == "timeline"]
        self.assertEqual(len(timelines), 2)
        self.assertIn("开营", timelines[0]["items"][0]["body"])
        self.assertEqual(timelines[1]["items"][0]["date"], "9月2日")

    def test_information_allocation_gives_plain_notice_a_thematic_visual(self) -> None:
        source = (
            "大家好\n"
            "1. 通知培训时间\n"
            "2. 发放提交作品模板\n"
            "3. 遇到问题可以在群里答疑"
        )
        spec = build_auto_spec(source)
        allocation = spec["information_allocation"]

        self.assertEqual(allocation["decision"], "image_plus_native")
        self.assertTrue(allocation["image"]["use"])
        self.assertTrue(allocation["image"]["include"])
        self.assertIn("hero", spec)
        self.assertTrue(allocation["native_card"]["use"])

    def test_information_allocation_promotes_relationships_not_long_copy(self) -> None:
        source = (
            "AI先锋大赛\n"
            "0824-0904：\n"
            "- 0825多维表格培训\n"
            "0915：\n"
            "- 提交初赛参赛作品\n"
            "0915-九月底：\n"
            "- 决赛辅导与路演彩排\n"
            "群内遇到问题可以随时发消息，我们会统一答疑。"
        )
        spec = build_auto_spec(source)
        allocation = spec["information_allocation"]
        image_text = [item["text"] for item in allocation["image"]["include"]]

        self.assertEqual(allocation["decision"], "image_plus_native")
        self.assertTrue(allocation["image"]["use"])
        self.assertGreaterEqual(len([item for item in allocation["image"]["include"] if item["role"] == "stage"]), 3)
        self.assertFalse(any("随时发消息" in text for text in image_text))
        self.assertIn("群内遇到问题可以随时发消息，我们会统一答疑。", spec["analysis"]["source_text"])
        self.assertEqual(spec["analysis"]["design_plan"]["information_allocation"]["decision"], "image_plus_native")

    def test_information_allocation_promotes_short_metrics(self) -> None:
        source = "活跃率：98%\n人均时长：245min\nIM渗透率：98%\n口径说明：来自本周统计。"
        allocation = build_information_allocation(source)
        metric_items = [item["text"] for item in allocation["image"]["include"] if item["role"] == "metric"]

        self.assertTrue(allocation["image"]["use"])
        self.assertEqual(allocation["decision"], "image_plus_native")
        self.assertTrue(any("人均时长" in item and "245min" in item for item in metric_items))
        self.assertEqual(allocation["native_card"]["source_line_count"], 4)

    def test_button_allocation_requires_action_target_pair(self) -> None:
        passive = suggest_buttons(["来源：https://example.com/reference"])
        action = suggest_buttons(["立即报名：https://example.com/register"])
        pending = suggest_buttons(["请立即报名参加活动"])

        self.assertFalse(any(item["button_eligible"] for item in passive))
        self.assertEqual(passive[0]["surface"], "inline_url")
        self.assertEqual(action[0]["button_kind"], "primary")
        self.assertEqual(action[0]["surface"], "open_url")
        self.assertEqual(pending[0]["surface"], "needs_url_or_callback")
        self.assertFalse(any(item["button_eligible"] for item in pending))

    def test_real_button_stays_native_and_never_enters_image_allocation(self) -> None:
        allocation = build_information_allocation(COPY)

        self.assertTrue(allocation["buttons"]["use"])
        self.assertEqual(allocation["buttons"]["primary"]["surface"], "open_url")
        self.assertFalse(any(item.get("role") == "cta" for item in allocation["image"]["include"]))
        self.assertIn("按钮/CTA 标签", allocation["image"]["not_for"])

    def test_information_visual_contract_is_not_decorative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._run_with_seedream(FULL_CAMP_COPY, temp_dir, "visual", hero_img_key="img_v3_test_key")
            bundle = Path(temp_dir) / "visual"
            spec = json.loads((bundle / "visual.spec.json").read_text(encoding="utf-8"))
            prompt = (bundle / "visual.image-prompt.md").read_text(encoding="utf-8")
            prompt_routing = json.loads((bundle / "visual.prompt-routing.json").read_text(encoding="utf-8"))
            manifest = json.loads((bundle / "visual.cardkit-import.json").read_text(encoding="utf-8"))

        media = spec["analysis"]["design_plan"]["media_policy"]
        self.assertTrue(spec["visual_contract"]["not_decorative"])
        self.assertEqual(spec["visual_contract"]["image_source"], "ai_generated")
        self.assertIn("information_carrier", spec["visual_contract"]["image_roles"])
        self.assertEqual(spec["visual_contract"]["text_in_image"], "seedream_5_pro_direct_selected_text_and_layout")
        self.assertEqual(spec["visual_contract"]["image_text_layout"], "seedream_5_pro_direct_full_card")
        self.assertGreaterEqual(len(spec["visual_contract"]["functional_text"]), 2)
        self.assertTrue(media["information_carrier"])
        self.assertEqual(spec["visual_contract"]["role"], "information_timeline")
        self.assertIn("final information-bearing Feishu card image in one Seedream 5.0 Pro pass", prompt)
        self.assertIn("Image text whitelist", prompt)
        self.assertIn("Native Card allocation", prompt)
        self.assertIn("Do not depend on HTML, CSS, SVG, Pillow", prompt)
        self.assertNotIn("Base image text (verbatim): none", prompt)
        self.assertNotIn("Functional overlay", prompt)
        self.assertIn("Auto-routed prompt recipe", prompt)
        self.assertIn("Auto-selected visual skill packs", prompt)
        self.assertIn("Never generate a button", prompt)
        self.assertIn("Native Card buttons are intentionally omitted", prompt)
        self.assertNotIn('"role": "cta"', prompt)
        self.assertFalse(any(item.get("role") == "cta" for item in spec["information_allocation"]["image"]["include"]))
        self.assertEqual(prompt_routing["primary_content_profile"], "timeline")
        self.assertIn("timeline", prompt_routing["selected_profiles"])
        self.assertIn("quote-anchor", prompt_routing["selected_profiles"])
        self.assertEqual(
            prompt_routing["visual_skill_routing"]["selected_packs"],
            ["baoyu-infographic", "guizang-social-swiss"],
        )
        self.assertEqual(prompt_routing["visual_skill_routing"]["style_id"], "blueprint-timeline")
        self.assertEqual(prompt_routing["visual_skill_routing"]["visual_layout"], "linear-progression")
        self.assertTrue(prompt_routing["matched_profiles"])
        self.assertEqual(report["prompt_routing_file"], str(bundle / "visual.prompt-routing.json"))
        self.assertTrue(report["doubao"]["seedream_required"])
        self.assertTrue(report["doubao"]["visual_output_ready"])
        self.assertEqual(manifest["execution"], "bytedcli_web_backed_or_browser_ui")
        self.assertTrue(manifest["size_ok"])

    def test_semantic_emoji_mode_is_bounded(self) -> None:
        spec = build_auto_spec(FULL_CAMP_COPY, emoji_mode="semantic")
        generated = [
            item for item in spec["analysis"]["transformations"]
            if item.get("kind", "").endswith("_emoji")
        ]
        self.assertGreaterEqual(len(generated), 1)
        self.assertLessEqual(len(generated), 6)

    def test_banner_mode_uses_seedream_profile_and_native_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                COPY,
                Path(temp_dir),
                name="banner",
                design_plan={
                    "media_policy": {
                        "need_hero": True,
                        "image_generation_mode": "seedream_5_pro_banner_plus_native_card",
                    }
                },
            )
            bundle = Path(temp_dir) / "banner"
            spec = json.loads((bundle / "banner.spec.json").read_text(encoding="utf-8"))
            prompt = (bundle / "banner.image-prompt.md").read_text(encoding="utf-8")

        self.assertEqual(report["status"], "needs_image")
        self.assertEqual(spec["image_generation_mode"], "seedream_5_pro_banner_plus_native_card")
        self.assertEqual(spec["hero"]["text_in_image"], "seedream_5_pro_banner_selected_text_and_layout")
        self.assertEqual(
            spec["hero"]["image_roles"],
            ["banner", "information_carrier", "text_companion"],
        )
        self.assertEqual(spec["hero"]["generation_model"], "seedream-5.0-pro")
        self.assertEqual(report["media"]["generation_model_label"], "Seedream 5.0 Pro")
        self.assertEqual(
            report["doubao"]["card_image_contract"]["final_asset_role"],
            "seedream_banner_plus_native_card_components",
        )
        self.assertIn("banner-header-image", prompt)
        self.assertIn("Seedream 5.0 Pro", prompt)
        self.assertIn("Native Card carries", prompt)
        self.assertEqual(len(report["proposals"]), 3)

    def test_explicit_image_mode_enables_image_task_for_plain_notice(self) -> None:
        source = "公告\n请查看详情"
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(
                source,
                Path(temp_dir),
                name="explicit-banner",
                design_plan={
                    "media_policy": {
                        "image_generation_mode": "seedream_5_pro_banner_plus_native_card",
                    }
                },
            )
            spec = json.loads(
                (Path(temp_dir) / "explicit-banner" / "explicit-banner.spec.json").read_text(encoding="utf-8")
            )

        self.assertEqual(report["status"], "needs_image")
        self.assertTrue(report["doubao"]["image_required"])
        self.assertEqual(spec["image_generation_mode"], "seedream_5_pro_banner_plus_native_card")
        self.assertEqual(spec["hero"]["text_in_image"], "seedream_5_pro_banner_selected_text_and_layout")

    def test_layout_proposals_and_detected_url_are_local_and_source_backed(self) -> None:
        source = "作品案例\n点击查看作品：https://example.com/work"
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(source, Path(temp_dir), name="proposals", no_image=True)
            bundle = Path(temp_dir) / "proposals"
            card = json.loads((bundle / "proposals.card").read_text(encoding="utf-8"))

        self.assertEqual(
            {item["id"] for item in report["proposals"]},
            {"banner-led", "infographic-led", "text-led"},
        )
        self.assertEqual(
            {item["image_mode"] for item in report["proposals"]},
            {"seedream_5_pro_direct_full_card", "seedream_5_pro_banner_plus_native_card"},
        )
        self.assertEqual(report["detected_urls"][0]["url"], "https://example.com/work")
        self.assertTrue(
            any(
                item.get("tag") == "button"
                and any(
                    behavior.get("default_url") == "https://example.com/work"
                    for behavior in item.get("behaviors", [])
                    if isinstance(behavior, dict)
                )
                for item in card["body"]["elements"]
                if isinstance(item, dict)
            )
        )

    def test_passive_url_is_reported_but_not_promoted_to_button(self) -> None:
        source = "参考资料：https://example.com/reference"
        with tempfile.TemporaryDirectory() as temp_dir:
            report = run_pipeline(source, Path(temp_dir), name="passive", no_image=True)
            card = json.loads(
                (Path(temp_dir) / "passive" / "passive.card").read_text(encoding="utf-8")
            )

        self.assertEqual(report["detected_urls"][0]["url"], "https://example.com/reference")
        self.assertFalse(report["detected_urls"][0]["button_eligible"])
        self.assertFalse(
            any(
                item.get("tag") == "button"
                for item in card["body"]["elements"]
                if isinstance(item, dict)
            )
        )

    def test_legacy_image_generation_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_pipeline(
                COPY,
                Path(tempfile.mkdtemp()),
                name="legacy-mode",
                design_plan={"media_policy": {"need_hero": True, "image_generation_mode": "legacy"}},
            )

    def test_style_catalog_auto_selects_without_changing_default_pointer(self) -> None:
        catalog_path = ROOT / "presets" / "image-style-index.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        style_ids = {item["id"] for item in catalog["styles"]}

        self.assertIsNone(catalog["default"])
        self.assertTrue(catalog["selection_policy"]["auto_select"])
        self.assertTrue(catalog["selection_policy"]["explicit_style_wins"])
        self.assertTrue(catalog["selection_policy"]["ask_before_switching"])
        self.assertTrue(catalog["selection_policy"]["style_is_not_layout"])
        self.assertIn("blueprint-timeline", style_ids)
        self.assertIn("xhs-editorial-magazine", style_ids)
        self.assertTrue((ROOT / "references" / "image-style-catalog.md").is_file())


if __name__ == "__main__":
    unittest.main()
