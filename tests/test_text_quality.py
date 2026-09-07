import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from text_quality import concise, hierarchy, prepare_blocks


class TextQualityTests(unittest.TestCase):
    def test_visual_evidence_missing_corrupt_or_changed_is_not_pass(self):
        import tempfile
        from review_evidence import current, screenshot
        from media_fixtures import write_test_png
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'preview.png'
            write_test_png(p)
            evidence = {'surface':'local_preview','desktop':screenshot(p),'mobile':screenshot(p)}
            self.assertTrue(current(evidence))
            self.assertFalse(current({'surface':'local_preview','desktop':'bad'}))
            self.assertFalse(current({'surface':'local_preview'}))
            p.write_bytes(b'not a png')
            self.assertFalse(current(evidence))

    def test_update_unavailable_target_never_creates_duplicate(self):
        import tempfile, json
        from unittest.mock import patch
        import feishu_cli as cli
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'demo.card'
            card={'schema':'2.0','body':{'elements':[]}}
            p.write_text(json.dumps(card))
            with patch.object(cli,'_path_from_user',return_value=p), patch.object(cli,'_card_from_path',return_value=(p,card,{'ok':True})), patch.object(cli,'_image_readiness_gate',return_value=None), patch.object(cli,'_relative_for_cli',return_value='demo.card'), patch.object(cli,'_run_byted_cli',return_value=(1,{},'unavailable')) as run:
                result=cli.push_cardkit(str(p),name='demo',template_id='target',confirm=True)
            self.assertEqual(result['status'],'update_target_unavailable')
            self.assertEqual(run.call_count,1)
            self.assertIn('get',run.call_args.args[0])

    def test_numbered_steps_and_url_are_preserved(self):
        value = '1. 上传文件\n  2. 核对成绩\n链接：https://example.com/a;b'
        rendered = hierarchy(value)
        self.assertIn('1. 上传文件', rendered)
        self.assertIn('  2. 核对成绩', rendered)
        self.assertIn('https://example.com/a;b', rendered)

    def test_long_indivisible_sentence_is_not_silently_truncated(self):
        value = '先核对评分标准和适用条件再逐项提供反馈' * 15
        self.assertEqual(concise(value, 60), value)
        self.assertNotIn('…', concise(value, 60))

    def test_complete_sentence_and_source_preserved(self):
        value = '先核对标准。' + '在各项条件满足后再逐项提供反馈' * 20 + '。'
        self.assertEqual(concise(value, 60), '先核对标准。')

    def test_notes_removed_long_facts_use_single_column(self):
        blocks = [{'type':'section','body':'反馈更及时。\n按钮文案：查看方案（暂不跳转）'},
                  {'type':'metrics','items':[{'label':'时间','value':'9月17日启动培训，面向各学科教师统一讲解并现场演示完整流程。'}]}]
        result = prepare_blocks(blocks)
        self.assertNotIn('按钮文案',result[0]['body'])
        self.assertIn('按钮文案',blocks[0]['body'])
        self.assertEqual(result[1]['type'],'highlight')

    def test_update_keeps_target_and_uses_current_version(self):
        import tempfile, json
        from unittest.mock import patch
        import feishu_cli as cli
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'card.card'
            card={'schema':'2.0','body':{'elements':[]}}
            p.write_text(json.dumps(card))
            calls=[]
            def run(args, **kwargs):
                calls.append(args)
                if 'get' in args:
                    return 0, {'data':{'template':{'draft_version_id':'v1'},'card_json':card}}, ''
                if 'list' in args:
                    return 0, {'data':[{'template_id':'target','name':'demo'}]}, ''
                return 0, {'ok':True}, ''
            with patch.object(cli,'_path_from_user',return_value=p), patch.object(cli,'_card_from_path',return_value=(p,card,{'ok':True})), patch.object(cli,'_image_readiness_gate',return_value=None), patch.object(cli,'_relative_for_cli',return_value='card.card'), patch.object(cli,'_run_byted_cli',side_effect=run):
                result=cli.push_cardkit(str(p),name='demo',template_id='target',confirm=True)
            self.assertTrue(result['ok'])
            self.assertEqual(result['template_id'],'target')
            self.assertFalse(result['editor_edit_save_verified'])
            self.assertFalse(any('import' in c for c in calls))
            update=next(c for c in calls if 'update' in c)
            self.assertIn('--saved-version-id',update)

if __name__ == '__main__':
    unittest.main()
