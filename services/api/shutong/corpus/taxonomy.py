# -*- coding: utf-8 -*-
"""北京市义务教育课程标准四科（数学、物理、英语、语文）核心知识点树定义。
严格依照北京市初中学业水平考试考查要求与教学大纲梳理，支持层级与版本演进。
"""
from __future__ import annotations

TAXONOMY: dict[str, list[dict[str, str | None]]] = {
    "math": [
        # 一级主题：数与代数
        {"code": "math.num_alg", "subject": "math", "name": "数与代数", "description": "数与式、方程与不等式、函数及其图象", "parent_code": None},
        {"code": "math.num.real", "subject": "math", "name": "实数与数轴绝对值", "description": "有理数、无理数、相反数、数轴表示、绝对值及科学记数法", "parent_code": "math.num_alg"},
        {"code": "math.alg.poly", "subject": "math", "name": "整式运算与因式分解", "description": "整式加减乘除、乘法公式、提公因式法与公式法因式分解", "parent_code": "math.num_alg"},
        {"code": "math.alg.frac", "subject": "math", "name": "分式与二次根式运算", "description": "分式化简求值、二次根式性质与化简计算", "parent_code": "math.num_alg"},
        {"code": "math.eq.linear_system", "subject": "math", "name": "一次方程与二元一次方程组", "description": "一元一次方程解法、二元一次方程组代入消元与加减消元", "parent_code": "math.num_alg"},
        {"code": "math.eq.quadratic", "subject": "math", "name": "一元二次方程与分式方程", "description": "一元二次方程配方法/公式法、根的判别式及分式方程验根", "parent_code": "math.num_alg"},
        {"code": "math.ineq", "subject": "math", "name": "一元一次不等式组", "description": "不等式基本性质、一元一次不等式组解集及数轴表示", "parent_code": "math.num_alg"},
        {"code": "math.func.linear", "subject": "math", "name": "一次函数与正比例函数", "description": "一次函数图象与增减性质、待定系数法求解析式、交点问题", "parent_code": "math.num_alg"},
        {"code": "math.func.inverse", "subject": "math", "name": "反比例函数", "description": "反比例函数图象、增减性、k的几何意义与面积关系", "parent_code": "math.num_alg"},
        {"code": "math.func.quad", "subject": "math", "name": "二次函数综合", "description": "二次函数图象、顶点式、对称轴、交点、极值与实际应用", "parent_code": "math.num_alg"},

        # 一级主题：图形与几何
        {"code": "math.geo", "subject": "math", "name": "图形与几何", "description": "相交线与平行线、三角形、四边形、圆、图形变换", "parent_code": None},
        {"code": "math.geo.lines", "subject": "math", "name": "相交线、平行线与角", "description": "对顶角、平行线性质与判定、角平分线性质", "parent_code": "math.geo"},
        {"code": "math.geo.triangle", "subject": "math", "name": "三角形与全等三角形", "description": "三角形内角和与外角、等腰/等边三角形、全等判定与证明", "parent_code": "math.geo"},
        {"code": "math.geo.pythagoras", "subject": "math", "name": "勾股定理与直角三角形", "description": "勾股定理及其逆定理、特殊直角三角形性质", "parent_code": "math.geo"},
        {"code": "math.geo.quadrilateral", "subject": "math", "name": "四边形与特殊平行四边形", "description": "平行四边形、矩形、菱形、正方形性质与判定综合", "parent_code": "math.geo"},
        {"code": "math.geo.circle", "subject": "math", "name": "圆的性质与切线", "description": "垂径定理、圆周角定理、切线性质与判定、弧长扇形计算", "parent_code": "math.geo"},
        {"code": "math.geo.similar", "subject": "math", "name": "相似图形与比例线段", "description": "相似三角形判定与性质、射影定理与比例线段计算", "parent_code": "math.geo"},
        {"code": "math.geo.trig", "subject": "math", "name": "锐角三角函数与解直角三角形", "description": "正弦、余弦、正切概念与特殊角三角函数值、仰角俯角测量", "parent_code": "math.geo"},
        {"code": "math.geo.transform", "subject": "math", "name": "图形变换与对称折叠", "description": "轴对称图形、中心对称图形、图形旋转、平移与折叠问题", "parent_code": "math.geo"},
        {"code": "math.geo.comprehensive", "subject": "math", "name": "几何综合探究与动点最值", "description": "动点路径、几何定值与最值、旋转综合与线段关系探究", "parent_code": "math.geo"},

        # 一级主题：统计与概率
        {"code": "math.stat_prob", "subject": "math", "name": "统计与概率", "description": "数据分析与概率初步", "parent_code": None},
        {"code": "math.stat.data", "subject": "math", "name": "数据的收集、整理与分析", "description": "平均数、中位数、众数、方差、频数分布表与条形扇形统计图", "parent_code": "math.stat_prob"},
        {"code": "math.prob.basic", "subject": "math", "name": "概率初步与树状图法", "description": "简单随机事件概率、列表法与树状图法求概率", "parent_code": "math.stat_prob"},

        # 一级主题：新考法与新定义
        {"code": "math.adv.new_definition", "subject": "math", "name": "新定义与综合实践探究", "description": "新运算规则、新几何特征图形探究、关联点集与综合推理", "parent_code": None},
    ],

    "physics": [
        # 一级主题：声与光
        {"code": "physics.acoustics_optics", "subject": "physics", "name": "声学与光学", "description": "声现象与光现象综合", "parent_code": None},
        {"code": "physics.sound", "subject": "physics", "name": "声现象", "description": "声音的产生与传播、音调响度音色、噪声的防治与控制", "parent_code": "physics.acoustics_optics"},
        {"code": "physics.light.reflection_refraction", "subject": "physics", "name": "光的直线传播、反射与折射", "description": "光的直线传播与小孔成像、光的反射规律、平面镜成像、折射现象", "parent_code": "physics.acoustics_optics"},
        {"code": "physics.light.lens", "subject": "physics", "name": "透镜及其成像规律", "description": "凸透镜成像规律及应用、照相机/放大镜原理、近视远视眼矫正", "parent_code": "physics.acoustics_optics"},

        # 一级主题：热学
        {"code": "physics.thermal", "subject": "physics", "name": "热学", "description": "物态变化、内能与比热容", "parent_code": None},
        {"code": "physics.thermal.state", "subject": "physics", "name": "物态变化", "description": "熔化和凝固、汽化和液化、升华和凝华现象辨析及吸放热特点", "parent_code": "physics.thermal"},
        {"code": "physics.thermal.heat", "subject": "physics", "name": "内能、比热容与热机", "description": "分子动理论、内能概念与改变方式、比热容及其热量计算、热机效率", "parent_code": "physics.thermal"},

        # 一级主题：力学
        {"code": "physics.mechanics", "subject": "physics", "name": "力学", "description": "运动和力、压强与浮力、功与机械", "parent_code": None},
        {"code": "physics.mech.motion", "subject": "physics", "name": "机械运动与参照物", "description": "参照物的选取、物体运动状态判断、速度与平均速度计算", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.forces", "subject": "physics", "name": "常见力与重力摩擦力", "description": "力的概念与作用效果、弹簧测力计使用、重力计算、增大与减小摩擦", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.balance", "subject": "physics", "name": "牛顿第一定律、惯性与二力平衡", "description": "牛顿第一定律、惯性现象及解释、平衡力与相互作用力辨析", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.density", "subject": "physics", "name": "质量与密度测量", "description": "质量概念与天平使用、密度公式应用、量筒测液体固体密度", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.pressure", "subject": "physics", "name": "固体与液体压强、大气压强", "description": "固体压强概念与计算、液体内部压强规律、托里拆利实验与流体压强", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.buoyancy", "subject": "physics", "name": "浮力与阿基米德原理", "description": "阿基米德原理、浮力产生原因、物体浮沉条件及潜水艇轮船应用", "parent_code": "physics.mechanics"},
        {"code": "physics.mech.work", "subject": "physics", "name": "功、功率与机械效率", "description": "做功必要因素、功和功率计算、动能与势能转化、杠杆与滑轮机械效率", "parent_code": "physics.mechanics"},

        # 一级主题：电学与磁学
        {"code": "physics.electromagnetism", "subject": "physics", "name": "电学与磁学", "description": "电路、欧姆定律、电功率与电磁现象", "parent_code": None},
        {"code": "physics.elec.circuit", "subject": "physics", "name": "电路基础与电流电压", "description": "摩擦起电、导体绝缘体、串并联电路、电流表与电压表使用与读数", "parent_code": "physics.electromagnetism"},
        {"code": "physics.elec.ohm", "subject": "physics", "name": "电阻、滑动变阻器与欧姆定律", "description": "影响电阻大小因素、滑动变阻器连接、欧姆定律公式应用与动态电路", "parent_code": "physics.electromagnetism"},
        {"code": "physics.elec.power", "subject": "physics", "name": "电功、电功率与焦耳定律", "description": "电能表读数、额定功率与实际功率计算、焦耳定律与电热、安全用电", "parent_code": "physics.electromagnetism"},
        {"code": "physics.elec.magnetism", "subject": "physics", "name": "电与磁、电磁感应", "description": "磁场与磁感线、安培定则、电磁铁、电动机发电机原理、电磁感应现象", "parent_code": "physics.electromagnetism"},
        {"code": "physics.exp.inquiry", "subject": "physics", "name": "物理实验与科学探究方法", "description": "控制变量法、转换法、实验数据分析与结论表述、误差评估", "parent_code": None},
    ],

    "english": [
        # 一级主题：词法
        {"code": "english.grammar", "subject": "english", "name": "语法与词法", "description": "初中阶段代词、介词、时态、语态及连词", "parent_code": None},
        {"code": "english.grammar.pronoun", "subject": "english", "name": "代词分类与用法", "description": "人称代词主宾格、物主代词、反身代词、不定代词 (some/any/each/both)", "parent_code": "english.grammar"},
        {"code": "english.grammar.preposition", "subject": "english", "name": "介词与介词短语", "description": "时间介词 (at/on/in)、地点与方向介词 (under/between/across)、常用固定搭配", "parent_code": "english.grammar"},
        {"code": "english.grammar.tense", "subject": "english", "name": "动词时态与语态", "description": "一般现在时、一般过去时、现在进行时、一般将来时、现在完成时与被动语态", "parent_code": "english.grammar"},
        {"code": "english.grammar.modal", "subject": "english", "name": "情态动词用法", "description": "can/could, may, must, should, need 的语气与用法辨析", "parent_code": "english.grammar"},
        {"code": "english.grammar.conjunction", "subject": "english", "name": "连词与并列句", "description": "and, but, or, so, because, although, if, until 等并列与从属连词", "parent_code": "english.grammar"},
        {"code": "english.grammar.comparative", "subject": "english", "name": "形容词与副词比较等级", "description": "原级比较 (as...as)、比较级与最高级的规则与不规则变化及典型句型", "parent_code": "english.grammar"},
        {"code": "english.grammar.noun", "subject": "english", "name": "名词的数与所有格", "description": "可数名词复数、不可数名词计量、名词所有格及词义辨析", "parent_code": "english.grammar"},

        # 一级主题：句法
        {"code": "english.syntax", "subject": "english", "name": "句法与复合句", "description": "宾语从句、状语从句与定语从句", "parent_code": None},
        {"code": "english.syntax.object_clause", "subject": "english", "name": "宾语从句", "description": "that/if/whether 及特殊疑问词引导的宾语从句陈述语序与时态呼应", "parent_code": "english.syntax"},
        {"code": "english.syntax.adverbial_clause", "subject": "english", "name": "状语从句", "description": "时间、条件、让步、原因状语从句及其主将从现原则", "parent_code": "english.syntax"},
        {"code": "english.syntax.attributive_clause", "subject": "english", "name": "定语从句初步", "description": "that, which, who 引导的定语从句识别与基本理解", "parent_code": "english.syntax"},

        # 一级主题：语篇与应用
        {"code": "english.skills", "subject": "english", "name": "语篇理解与综合表达", "description": "完形填空、阅读理解与书面表达", "parent_code": None},
        {"code": "english.cloze.context", "subject": "english", "name": "完形填空语境理解与词义辨析", "description": "结合故事叙述与上下文线索推断实词（名词、动词、形容词）最佳选项", "parent_code": "english.skills"},
        {"code": "english.reading.detail", "subject": "english", "name": "阅读理解事实细节与主旨概括", "description": "快速定位事实信息、同义替换理解、段落与全文主旨大意提炼", "parent_code": "english.skills"},
        {"code": "english.reading.expression", "subject": "english", "name": "任务型阅读与简答表达", "description": "阅读文本回答问题、原句信息提炼、规范简明书写", "parent_code": "english.skills"},
        {"code": "english.writing.composition", "subject": "english", "name": "书面表达与话题写作", "description": "根据提示完成书信、通知、自我感悟等话题短文，语法正确连贯", "parent_code": "english.skills"},
        {"code": "english.listening", "subject": "english", "name": "听力理解", "description": "短对话理解、长对话推断、独白信息提取与记录", "parent_code": "english.skills"},
    ],

    "chinese": [
        # 一级主题：基础·运用
        {"code": "chinese.base", "subject": "chinese", "name": "基础·运用", "description": "字音字形、成语词语、病句标点、文化常识与综合表达", "parent_code": None},
        {"code": "chinese.base.phonetics", "subject": "chinese", "name": "字音辨析与注音拼读", "description": "初中统编教材多音字、易错字读音辨析与规范拼音标注", "parent_code": "chinese.base"},
        {"code": "chinese.base.character", "subject": "chinese", "name": "汉字字形与错别字纠正", "description": "常见同音字、形近字字形辨析与规范书写", "parent_code": "chinese.base"},
        {"code": "chinese.base.idiom", "subject": "chinese", "name": "成语与词语语境运用", "description": "结合具体语境理解成语含义、褒贬色彩、使用对象与轻重程度", "parent_code": "chinese.base"},
        {"code": "chinese.base.syntax", "subject": "chinese", "name": "病句辨析与句子修改", "description": "成分残缺、搭配不当、语序不当、句式杂糅等常见语病识别与修改", "parent_code": "chinese.base"},
        {"code": "chinese.base.punctuation", "subject": "chinese", "name": "标点符号规范使用", "description": "顿号、逗号、分号、冒号、引号、书名号等标点符号规范用法", "parent_code": "chinese.base"},
        {"code": "chinese.base.culture", "subject": "chinese", "name": "文学文化常识与书法鉴赏", "description": "传统文化常识、书法五体特点鉴赏、节日节气与名家名作常识", "parent_code": "chinese.base"},
        {"code": "chinese.base.expression", "subject": "chinese", "name": "情境表达与综合性学习", "description": "宣传标语拟写、发言提纲、活动方案设计与得体文明表达", "parent_code": "chinese.base"},

        # 一级主题：古诗文阅读
        {"code": "chinese.poetry_classical", "subject": "chinese", "name": "古诗文阅读", "description": "古诗文名句默写、诗歌鉴赏与文言文阅读", "parent_code": None},
        {"code": "chinese.poetry.dictation", "subject": "chinese", "name": "古诗文名句理解性默写", "description": "课标推荐背诵古诗文名句情境默写与准确书写", "parent_code": "chinese.poetry_classical"},
        {"code": "chinese.poetry.appreciation", "subject": "chinese", "name": "古代诗歌意象鉴赏与情感感悟", "description": "炼字炼句品味、典型意象分析、诗人思想感情与主旨把握", "parent_code": "chinese.poetry_classical"},
        {"code": "chinese.prose.classical", "subject": "chinese", "name": "文言文实词、断句与对比理解", "description": "重点文言实词释义、文言断句、重点句子翻译与文意对比探究", "parent_code": "chinese.poetry_classical"},

        # 一级主题：名著与现代文阅读
        {"code": "chinese.reading", "subject": "chinese", "name": "现代文与整本书阅读", "description": "名著阅读、记叙文/散文、说明性文本与议论文阅读", "parent_code": None},
        {"code": "chinese.classic.reading", "subject": "chinese", "name": "名著阅读人物与主题探究", "description": "《骆驼祥子》《红星照耀中国》《朝花夕拾》《水浒传》等情节人物分析", "parent_code": "chinese.reading"},
        {"code": "chinese.reading.narrative", "subject": "chinese", "name": "记叙文语言品味与主旨理解", "description": "情节梳理概括、人物形象与心理分析、关键语句赏析、主题感悟", "parent_code": "chinese.reading"},
        {"code": "chinese.reading.informative", "subject": "chinese", "name": "说明文与非连续性文本信息提取", "description": "说明方法及作用、图表与多材料信息比对整合、实际生活应用探究", "parent_code": "chinese.reading"},
        {"code": "chinese.reading.argumentative", "subject": "chinese", "name": "议论文论点论据论证分析", "description": "中心论点与分论点提炼、论据类型与论证方法分析、论证结构梳理", "parent_code": "chinese.reading"},

        # 一级主题：写作
        {"code": "chinese.writing.composition", "subject": "chinese", "name": "写作表达与立意构思", "description": "命题与半命题作文审题立意、真情实感、详略得当与语言表达", "parent_code": None},
    ],
}
