"""ST-007：使用虚构测试数据验证四科题型样例与按来源判分（题组/公式/图表/阅读/短答归一化）。"""


def make_source(client, auth, subject, title='虚构测试数据：题型样例题源'):
    response = client.post('/api/admin/sources', headers=auth, json={
        'title': title, 'subject': subject, 'rights_status': 'personal_use_reviewed', 'verified': True,
    })
    assert response.status_code == 201
    return response.json()['id']


def publish_question(client, auth, source_id, **overrides):
    body = {
        'source_document_id': source_id, 'stem': '虚构测试数据：1+1=?', 'kind': 'single_choice',
        'options': ['A. 1', 'B. 2'], 'correct_answer': 'B',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2,
    }
    body.update(overrides)
    created = client.post('/api/admin/questions', headers=auth, json=body)
    assert created.status_code == 201
    version_id = created.json()['id']
    assert client.post(f'/api/admin/questions/{version_id}/review', headers=auth).status_code == 200
    assert client.post(f'/api/admin/questions/{version_id}/publish', headers=auth).status_code == 200
    return version_id


def practice_next(client, auth, subject):
    response = client.get(f'/api/practice/next?subject={subject}', headers=auth)
    assert response.status_code == 200
    return response.json()


def submit_answer(client, auth, item, answer, key):
    response = client.post('/api/practice/attempts', headers=auth, json={
        'client_attempt_id': key, 'exposure_id': item['exposure_id'], 'answer': answer,
    })
    assert response.status_code == 201
    return response.json()


def test_math_formula_and_short_answer_normalization(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'math', '虚构测试数据：数学公式题源')
    first = publish_question(client, admin_auth, source,
                             stem='虚构测试数据：解方程 x^2+2x+1=0，写出 x 的值', kind='short_answer',
                             options=[], correct_answer='x=-1', knowledge_ids=['math.arithmetic'], max_points=2)
    second = publish_question(client, admin_auth, source,
                              stem='虚构测试数据：解方程 (x+1)^2=0，写出 x 的值', kind='short_answer',
                              options=[], correct_answer='x=-1', knowledge_ids=['math.arithmetic'], max_points=2)
    item = practice_next(client, student_auth, 'math')
    assert item['question_version_id'] == first
    assert item['kind'] == 'short_answer'
    assert item['group_context'] is None
    attempt = submit_answer(client, student_auth, item, '  X=-1  ', 'sa-normalized')
    assert attempt['earned_points'] == 2
    assert attempt['scoring_origin'] == 'reviewed_answer_key'
    second_item = practice_next(client, student_auth, 'math')
    assert second_item['question_version_id'] == second
    spaced = submit_answer(client, student_auth, second_item, 'x = - 1', 'sa-inner-spaces')
    assert spaced['earned_points'] == 0
    assert spaced['scoring_origin'] == 'reviewed_answer_key'


def test_chinese_reading_group_context(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'chinese', '虚构测试数据：语文阅读题源')
    passage = '虚构测试数据：阅读下列文段，回答问题。白日依山尽，黄河入海流。'
    first = publish_question(client, admin_auth, source, stem='虚构测试数据：“白日依山尽”的下一句是？',
                             options=['A. 黄河入海流', 'B. 大江东去'], correct_answer='A',
                             knowledge_ids=['chinese.reading'], max_points=2, group_context=passage)
    second = publish_question(client, admin_auth, source, stem='虚构测试数据：文段中“入海流”写的是哪条河？',
                              options=['A. 长江', 'B. 黄河'], correct_answer='B',
                              knowledge_ids=['chinese.reading'], max_points=2, group_context=passage)
    third = publish_question(client, admin_auth, source, stem='虚构测试数据：“依”字注音正确的是？',
                             options=['A. yī', 'B. yí'], correct_answer='A',
                             knowledge_ids=['chinese.pinyin'], max_points=2)
    contexts = {}
    for _ in range(3):
        item = practice_next(client, student_auth, 'chinese')
        contexts[item['question_version_id']] = item['group_context']
    assert contexts[first] == passage
    assert contexts[second] == passage
    assert contexts[third] is None


def test_physics_chart_in_stem_single_choice(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'physics', '虚构测试数据：物理图表题源')
    version = publish_question(client, admin_auth, source,
                               stem='虚构测试数据：如图（示意），物体受力 F=10N 沿水平方向……',
                               options=['A. 10N', 'B. 20N'], correct_answer='A',
                               knowledge_ids=['physics.mechanics'], max_points=2)
    item = practice_next(client, student_auth, 'physics')
    assert item['question_version_id'] == version
    assert item['kind'] == 'single_choice'
    attempt = submit_answer(client, student_auth, item, 'A', 'physics-chart')
    assert attempt['earned_points'] == 2
    assert attempt['scoring_origin'] == 'reviewed_answer_key'


