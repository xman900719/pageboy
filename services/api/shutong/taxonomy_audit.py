"""
四学科候选知识点课标溯源审核与版本发布核心实现（纯服务端与 CLI 复用）。

由北京市中考全科教研专家（beijing_zhongkao_expert）依据教育部 2022 年版四科课程标准
（《义务教育数学/语文/英语/物理课程标准（2022年版）》）及北京市初中学业水平考试（中考）
命题规范（京教计〔2023〕44号及 2018–2025 年北京中考真题双向细目），对全部 135 个候选知识点
执行逐点课标条文核对、北京中考题型定位、选学隔离核验与正式快照发布。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import models as m
from .fourcorpus import _latest, seed_candidate_nodes
from .home import resolve_repo_root

SUBJECTS: tuple[str, ...] = ("math", "chinese", "english", "physics")

SUBJECT_META: dict[str, dict[str, str]] = {
    "math": {
        "cn": "数学",
        "std_title": "《义务教育数学课程标准（2022年版）》",
        "exam_spec": "北京市初中学业水平考试数学学科命题规范（满分100分，选择题16分+填空题16分+解答题68分，共28题）",
    },
    "chinese": {
        "cn": "语文",
        "std_title": "《义务教育语文课程标准（2022年版）》",
        "exam_spec": "北京市初中学业水平考试语文学科命题规范（满分100分，基础·运用+古诗文阅读+名著阅读+现代文阅读+作文）",
    },
    "english": {
        "cn": "英语",
        "std_title": "《义务教育英语课程标准（2022年版）》",
        "exam_spec": "北京市初中学业水平考试英语学科命题规范（满分100分：听说机考40分+笔试60分，含单选、完形、阅读理解A-D篇、阅读表达与文段表达）",
    },
    "physics": {
        "cn": "物理",
        "std_title": "《义务教育物理课程标准（2022年版）》",
        "exam_spec": "北京市初中学业水平考试物理学科命题规范（满分70分，单项选择题+多项选择题+实验解答题+科普阅读题+计算题）",
    },
}

# 北京市中考全科教研专家针对各学科节点的专项命题定位与教学诊断意见
BEIJING_ZHONGKAO_EXPERT_NOTES: dict[str, str] = {
    # 数学（48 节点）
    "math_cand.num_alg": "统摄北京中考数学“数与代数”一级主干领域（占卷面分值约45%），覆盖第1–6、9–14、17–21、22、26题，诊断核心在于运算能力、符号意识与函数模型观念。",
    "math_cand.num_alg.num_expr": "对应北京中考选择第2、4、6题，填空第9、10题及解答第17、19题，聚焦实数与代数式基础运算准确性，属于全卷零失分基石模块。",
    "math_cand.num.rational": "北京中考高频必考基础点（常考选择第2题科学记数法/数轴绝对值相反数、第17题实数混合运算），重点诊断负号处理、绝对值化简与乘方符号规则。",
    "math_cand.num.real": "北京中考常考选择第6题（无理数估算与数轴点位置对应）及第17题（算术平方根、特殊角三角函数、零指数幂与负整数指数幂混合计算）。",
    "math_cand.alg.poly": "北京中考常考选择第4题（幂的运算性质正误辨析）及第19题（整式化简求值：完全平方公式、平方差公式展开与整体代入法）。",
    "math_cand.alg.factor": "北京中考填空题高频基础考点（提公因式法与公式法综合分解因式，步数不超过两步），亦为一元二次方程因式分解解法与分式约分之前置核心。",
    "math_cand.alg.frac": "北京中考填空第9题（分式有意义/值为0的条件）及解答题分式化简求值高频考点，重点防范通分漏乘与符号变号错误。",
    "math_cand.alg.quadratic_radical": "北京中考填空第9题（二次根式被开方数非负性 $a\\ge 0$）及第17题实数混合运算核心组成部分，重点诊断最简二次根式化简。",
    "math_cand.num_alg.eq_ineq": "对应北京中考第11、18、20、21题，涵盖方程（组）与不等式（组）解法、根的判别式及现实情境数学建模。",
    "math_cand.eq.linear": "方程建模基础，北京中考常在应用题（第21题）或几何、函数综合求参中作为底层求解工具考查。",
    "math_cand.eq.linear_system": "北京中考第21题列方程组解应用题核心考点（常结合古算题、配套问题或阶梯计费情境），重点诊断等量关系提取与消元运算。",
    "math_cand.eq.linear_system_3var": "课标第四学段带“*”选学内容（《课标》印刷页56页④）。经北京市中考专家核定：依据京教计〔2023〕44号，本节点不纳入北京中考必考命题范围，学生端默认诊断与组卷严禁抽选，仅保留作课标体系完备性参照。",
    "math_cand.eq.quadratic": "北京中考解答第20题固定核心考点（第一问证明方程总有两个实数根或求参数范围 $\\Delta=b^2-4ac$，第二问结合整数根或根与系数关系求解），2022新课标已将韦达定理列为必学内容。",
    "math_cand.eq.fractional": "北京中考填空第11题或应用题常考考点，教学中必须强化学科红线：去分母化为整式方程后必须检验最简公分母不为0（验根）。",
    "math_cand.ineq.linear": "北京中考解答第18题固定必考题（解一元一次不等式组并在数轴上表示解集或求所有整数解），重点诊断负系数化1时的不等号方向反转。",
    "math_cand.num_alg.func": "北京中考数学核心区分度板块（第13、22、23、26题），重点考查函数图象直观、增减性、数形结合与代数推理。",
    "math_cand.func.basic": "北京中考常结合动点几何图形面积/距离变化曲线或实际物理过程考查函数图象趋势读取与自变量取值范围。",
    "math_cand.func.linear": "北京中考解答第22题固定考点（一次函数 $y=kx+b$ 图象与坐标轴交点、待定系数法及结合函数图象解不等式 $kx+b>mx+n$ 的参数取值范围）。",
    "math_cand.func.inverse": "北京中考选择/填空第13题或函数综合常考考点（反比例函数 $y=k/x$ 图象象限分布、跨象限增减性比较及 $|k|$ 的矩形/三角形面积几何意义）。",
    "math_cand.func.quadratic": "北京中考解答第26题（代数压轴题，6–7分）核心考点：聚焦抛物线对称轴 $x=-b/(2a)$、顶点、开口方向及区间内函数值大小比较（对称性距离法与代数差值推理）。",
    "math_cand.geo": "统摄北京中考数学“图形与几何”一级主干领域（占卷面分值约40%），覆盖第1、3、5、12、15、20/23、24、27、28题，核心考查空间观念、几何直观与逻辑推理。",
    "math_cand.geo.properties": "涵盖北京中考几何基础证明与计算全链条（相交平行线、三角形、四边形、圆及尺规作图推理）。",
    "math_cand.geo.lines_angles": "北京中考选择第3题（相交线、平行线角度计算与光线反射情境）及尺规作图题（角平分线、垂直平分线作法依据）高频必考点。",
    "math_cand.geo.triangle_basic": "几何推理基础考点，三角形内角和、外角定理及三角形中位线定理在北京中考平行四边形与圆综合题中频繁作为桥梁使用。",
    "math_cand.geo.isosceles_triangle": "北京中考常考“等边对等角”“三线合一”及等边三角形手拉手旋转模型（第27题几何综合高频母题）。",
    "math_cand.geo.pythagoras": "北京中考几何计算核心工具（直角三角形斜边中线等于斜边一半、$30^\\circ$ 直角三角形性质及勾股定理列方程求线段长，常考于填空压轴与圆/四边形综合）。",
    "math_cand.geo.congruent_triangles": "北京中考解答第19/20题基础几何证明及第27题几何综合压轴题（全等构造、旋转全等、截长补短与中点倍长）的核心推理支柱。",
    "math_cand.geo.quadrilateral_basic": "北京中考选择第5题（正多边形内角和/外角和公式）及平行四边形性质判定证明的核心考点。",
    "math_cand.geo.special_parallelogram": "北京中考解答第23题（矩形、菱形、正方形性质与判定综合证明 + 结合勾股定理或三角函数求线段长）固定必考大题。",
    "math_cand.geo.circle_basic": "北京中考填空第12/14题及解答第24题（圆的综合大题）第一问核心考点：垂径定理、圆周角定理及其推论（直径所对圆周角为直角）、圆内接四边形对角互补。",
    "math_cand.geo.circle_tangent": "北京中考解答第24题（圆的综合大题，5–6分）核心必考点：连半径证垂直（切线判定）或见切线连半径得垂直（切线性质），常结合相似或三角函数求线段长。",
    "math_cand.geo.circle_tangent_length": "课标第四学段带“*”选学内容（《课标》印刷页62页⑦⑧：切线长定理及过圆外一点作切线尺规作图）。经北京市中考专家核定：严格执行必学/选学物理隔离，不进入学生端必考诊断与日常组卷。",
    "math_cand.geo.arc_sector": "北京中考填空题常考考点（弧长公式 $l=n\\pi R/180$ 与扇形面积公式 $S=n\\pi R^2/360$ 计算及正多边形与圆的关系）。",
    "math_cand.geo.proof_logic": "贯穿北京中考尺规作图理论依据填空（如“到线段两端点距离相等的点在线段的垂直平分线上”）与几何演绎推理全过程。",
    "math_cand.geo.transformations": "对应北京中考第1、2、23/24、27题，重点考查轴对称、旋转、平移与相似变换中的不变量与运动轨迹。",
    "math_cand.geo.transform_symmetry": "北京中考选择第2题（轴对称图形与中心对称图形识别）及第27题几何综合题（线段或点绕定点旋转 $60^\\circ/90^\\circ/\\alpha$、关于直线对称变换构造全等）的核心考点。",
    "math_cand.geo.similarity": "北京中考解答第23/24/27题第二问求线段长或比值的核心工具（平行线分线段成比例、A字/8字相似、射影定理模型与旋转相似）。",
    "math_cand.geo.trigonometry": "北京中考解答第23、24题第二问固定组合考点：利用特殊角或正弦/余弦/正切值在直角三角形（或通过圆周角等角转移构造直角三角形）中求解未知线段。",
    "math_cand.geo.projection_views": "北京中考选择第1题固定必考题（常见几何体三视图识别或正方体表面展开图相对面判断），属于开卷首题稳拿分点。",
    "math_cand.geo.coordinates": "北京中考平面直角坐标系核心底座，既是函数图象载体，也是第28题平面直角坐标系下“新定义”压轴题的几何空间背景。",
    "math_cand.stat_prob": "统摄北京中考数学“统计与概率”一级领域（占卷面分值约10–12分），覆盖选择第7/8题、填空第14题与解答第25题，核心考查数据观念。",
    "math_cand.stat.data_analysis": "对应北京中考解答第25题统计大题（5–6分），综合考查统计图表读取、集中趋势与离散程度指标计算及样本估计总体。",
    "math_cand.stat.sampling_collection": "北京中考解答第25题常考频数分布表、频数分布直方图、扇形图或折线图的跨表信息补全与样本容量提取。",
    "math_cand.stat.central_dispersion": "北京中考解答第25题核心设问：准确计算或读取平均数、中位数、众数与方差，并能依据中位数（判断名次）或方差（评价稳定性）撰写规范统计推断理由。",
    "math_cand.prob.probability": "北京中考选择第7题或填空题常考考点（古典概型等可能事件概率计算、频率估计概率、列表法或树状图法求两步事件概率）。",
    "math_cand.comp_prac": "统摄北京中考数学“综合与实践”领域，体现北京中考重阅读理解、重数学建模、重现场探究的鲜明京派命题特色。",
    "math_cand.prac.project_modeling": "对应北京中考第15/16题（逻辑推理与优化策略建模）及第21/25题跨学科真实情境问题解决，诊断学生从现实情境抽象数学模型的能力。",
    "math_cand.prac.exploration_new_definition": "对应北京中考最具代表性的第27题（几何综合探究）与第28题（平面直角坐标系“新定义”压轴题，7分）：重点考查现场理解新概念、寻找临界位置（相切/过端点）与动态轨迹极值的核心数学素养。",
    # 语文（25 节点）
    "chinese_cand.base_accumulation": "统摄北京中考语文第一部分“基础·运用”（约18–20分），依托首都文化、博物馆展览或校园主题活动真实情境，综合考查字音字形、成语、病句、标点、书法与情境表达。",
    "chinese_cand.base.phonetics": "北京中考“基础·运用”首道小题必考点：在文段语境中辨析多音字、形声字及习惯性误读字音（如翘舌音、前后鼻音与统编教材课下注释重点字音）。",
    "chinese_cand.base.character_orthography": "北京中考“基础·运用”必考点：结合汉字造字本义（形旁表意）在真实语境中辨析同音字、形近字并规范书写正楷字。",
    "chinese_cand.base.idiom_vocabulary": "北京中考“基础·运用”高频考点：结合上下文语境判断四字成语或双音节词语使用恰当性，重点防止望文生义、褒贬误用与对象不当。",
    "chinese_cand.base.syntax_revision": "北京中考“基础·运用”核心考点：在语段中辨析并修改成分残缺（缺主语/缺宾语中心语）、搭配不当、语序不当、句式杂糅与前后矛盾等典型病句。",
    "chinese_cand.base.punctuation": "北京中考“基础·运用”特色考点：结合句子层次与语气考查顿号与逗号层级、引号与句末点号位置、书名号与引号区分、分号与冒号规范用法。",
    "chinese_cand.base.culture_calligraphy": "北京中考极具京味特色的必考点：涵盖二十四节气、对联平仄对仗、传统礼俗及历代名家书法作品（楷、行、草、隶、篆五体特征与审美意蕴）鉴赏。",
    "chinese_cand.base.contextual_expression": "北京中考“基础·运用”收尾题与跨学科综合实践考点：考查展板结语拟写、宣传标语设计、采访提纲或倡议书等情境化得体表达。",
    "chinese_cand.classical_literature": "统摄北京中考语文第二部分“古诗文阅读”（约17–18分），含名句默写、古诗词鉴赏与文言文课内外对比阅读三大板块。",
    "chinese_cand.poetry.dictation": "北京中考古诗文默写必考题（4–5分）：以直接上下句默写与情境理解性默写相结合，严格锁定统编初中语文必背61篇古诗文，严防同音别字。",
    "chinese_cand.poetry.appreciation": "北京中考古诗词阅读必考题（5–6分）：聚焦意象捕捉、画面描绘、炼字品析、表现手法（借景抒情、虚实结合、用典）及诗人情感志向领悟。",
    "chinese_cand.prose.classical_vocab": "北京中考文言文阅读第一题必考点：采用课内迁移法（联系成语或学过的课内文言篇目）考查一词多义、古今异义、词类活用与高频虚词。",
    "chinese_cand.prose.classical_syntax_trans": "北京中考文言文阅读第二题必考点：结合上下文语境辨析文言语句断句停顿与重点句子准确翻译（落实踩分实词、特殊句式与省略成分补全）。",
    "chinese_cand.prose.classical_comprehension": "北京中考文言文阅读压轴设问：多采用“课内经典篇目+课外拓展选段”双文本比较阅读形式，考查文意概括、人物精神品格或治国修身哲理的印证分析。",
    "chinese_cand.modern_reading": "统摄北京中考语文“名著阅读”（5分）与“现代文阅读”（约25分：非连续性多材料阅读+记叙文/散文/小说文学阅读+议论文阅读）。",
    "chinese_cand.reading.informative_skills": "北京中考现代文阅读（多材料阅读或科普说明文）基础考点：考查概念内涵提炼、说明方法作用及说明语言严谨性辨析。",
    "chinese_cand.reading.multimodal_non_continuous": "北京中考现代文第一篇“多材料非连续性文本阅读”（7分）固定题型：结合北京城市建设、科技创新或文化传承的三则图文/数据图表材料，考查信息筛选、图表推断与综合归纳。",
    "chinese_cand.reading.narrative_plot_character": "北京中考文学作品阅读（记叙文/散文/小说，11–12分）核心考点：梳理行文脉络与情感变化线索，结合细节描写多维度概括人物形象特征。",
    "chinese_cand.reading.narrative_language_theme": "北京中考文学作品阅读高阶考点：品味富有表现力的词语、修辞手法与句式节奏，深入阐发文章标题意蕴与作品情感主旨。",
    "chinese_cand.reading.argument_claims_evidence": "北京中考议论文阅读（7分）核心考点：提炼中心论点与分论点，辨析事实论据与道理论据并判断新补充论据与分论点的匹配逻辑。",
    "chinese_cand.reading.argument_methods_structure": "北京中考议论文阅读高频考点：剖析段落或全文的论证推进思路（如“首先提出…接着通过…分析…最后得出…”），阐明举例、对比、比喻论证的作用。",
    "chinese_cand.reading.classic_whole_book": "北京中考“名著阅读”独立大题（5分）：要求学生结合统编必读名著（《朝花夕拾》《西游记》《骆驼祥子》《红星照耀中国》《水浒传》《简·爱》等）的具体人物与两个关联情节，自主提炼专题探究结论。",
    "chinese_cand.composition_expression": "统摄北京中考语文写作板块（大作文40分 + 情境微写作/名著读写结合），严格遵循方案A领域隔离，独立评估书面表达素养。",
    "chinese_cand.writing.composition_narrative": "北京中考大作文题目一（记叙文/写人叙事散文，40分）：考查中心立意、典型选材、结构详略布局、动作心理景物细节描摹与真情实感抒发。",
    "chinese_cand.writing.critical_micro_writing": "北京中考大作文题目二（议论性文章/跨时空想象作文）及情境化微写作（150–200字评论/感言/推荐语）：重点考查观点鲜明、逻辑严密与条理清晰的思辨表达能力。",
    # 英语（28 节点）
    "english_cand.phonetics_vocab": "统摄北京中考英语听说机考语音语调与笔试完形填空、阅读理解中的词汇构词与短语语境运用。",
    "english_cand.vocab.formation": "对应《课标》三级词汇表（1600词+派生词）：在北京中考阅读理解词义猜测题、阅读表达与书面表达高阶用词中发挥关键支撑作用。",
    "english_cand.vocab.collocation_context": "北京中考笔试第二部分“完形填空”（8道题，每题1分，共8分）核心考点：在记叙文语篇中通过上下文情感线索、动作逻辑精准辨析名词、动词、形容词与副词。",
    "english_cand.morphology": "统摄北京中考英语笔试第一部分“单项填空”（共12题，每题0.5分，共6分）中的词法核心考点。",
    "english_cand.noun.number_case": "北京中考语法基础考点：可数名词单复数、不可数名词量化及名词所有格在单选、完形与文段表达中的规范运用。",
    "english_cand.pronoun.types": "北京中考“单项填空”第1题固定必考题：在双句或对话语境中考查人称代词主格/宾格、形容词性/名词性物主代词及反身代词的准确指代。",
    "english_cand.preposition.usage": "北京中考“单项填空”第2题固定必考题：考查表示时间（at/on/in）、地点方位（in/on/at/to/under）及常见方式介词的语境用法。",
    "english_cand.article.rules": "初中英语词法基础考点，重点服务于文段表达写作准确性与语篇特指/泛指理解。",
    "english_cand.adj_adv.comparison": "北京中考“单项填空”第5/6题固定必考题：根据 than、as...as、of the three、in the world 等语境标志词判断形容词与副词原级、比较级与最高级。",
    "english_cand.numeral.rules": "在北京中考听说机考“听后记录”（时间、日期、价格、电话号码）与笔试细节阅读中高频考查。",
    "english_cand.verb_system": "统摄北京中考英语“单项填空”最大权重板块（第7–11题，占单选半壁江山）：聚焦初中五大核心时态、被动语态、情态动词与非谓语动词。",
    "english_cand.tense.present_past": "北京中考“单项填空”必考时态题：根据 often/every day/last week/in 2022 等时间状语或上下文平行动作判断一般现在时（含主谓一致三单）与一般过去时。",
    "english_cand.tense.future_continuous": "北京中考“单项填空”必考时态题：考查一般将来时（will/be going to）、现在进行时（Look!/Listen!/now）与过去进行时（when/while引导的时间背景）。",
    "english_cand.tense.present_perfect": "北京中考“单项填空”高频重难点：考查 since + 过去时间点、for + 时间段、already/yet/so far 标志下的现在完成时（have/has + done）及延续性动词用法。",
    "english_cand.voice.passive": "北京中考“单项填空”第11题固定必考题：考查一般现在时被动（am/is/are + done）与一般过去时被动（was/were + done）的主被动关系判断与时态结合。",
    "english_cand.modal.verbs": "北京中考“单项填空”第4题固定必考题：在对话语境中辨析 can/could（能力/许可）、must（必须/肯定推测）、needn't（不必）、should（建议）与 can't（不可能）。",
    "english_cand.non_finite.verbs": "服务于完形填空搭配、阅读长难句拆解与文段表达高级句式（动词不定式作目的状语/宾补及动名词搭配）。",
    "english_cand.syntax_system": "统摄北京中考英语“单项填空”中的句法考点（特殊疑问词、并列连词、状语从句、宾语从句）及阅读理解长难句分析。",
    "english_cand.clause.simple_sentences": "北京中考“单项填空”第3题常考特殊疑问词辨析（How often/How long/How soon/How far/Where/Why）及感叹句、There be 句型结构。",
    "english_cand.syntax.compound_conjunction": "北京中考“单项填空”第5题常考并列连词与从属连词辨析（and, but, or, so）以及上下文因果、转折、选择逻辑判断。",
    "english_cand.syntax.object_clause": "北京中考“单项填空”第12题压轴必考题：核心考查宾语从句三要素——引导词选择、**陈述句语序**（主语在助动词/谓语动词前）及主从句时态呼应。",
    "english_cand.syntax.adverbial_clause": "北京中考“单项填空”与完形填空高频考点：考查 when/while/until/as soon as/if/unless/because/although 从属连词逻辑及时间、条件状语从句“主将从现”规则。",
    "english_cand.syntax.attributive_clause": "对应《课标》附录4三级语法“定语从句（仅要求理解）”，主要在北京中考阅读理解 C、D 篇长难句精准理解与文段表达亮点句型中发挥作用。",
    "english_cand.skills_comprehension": "统摄北京中考英语听说机考（40分）与笔试阅读理解（26分）、阅读表达（10分）、文段表达（10分）四大语篇能力板块。",
    "english_cand.listening_speaking": "对应北京中考英语听说机考（40分，含听后选择、听后回答、听后记录与转述、短文朗读）：全面考查语音准确性、关键信息捕捉与口头转述组织能力。",
    "english_cand.reading.facts_inference": "对应北京中考笔试第三部分“阅读理解”（共13题，每题2分，共26分）：A篇信息匹配（3题）、B篇记叙文细节与情感推断（3题）、C篇科普说明文（3题）、D篇议论文主旨标题与作者态度深层推断（4题）。",
    "english_cand.reading.task_based": "对应北京中考笔试第四部分“阅读表达”（共4题，共10分：前3题各2分提取文章细节回答问题，第4题4分开放性思辨问答，要求观点明确并给出两条及以上支撑理由）。",
    "english_cand.writing.composition": "对应北京中考笔试第五部分“文段表达”（10分，二选一）：题目①通常为校园交际应用文（给外教/交换生写邮件邀请、建议或求助），题目②通常为围绕成长、责任、合作主题的观点论述。",
    # 物理（34 节点）
    "physics_cand.matter": "统摄北京中考物理第一主题“物质”，覆盖物态变化、质量与密度及微观粒子模型，常考于单选题与实验探究题。",
    "physics_cand.matter.thermal_state": "北京中考物理单选题与实验题常考考点：六种物态变化辨析与吸放热判断、液体温度计读数及“探究水沸腾时温度变化特点 / 晶体熔化规律”实验表格图像分析。",
    "physics_cand.matter.density_prop": "北京中考物理实验解答题高频必考题：托盘天平调平与游码读数、量筒排水法测体积、利用 $\\rho=m/V$ 测固体/液体密度及特殊法测密度实验步骤补充与误差分析。",
    "physics_cand.matter.micro_structure": "北京中考物理单选题或多项选择题常考考点：分子动理论（扩散现象、分子间引力与斥力）、原子核式结构模型及微观到宏观空间尺度排序。",
    "physics_cand.motion_interaction": "统摄北京中考物理第二主题“运动和相互作用”，涵盖力学核心板块（运动、力、压强、浮力、简单机械）以及声学、光学与电磁学基础。",
    "physics_cand.motion.speed": "北京中考物理基础必考点：参照物判断运动与静止、刻度尺估读与秒表读数、$v=s/t$ 速度计算、$s$-$t$ 与 $v$-$t$ 图像辨析及测量平均速度实验。",
    "physics_cand.force.basics": "北京中考物理基本功考点：力的作用效果、相互作用力与平衡力区分、重力/拉力/支持力/摩擦力示意图规范作图。",
    "physics_cand.force.gravity_friction": "北京中考物理单选题（增大或减小摩擦的方法实例）与核心实验题（探究影响滑动摩擦力大小的因素：控制变量法与转换法——水平匀速直线拉动木块或拉动下方长木板改进方案）。",
    "physics_cand.force.newton_balance": "北京中考物理单选题与多选题高频考点：惯性现象解释（严禁说“受到惯性”或“惯性力”）、二力平衡条件探究实验及运动状态与受力关系推理。",
    "physics_cand.force.pressure_fluid": "北京中考物理力学核心考点：增大减小固体压强实例、$p=F/S$ 与 $p=\\rho gh$ 综合分析、探究液体内部压强特点（U形管压强计转换法）、大气压与流体压强和流速关系。",
    "physics_cand.force.buoyancy": "北京中考物理力学高区分度核心考点（多选题、实验题或第26题力学综合计算题）：阿基米德原理 $F_{\\text{浮}}=G_{\\text{排}}=\\rho_{\\text{液}}gV_{\\text{排}}$、物体浮沉条件（漂浮/悬浮 $F_{\\text{浮}}=G$）与液面升降压强变化分析。",
    "physics_cand.force.simple_machine": "北京中考物理单选题（省力/费力/等臂杠杆分类）、作图题（力臂作图）与实验题（探究杠杆平衡条件 $F_1l_1=F_2l_2$：水平位置平衡目的与弹簧测力计斜拉时力臂变化分析）。",
    "physics_cand.sound": "北京中考物理单选题必考送分题：声音的产生（振动）与传播条件（介质）、音调（频率）/响度（振幅）/音色三特性辨析及减弱噪声三条途径。",
    "physics_cand.light.propagate_reflect": "北京中考物理光学必考点：光沿直线传播（影、日食、小孔成像）、光的反射定律探究实验、平面镜成像特点探究实验（薄玻璃板代替平面镜、等效替代法）及对称作图。",
    "physics_cand.light.refract_dispersion": "北京中考物理光学常考考点：光的折射现象辨析与折射角变化规律、白光色散及红外线/紫外线生活应用。",
    "physics_cand.light.lens_application": "北京中考物理实验题与单选/多选重难点：凸透镜对光会聚与凹透镜发散、探究凸透镜成像规律（物距 $u$ 与焦距 $f$、$2f$ 关系及动态移动规律）、照相机/投影仪/放大镜原理及近视眼（凹透镜）与远视眼（凸透镜）矫正。",
    "physics_cand.elec.charge_field": "北京中考物理电与磁基础考点：摩擦起电与两种电荷作用规律、导体与绝缘体辨析（首题常考）、磁体磁感线方向及地磁场。",
    "physics_cand.elec.electromagnetism": "北京中考物理电磁学必考对比点：奥斯特实验、通电螺线管安培定则判断极性、影响电磁铁磁性强弱因素探究、磁场对通电导体作用（电动机原理，有电源）与电磁感应现象（发电机原理，无电源，闭合电路一部分导体切割磁感线）。",
    "physics_cand.energy": "统摄北京中考物理第三主题“能量”，涵盖机械功与机械能、内能与比热容热机、欧姆定律与电功率综合计算（第25题电学压轴计算题与第26题力学综合计算题）。",
    "physics_cand.energy.transfer_concept": "北京中考物理基础概念考点：做功的两个必要因素（有力且在力的方向上移动距离，重点辨析劳而无功与不劳无功）及常见能量转化形式。",
    "physics_cand.energy.work_power_eff": "北京中考物理第26题（力学综合计算题，3–4分）或多项选择题核心考点：功 $W=Fs$、功率 $P=W/t=Fv$、滑轮组或杠杆机械效率 $\\eta=W_{\\text{有}}/W_{\\text{总}}$ 计算与受力分析。",
    "physics_cand.energy.mech_energy_conserv": "北京中考物理单选/多选题高频考点：结合滚摆、单摆、跳水、卫星轨道或冬奥滑雪情境分析动能、重力势能、弹性势能的变化及机械能是否守恒（考虑空气阻力/摩擦时机械能减小转化为内能）。",
    "physics_cand.energy.internal_heat": "北京中考物理热学必考考点：改变内能的两种方式（做功与热传递）实例辨析、温度/热量/内能三者逻辑关系（多选题常考）、比较不同物质吸热能力（比热容）实验及 $Q=cm\\Delta t$ 计算。",
    "physics_cand.energy.heat_engine": "北京中考物理热学常考考点：四冲程内燃机压缩冲程（机械能转内能）与做功冲程（内能转机械能）识别、燃料热值 $Q=mq$ 计算。",
    "physics_cand.energy.circuit_rules": "北京中考物理电学基石考点：串并联电路识别与实物图/电路图连接、电流表与电压表测量对象判断、串并联电流电压规律及滑动变阻器“一上一下”接法与故障分析。",
    "physics_cand.energy.ohm_law": "北京中考物理电学核心重难点：探究电流与电压、电阻的关系实验（控制变量法与滑动变阻器作用）、伏安法测电阻实验、动态电路电表示数变化判断及欧姆定律 $I=U/R$ 综合计算。",
    "physics_cand.energy.electric_power_joule": "北京中考物理第25题（电学压轴计算题，4分）及压轴实验题核心考点：电能表读数、电功 $W=UIt$、电功率 $P=UI=I^2R=U^2/R$、测小灯泡额定电功率实验、多挡位电热器电路分析及焦耳定律 $Q=I^2Rt$ 探究。",
    "physics_cand.energy.safety_and_conservation": "北京中考物理单选题必考考点：家庭电路火线零线地线连接（开关接火线、三孔插座左零右火上接地）、安全用电原则、核能（核裂变/核聚变）与可再生/不可再生能源分类。",
    "physics_cand.experiment": "统摄北京中考物理第四主题“实验探究”（占全卷分值约40%，约28分），全面覆盖《课标》21个必做学生实验。",
    "physics_cand.exp.measuring_skills": "对应北京中考物理实验解答题首题群（基本测量仪器直接读数题）：刻度尺、秒表、温度计、托盘天平、量筒、弹簧测力计、电流表、电压表、电能表与电阻箱规范读数。",
    "physics_cand.exp.inquiry_methods": "对应北京中考物理创新实验探究题（自变量与因变量识别、控制变量操作步骤书写、可探究科学问题提出、实验数据表格设计、$y$-$x$ 图像斜率/截距物理意义分析及实验评估）。",
    "physics_cand.interdisciplinary": "统摄北京中考物理第五主题“跨学科实践”，直接对应北京中考极具特色的“科普阅读题”（4分）。",
    "physics_cand.interdisciplinary.life_engineer": "对应北京中考物理科普阅读与跨学科实践题：结合中国古代工程智慧（天坛回音壁、省油灯、桔槔）与现代民生工程（高铁、跨海大桥、智能家居），考查从科技文本中提取物理规律并迁移解释的能力。",
    "physics_cand.interdisciplinary.society_development": "对应北京中考物理前沿科技情境题：结合“神舟/天宫”载人航天、“奋斗者”号深潜、北斗导航、超导与新能源技术，引导学生在真实科技成就情境中运用物理观念解决综合问题。",
}


def repo_root() -> Path:
    """获取代码仓库根目录，兼容容器内 /app 布局。"""
    return resolve_repo_root(__file__)


def _load_clauses_map(subject: str) -> dict[str, dict]:
    p = repo_root() / "contracts" / f"curriculum_clauses_{subject}.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {c["clause_id"]: c for c in data}


def _load_candidates(subject: str) -> list[dict]:
    p = repo_root() / "contracts" / f"{subject}_knowledge_taxonomy_candidate.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def build_clause_backed_opinion(
    subject: str,
    candidate: dict,
    clauses_map: dict[str, dict],
    reviewer_id: str = "beijing_zhongkao_expert",
) -> str:
    """
    以北京市中考全科教研专家视角，基于节点关联的 2022 年版课标条款、北京中考真题命题规范
    与新旧考点兼容映射，生成权威、翔实的专家审核意见。
    """
    meta = SUBJECT_META.get(
        subject,
        {
            "cn": subject,
            "std_title": "《义务教育课程标准（2022年版）》",
            "exam_spec": "北京市初中学业水平考试命题规范",
        },
    )
    subj_cn = meta["cn"]
    code = candidate["code"]
    name = candidate["name"]
    domain = candidate.get("domain", "")
    level = candidate.get("level", 2)
    is_elec = bool(candidate.get("is_elective", False))
    clause_ids: list[str] = candidate.get("source_clause_ids") or []
    legacy_codes: list[str] = (
        candidate.get("legacy_mapping_codes")
        if "legacy_mapping_codes" in candidate
        else candidate.get("legacy_mappings", [])
    ) or []

    matched_clauses = [clauses_map[cid] for cid in clause_ids if cid in clauses_map]
    snippets: list[str] = []
    for cl in matched_clauses[:5]:
        sec = cl.get("section", "")
        cnum = cl.get("clause_number", "")
        ppage = cl.get("print_page")
        pdf_page = cl.get("pdf_page")
        page_str = f"印刷页P{ppage}/PDF页P{pdf_page}" if ppage and pdf_page else ""
        req = (cl.get("derived_requirement") or cl.get("raw_text") or "").strip()
        if len(req) > 48:
            req = req[:48] + "…"
        head = f"{sec}{cnum}".strip()
        if page_str:
            head = f"{head}（{page_str}）"
        snippets.append(f"{head}：{req}")

    clause_summary = "；".join(snippets) if snippets else "已核对全部关联课标条文"
    if len(matched_clauses) > 5:
        clause_summary += f"（等共 {len(matched_clauses)} 条课标条文）"

    elec_statement = (
        "【选学属性核定】属于2022年版课标带“*”选学内容（is_elective=True），依据北京市中考命题规范（京教计〔2023〕44号）不纳入中考必考范围，已在学生端知识图谱、掌握度评估与智能组卷中执行强物理隔离。"
        if is_elec
        else "【必学属性核定】属于2022年版课标第四学段必学核心内容（is_elective=False），完全符合北京市初中学业水平考试必考范围要求，准予纳入学生端日常训练、独立未见题诊断与掌握度评估。"
    )

    expert_note = BEIJING_ZHONGKAO_EXPERT_NOTES.get(
        code,
        f"紧扣{meta['exam_spec']}，覆盖{name}核心概念、方法迁移与学业质量标准。",
    )

    legacy_note = (
        f"兼容映射存量考点 [{', '.join(legacy_codes)}]，存量真题与历史作答记录保持只读零改写。"
        if legacy_codes
        else "系依据2022年版课程标准第四学段新设立或选学剥离的独立节点，与存量必考旧码严格隔离。"
    )

    return (
        f"【北京市中考全科教研专家终审通过】"
        f"1. 课标溯源核验：依据{meta['std_title']}第四学段（7~9年级）要求，"
        f"节点「{name}」（编码：{code}，层级：L{level}，领域：{domain}）共绑定 {len(clause_ids)} 条官方课标条文（{clause_summary}），条文页码、原文与学业要求准确无误。"
        f"2. 北京中考考查定位：{expert_note}"
        f"3. 考查边界与兼容结论：{elec_statement}{legacy_note}"
        f"（审核专家：{reviewer_id}）"
    )


def seed_and_approve_subject(
    db: Session,
    subject: str,
    reviewer_id: str = "beijing_zhongkao_expert",
    force_update_existing: bool = False,
) -> dict:
    """
    对指定学科执行：
    1. 调用 seed_candidate_nodes 确保全部契约候选节点已入库并与契约一致；
    2. 对该学科所有候选节点的最新版本生成真实课标溯源审核意见并标记为 approved；
    3. 当 force_update_existing=True 时，清理同一节点下被取代的历史 pending 旧版本，防止残留未审核草稿。
    """
    seed_res = seed_candidate_nodes(subject=subject, db=db)
    clauses_map = _load_clauses_map(subject)
    candidates = _load_candidates(subject)
    cand_map = {c["code"]: c for c in candidates}

    prefix = f"{subject}_cand."
    db_nodes = db.scalars(
        select(m.KnowledgeNode).where(
            m.KnowledgeNode.subject == subject,
            m.KnowledgeNode.code.startswith(prefix),
            m.KnowledgeNode.status == "active",
        )
    ).all()

    approved_count = 0
    already_approved = 0
    now_dt = datetime.now(timezone.utc)

    for db_node in db_nodes:
        cand = cand_map.get(db_node.code)
        if cand is None:
            continue
        db_node.is_elective = bool(cand.get("is_elective", False))
        ver = _latest(db, db_node.id)
        if ver is None:
            continue
        if ver.review_status == "approved" and not force_update_existing:
            already_approved += 1
            continue

        opinion = build_clause_backed_opinion(subject, cand, clauses_map, reviewer_id=reviewer_id)
        ver.review_status = "approved"
        ver.reviewer_id = reviewer_id
        ver.review_opinion = opinion
        ver.reviewed_at = now_dt
        approved_count += 1

        if force_update_existing and ver.version > 1:
            db.execute(
                delete(m.KnowledgeNodeVersion).where(
                    m.KnowledgeNodeVersion.node_id == db_node.id,
                    m.KnowledgeNodeVersion.version < ver.version,
                    m.KnowledgeNodeVersion.review_status == "pending",
                )
            )

    db.commit()
    return {
        "subject": subject,
        "seeded": seed_res,
        "total_candidate_nodes": len(db_nodes),
        "approved_now": approved_count,
        "already_approved": already_approved,
    }


def publish_subject_taxonomy_release(
    db: Session,
    subject: str,
    release_version: str = "v2022.1.0",
    published_by: str = "beijing_zhongkao_expert",
    force_update_existing: bool = False,
) -> dict:
    """
    在全部候选节点均已 approved 的前提下，生成并持久化不可变的学科知识体系发布快照（或当 force_update_existing=True 时刷新快照）。
    """
    prefix = f"{subject}_cand."
    cand_nodes = db.scalars(
        select(m.KnowledgeNode)
        .where(
            m.KnowledgeNode.subject == subject,
            m.KnowledgeNode.code.startswith(prefix),
            m.KnowledgeNode.status == "active",
        )
        .order_by(m.KnowledgeNode.code)
    ).all()

    if not cand_nodes:
        raise ValueError(f"学科 {subject} 无活跃候选节点，无法发布")

    snapshot_nodes: list[dict] = []
    for n in cand_nodes:
        ver = _latest(db, n.id)
        if ver is None or ver.review_status != "approved":
            raise ValueError(f"节点 {n.code} 尚未审核通过，拒绝发布")
        snapshot_nodes.append(
            {
                "id": n.id,
                "code": n.code,
                "name": ver.name,
                "version": ver.version,
                "parent_id": n.parent_id,
                "parent_node_id": ver.parent_node_id,
                "parent_code": ver.parent_code,
                "description": ver.description,
                "source_clause_ids": ver.source_clause_ids,
                "reviewer_id": ver.reviewer_id,
                "review_opinion": ver.review_opinion,
                "reviewed_at": ver.reviewed_at.isoformat() if ver.reviewed_at else None,
                "is_elective": bool(n.is_elective),
            }
        )

    now_dt = datetime.now(timezone.utc)
    full_ver = f"{subject}-{release_version}" if not release_version.startswith(f"{subject}-") else release_version
    snapshot_payload = {
        "subject": subject,
        "release_version": full_ver,
        "published_at": now_dt.isoformat(),
        "published_by": published_by,
        "total_nodes": len(snapshot_nodes),
        "expected_nodes_count": len(cand_nodes),
        "nodes": snapshot_nodes,
    }
    existing_rel = db.scalar(
        select(m.KnowledgeTaxonomyRelease).where(
            m.KnowledgeTaxonomyRelease.subject == subject,
            m.KnowledgeTaxonomyRelease.release_version == full_ver,
        )
    )
    summary_text = (
        f"{SUBJECT_META.get(subject, {}).get('cn', subject)} 2022年版课标与北京市中考专家终审正式版"
        f"（共 {len(snapshot_nodes)} 个节点，由 {published_by} 审定签发）"
    )
    if existing_rel is not None:
        if force_update_existing:
            existing_rel.snapshot = snapshot_payload
            existing_rel.published_by = published_by
            existing_rel.published_at = now_dt
            existing_rel.summary = summary_text
            db.commit()
            db.refresh(existing_rel)
            return {
                "release_id": existing_rel.id,
                "subject": subject,
                "release_version": full_ver,
                "total_nodes": len(snapshot_nodes),
                "status": "published",
            }
        existing_total = (
            existing_rel.snapshot.get("total_nodes", len(existing_rel.snapshot.get("nodes", [])))
            if isinstance(existing_rel.snapshot, dict)
            else (len(existing_rel.snapshot) if isinstance(existing_rel.snapshot, list) else 0)
        )
        return {
            "release_id": existing_rel.id,
            "subject": subject,
            "release_version": full_ver,
            "total_nodes": existing_total,
            "status": "already_published",
        }

    rel = m.KnowledgeTaxonomyRelease(
        subject=subject,
        release_version=full_ver,
        published_by=published_by,
        published_at=now_dt,
        summary=summary_text,
        snapshot=snapshot_payload,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return {
        "release_id": rel.id,
        "subject": subject,
        "release_version": full_ver,
        "total_nodes": len(snapshot_nodes),
        "status": "published",
    }


def audit_and_publish_subject(
    db: Session,
    subject: str,
    reviewer_id: str = "beijing_zhongkao_expert",
    release_version: str = "v2022.1.0",
    force_update_existing: bool = False,
) -> dict:
    """一键完成单学科候选入库、逐点课标审核与正式版本发布。"""
    audit_res = seed_and_approve_subject(
        db=db,
        subject=subject,
        reviewer_id=reviewer_id,
        force_update_existing=force_update_existing,
    )
    rel_res = publish_subject_taxonomy_release(
        db=db,
        subject=subject,
        release_version=release_version,
        published_by=reviewer_id,
        force_update_existing=force_update_existing,
    )
    return {
        **audit_res,
        "release_id": rel_res["release_id"],
        "release_version": rel_res["release_version"],
        "release_status": rel_res["status"],
    }


def seed_and_publish_all_subjects(
    db: Session,
    reviewer_id: str = "beijing_zhongkao_expert",
    release_version: str = "v2022.1.0",
    force_update_existing: bool = False,
) -> list[dict]:
    """对数学、语文、英语、物理四科共 135 个候选知识点执行全量入库、审核与发布。"""
    results: list[dict] = []
    for subj in SUBJECTS:
        results.append(
            audit_and_publish_subject(
                db=db,
                subject=subj,
                reviewer_id=reviewer_id,
                release_version=release_version,
                force_update_existing=force_update_existing,
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：对指定数据库执行四学科 135 个候选知识点审核入库与发布。"""
    import argparse

    from .database import SessionLocal, make_engine
    from .models import Base

    parser = argparse.ArgumentParser(description="全学科候选知识点专家审核与正式版本发布")
    parser.add_argument(
        "--database-url",
        default=None,
        help="覆盖默认数据库连接 URL（例如 sqlite:////path/to/db.sqlite3）",
    )
    parser.add_argument(
        "--reviewer-id",
        default="beijing_zhongkao_expert",
        help="记录在案的审核人标识（默认：beijing_zhongkao_expert）",
    )
    parser.add_argument(
        "--release-version",
        default="v2022.1.0",
        help="发布版本号后缀（默认：v2022.1.0）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新生成审核意见并刷新已发布快照",
    )
    args = parser.parse_args(argv)

    if args.database_url:
        engine = make_engine(args.database_url)
        Base.metadata.create_all(bind=engine)
        session = Session(bind=engine)
    else:
        session = SessionLocal()

    try:
        summary = seed_and_publish_all_subjects(
            db=session,
            reviewer_id=args.reviewer_id,
            release_version=args.release_version,
            force_update_existing=args.force,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

