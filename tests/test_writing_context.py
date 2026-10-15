from waypoint.communities import prepare_variants, save_plan
from waypoint.context import build_context, prompt_for
from waypoint.contracts import TaskSpec
from test_repository import make


def test_peer_drafts_are_current_same_group_and_excluded_from_translation(tmp_path):
    repo, brand, group = make(tmp_path)
    save_plan(repo, group, [{'name': 'r/test', 'variants': 3, 'rules_zh': '',
                           'culture_zh': '', 'confirmed': True}], 0)
    first, second, third = prepare_variants(repo, group)
    current = repo.save_revision(first['id'], 'english', 'A distinctive opening.', expected_epoch=0)
    repo.save_revision(third['id'], 'english', 'Outdated wording.', expected_epoch=0)
    repo.update_task(third['id'], {'raw_input': '新思路'})
    other_brand = repo.create_project('Other brand')
    other = repo.create_task(TaskSpec(project_id=other_brand, kind='comment', raw_input='另一品牌'))
    repo.save_revision(other, 'english', 'Private unrelated product.', expected_epoch=0)
    context = build_context(repo, second['id'], 'english')
    assert context['peer_drafts'] == [{'title': current['title'], 'body': current['body']}]
    assert 'Private unrelated product.' not in prompt_for(context)
    assert 'Outdated wording.' not in prompt_for(context)
    repo.set_task_state(first['id'], status='completed')
    repo.abandon_variant(first['id'])
    assert build_context(repo, second['id'], 'english')['peer_drafts'] == []
    assert build_context(repo, second['id'], 'backtranslation')['peer_drafts'] == []


def test_translation_request_contains_only_exact_english_and_applicable_rules():
    snapshot = {'target_stage': 'backtranslation', 'rules': [],
                'base': {'id': 'exact', 'title': 'A question', 'body': 'I liked it, but not the weight.'},
                'raw_input': '旧中文说非常喜欢重量', 'checkpoint': {'body': '旧节点里的私人内容'},
                'materials': [{'text': 'Private source text'}],
                'opinions': [{'raw_text': '再创作一句'}], 'peer_drafts': [{'body': 'Another story.'}]}
    prompt = prompt_for(snapshot)
    assert 'I liked it, but not the weight.' in prompt
    for unwanted in ('旧中文说非常喜欢重量', '旧节点里的私人内容', 'Private source text', '再创作一句', 'Another story.'):
        assert unwanted not in prompt


def test_creative_prompt_explicitly_separates_simulated_voice_and_fact_evidence():
    snapshot = {'target_stage': 'english', 'kind': 'comment', 'rules': [],
                'raw_input': '温和回复这个建议', 'materials': [], 'base': None}
    prompt = prompt_for(snapshot)
    assert '模拟人设' in prompt
    assert '产品事实' in prompt
    assert '不得编造产品使用经历、冒充原作者或自然消费者' not in prompt
    assert '有品牌相关性时如实说明' not in prompt
    assert 'note_zh' in prompt and 'questions' in prompt


def test_generation_keeps_current_evidence_without_replaying_old_stage_feedback(tmp_path):
    repo, brand, task = make(tmp_path)
    repo.update_task(task, {'name': '温和但有明确态度的回复'})
    old = repo.save_revision(task, 'chinese', '旧中文建议换一个角度', expected_epoch=1,
                             note_zh='过时的草稿核验警告')
    current = repo.save_revision(task, 'english', 'The feature fits this particular need.', expected_epoch=1,
                                 note_zh='旧版客服身份解释', questions=['过时的问题'])
    context = build_context(repo, task, 'english')
    prompt = prompt_for(context)
    assert '温和但有明确态度的回复' in prompt
    assert current['body'] in prompt
    for outdated in (old['body'], '过时的草稿核验警告', '旧版客服身份解释', '过时的问题'):
        assert outdated not in prompt
    # The evidence snapshot must still preserve original revision history.
    assert context['stages']['chinese']['body'] == old['body']
    assert context['base']['note_zh'] == '旧版客服身份解释'


def test_fact_research_sees_latest_opinion_exact_draft_and_comment_target(tmp_path):
    import asyncio, json
    from waypoint.fact_research import research_claims
    from waypoint.contracts import Opinion
    repo, brand, task = make(tmp_path)
    parent_task = repo.create_task(TaskSpec(project_id=brand, raw_input='自己的原帖'))
    parent = repo.save_revision(parent_task, 'english', 'Actual original post need.', expected_epoch=0)
    comment = repo.create_task(TaskSpec(project_id=brand, kind='comment', comment_kind='own',
                                       parent_revision_id=parent['id'], raw_input='围绕旧型号回复'))
    base = repo.save_revision(comment, 'english', 'An earlier response about Model A.', expected_epoch=0)
    op = Opinion(task_id=comment, stage='english', base_revision_id=base['id'],
                 raw_text='改为 Model B，核对美国版本，不谈价格')
    repo.add_opinion(op)
    context = build_context(repo, comment, 'english', base['id'])
    class ResearchProvider:
        supports_web_research = True
        async def generate(self, request):
            self.request = request
            yield {'kind': 'completed', 'text': json.dumps({'summary_zh': '未找到独立来源', 'claims': []}),
                   'web_sources': []}
    provider = ResearchProvider()
    class ResearchEngine:
        async def select_provider(self, role):
            return provider, {'model': 'test', 'effort': 'high'}
    asyncio.run(research_claims(ResearchEngine(), context))
    prompt = provider.request['prompt']
    assert op.raw_text in prompt
    assert base['body'] in prompt
    assert parent['body'] in prompt
    assert '不谈价格' in prompt