def test_subjective_flow_math_solution(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'math', '虚构测试数据：数学主观题源')
    reference = '先算乘法：5×2=10；再算加法：3+10=13'
    first = publish_question(client, admin_auth, source, stem='虚构测试数据：解答并写出过程：计算 3+5×2',
                             kind='subjective', options=[], correct_answer=reference,
                             knowledge_ids=['math.arithmetic'], max_points=3)
    second = publish_question(client, admin_auth, source, stem='虚构测试数据：解答并写出过程：计算 2+4×3',
                              kind='subjective', options=[], correct_answer='先算乘法：4×3=12；再算加法：2+12=14',
                              knowledge_ids=['math.arithmetic'], max_points=3)
    item = practice_next(client, student_auth, 'math')
    assert item['question_version_id'] == first
    assert item['kind'] == 'subjective'
    attempt = submit_answer(client, student_auth, item, '3+5×2=13', 'subjective-solution')
    assert attempt['earned_points'] is None
    assert attempt['scoring_origin'] == 'ungraded_subjective'
    assert attempt['evaluation_valid_unseen'] is False
    profile_before = client.get('/api/guidance/profile?subject=math', headers=student_auth).json()
    assert profile_before['knowledge'] == []

    reference_response = client.get(f"/api/practice/attempts/{attempt['id']}/reference", headers=student_auth)
    assert reference_response.status_code == 200
    assert reference_response.json() == {'reference_answer': reference, 'max_points': 3}

    assessed = client.post(f"/api/practice/attempts/{attempt['id']}/self-assessment", headers=student_auth,
                           json={'self_earned_points': 2})
    assert assessed.status_code == 201
    assert set(assessed.json()) == {'id', 'attempt_id', 'self_earned_points', 'max_points', 'scoring_origin'}
    assert assessed.json()['attempt_id'] == attempt['id']
    assert assessed.json()['self_earned_points'] == 2
    assert assessed.json()['max_points'] == 3
    assert assessed.json()['scoring_origin'] == 'self_assessment'
    repeat = client.post(f"/api/practice/attempts/{attempt['id']}/self-assessment", headers=student_auth,
                         json={'self_earned_points': 2})
    assert repeat.status_code == 409
    assert repeat.json()['detail'] == 'SELF_ASSESSMENT_ALREADY_RECORDED'

    second_item = practice_next(client, student_auth, 'math')
    assert second_item['question_version_id'] == second
    second_attempt = submit_answer(client, student_auth, second_item, '2+4×3=14', 'subjective-overflow')
    overflow = client.post(f"/api/practice/attempts/{second_attempt['id']}/self-assessment", headers=student_auth,
                           json={'self_earned_points': 99})
    assert overflow.status_code == 422

    # 自评为非客观证据：主观作答与其自评都不进 profile 的 math.arithmetic 样本。
    profile_after = client.get('/api/guidance/profile?subject=math', headers=student_auth).json()
    assert profile_after['knowledge'] == []


def test_self_assessment_access_rules(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'math', '虚构测试数据：自评访问规则题源')
    publish_question(client, admin_auth, source, stem='虚构测试数据：解答并写出过程：计算 1+2×3',
                     kind='subjective', options=[], correct_answer='先算乘法：2×3=6；再算加法：1+6=7',
                     knowledge_ids=['math.arithmetic'], max_points=3)
    publish_question(client, admin_auth, source, stem='虚构测试数据：1+2×3=?',
                     options=['A. 6', 'B. 7'], correct_answer='B',
                     knowledge_ids=['math.arithmetic'], max_points=2)
    subjective_item = practice_next(client, student_auth, 'math')
    assert subjective_item['kind'] == 'subjective'
    subjective_attempt = submit_answer(client, student_auth, subjective_item, '1+2×3=7', 'rules-subjective')
    subjective_id = subjective_attempt['id']
    assert client.get(f'/api/practice/attempts/{subjective_id}/reference', headers=student_auth).status_code == 200
    assert client.post(f'/api/practice/attempts/{subjective_id}/self-assessment', headers=student_auth,
                       json={'self_earned_points': 3}).status_code == 201

    objective_item = practice_next(client, student_auth, 'math')
    assert objective_item['kind'] == 'single_choice'
    objective_id = submit_answer(client, student_auth, objective_item, 'B', 'rules-objective')['id']

    reference_conflict = client.get(f'/api/practice/attempts/{objective_id}/reference', headers=student_auth)
    assert reference_conflict.status_code == 409
    assert reference_conflict.json()['detail'] == 'REFERENCE_NOT_APPLICABLE'
    assessment_conflict = client.post(f'/api/practice/attempts/{objective_id}/self-assessment', headers=student_auth,
                                      json={'self_earned_points': 1})
    assert assessment_conflict.status_code == 409
    assert assessment_conflict.json()['detail'] == 'SELF_ASSESSMENT_NOT_APPLICABLE'

    assert client.get('/api/practice/attempts/missing-attempt/reference', headers=student_auth).status_code == 404
    assert client.post('/api/practice/attempts/missing-attempt/self-assessment', headers=student_auth,
                       json={'self_earned_points': 1}).status_code == 404

    assert client.get('/api/practice/attempts/missing-attempt/reference').status_code == 401
    assert client.post('/api/practice/attempts/missing-attempt/self-assessment',
                       json={'self_earned_points': 1}).status_code == 401
    assert client.get('/api/practice/attempts?subject=math').status_code == 401


def test_question_input_validation_for_kinds(client, auth):
    source = make_source(client, auth, 'math', '虚构测试数据：题型校验题源')
    base = {'source_document_id': source, 'knowledge_ids': ['math.arithmetic'], 'max_points': 2}
    subjective_with_options = client.post('/api/admin/questions', headers=auth, json={
        **base, 'stem': '虚构测试数据：主观题不得带选项', 'kind': 'subjective',
        'options': ['A. 占位'], 'correct_answer': '虚构测试数据：参考解答'})
    assert subjective_with_options.status_code == 422
    choice_without_options = client.post('/api/admin/questions', headers=auth, json={
        **base, 'stem': '虚构测试数据：单选题缺选项', 'kind': 'single_choice',
        'options': [], 'correct_answer': 'A'})
    assert choice_without_options.status_code == 422
    subjective_without_options = client.post('/api/admin/questions', headers=auth, json={
        **base, 'stem': '虚构测试数据：主观题空选项', 'kind': 'subjective',
        'options': [], 'correct_answer': '虚构测试数据：参考解答'})
    assert subjective_without_options.status_code == 201
    unknown_kind = client.post('/api/admin/questions', headers=auth, json={
        **base, 'stem': '虚构测试数据：未知题型', 'kind': 'essay_magic',
        'options': [], 'correct_answer': '虚构测试数据：参考解答'})
    assert unknown_kind.status_code == 422
    oversized_context = client.post('/api/admin/questions', headers=auth, json={
        **base, 'stem': '虚构测试数据：题组文段超长', 'kind': 'single_choice',
        'options': ['A. 1', 'B. 2'], 'correct_answer': 'A', 'group_context': '虚' * 20001})
    assert oversized_context.status_code == 422


def test_group_context_revision(client, admin_auth, student_auth):
    source = make_source(client, admin_auth, 'math', '虚构测试数据：题组修订题源')
    v1 = publish_question(client, admin_auth, source, stem='虚构测试数据：文段A下的第一题：1+1=?',
                          options=['A. 2', 'B. 3'], correct_answer='A',
                          knowledge_ids=['math.arithmetic'], max_points=2, group_context='虚构测试数据：文段A')
    original_item = practice_next(client, student_auth, 'math')
    assert original_item['question_version_id'] == v1
    assert original_item['group_context'] == '虚构测试数据：文段A'
    revision = client.post(f'/api/admin/questions/{v1}/revisions', headers=admin_auth, json={
        'source_document_id': source, 'stem': '虚构测试数据：文段B下的第一题：2+2=?',
        'kind': 'single_choice', 'options': ['A. 4', 'B. 5'], 'correct_answer': 'A',
        'knowledge_ids': ['math.arithmetic'], 'max_points': 2, 'group_context': '虚构测试数据：文段B'})
    assert revision.status_code == 201
    v2 = revision.json()['id']
    assert client.post(f'/api/admin/questions/{v2}/review', headers=admin_auth).status_code == 200
    assert client.post(f'/api/admin/questions/{v2}/publish', headers=admin_auth).status_code == 200
    item = practice_next(client, student_auth, 'math')
    assert item['question_version_id'] == v2
    assert item['group_context'] == '虚构测试数据：文段B'
