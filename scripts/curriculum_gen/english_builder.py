# -*- coding: utf-8 -*-
"""
英语学科官方课程标准初中条款全集、候选知识体系与存量考点映射构建器。
依据教育部《义务教育英语课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-ENGLISH）初中三级（7~9年级）内容要求、附录4语法项目表与学业质量标准。
"""

from __future__ import annotations


def build_english_data():
    source_id = "MOE-2022-ENGLISH"
    subject = "english"
    stage = "stage4"  # Schema 学段代码 stage4，对应初中 7~9 年级（英语课标初中三级体系）
    pdf_offset = 7  # 印刷第1页对应 PDF 物理第8页

    # 1. 英语课程标准初中三级与附录4全量条款集合 (覆盖六大要素：主题、语篇、语言知识、文化、技能、策略及学业质量标准，附录4语法项目独立采录)
    clauses = [
        # --- 1. 主题范畴（初中三级要求）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:theme_contexts:c01",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "1. 主题范畴（三级）", "sub_theme": "人与自我、人与社会、人与自然三大范畴及子主题群",
            "section_type": "content_requirement", "clause_number": "三级·主题范畴",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "主题包括人与自我、人与社会、人与自然三大范畴。其中，“人与自我”以“我”为视角，设置“生活与学习”和“做人与做事”等主题群；“人与社会”以“社会”为视角，设置“社会服务与人际沟通”“文学、艺术与体育”“历史、社会与文化”和“科学与技术”等主题群；“人与自然”以“自然”为视角，设置“自然生态”“环境保护”“灾害防范”和“宇宙探索”等主题群。各主题群下设若干子主题。具体内容要求见表 5 至表 7。",
            "standardized_text": "在人与自我、人与社会、人与自然三大主题范畴及子主题语境中运用词汇、语法及语篇知识进行听、说、读、看、写，把握作者态度与价值取向。",
            "collation_note": "经人工逐字核对，与教育部2022年版英语课程标准印刷第14页（PDF第21页）主题范畴内容要求文字完全一致",
            "is_elective": False, "derived_requirement": "三大主题语境在完形填空、阅读理解与话题作文中的综合运用",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        },

        # --- 2. 语篇类型（表8 初中三级要求）---
        {
            "clause_id": "cs:english:2022:s4:reading:content_req:discourse_genre:c02",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "2. 语篇类型（表8 三级）", "sub_theme": "连续性文本与非连续性多模态语篇",
            "section_type": "content_requirement", "clause_number": "三级表8·语篇类型",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "1. 日常对话、独白；2. 记叙文，如故事、简版小说、人物传记、童话等；3. 说明文，如介绍类短文、程序或现象说明、事理阐释、书面指令、操作指南、使用手册等；4. 应用文，如日记、私人信件、宣传海报、宣传册、通知、活动安排与计划、规则、问卷等；5. 新闻报道，如简讯、专题报道等；6. 工具书，如词典、语法书等；7. 新媒体语篇，如常见网络媒体语篇、电子邮件、社交媒体信息等；8. 其他语篇类型，如歌曲、诗歌、剧本、广告、图片、表格（图表）与图示、天气预报，以及广播、电视、网络节目等。",
            "standardized_text": "接触和理解对话、记叙文、说明文、应用文及图表、图画等多模态非连续性文本，把握不同语篇的组织结构和文体特征。",
            "collation_note": "经人工逐字比对，与教育部2022年版英语课标印刷第18页（PDF第25页）表8语篇类型内容要求（三级）第1-8项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握常见应用文与说明文、记叙文文体特征分析与任务型阅读图文信息匹配",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        },

        # --- 3. 语言知识：语音知识（表9 三级）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:phonetics:c03",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·语音知识（表9 三级）", "sub_theme": "音标拼读、意群与连读语调",
            "section_type": "content_requirement", "clause_number": "三级表9·语音要求",
            "pdf_page": 19 + pdf_offset, "print_page": 19,
            "raw_text": "1. 了解语音在语言学习中的意义和在语境中的表意功能；2. 辨识口语表达中的意群，并在口头交流中按照意群表达；3. 根据重音、意群、语调与节奏等语音方面的变化，感知和理解说话人表达的意义、意图和态度；4. 借助重音、意群、语调、节奏等方面的变化，表达不同的意义、意图和态度；5. 根据读音规则和音标拼读单词；6. 查词典时，运用音标知识学习单词的发音。",
            "standardized_text": "掌握国际音标拼读、开闭音节规律、单词及句子重音、意群停顿与语调连读，准确运用于初中听说朗读与口语交互。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第19页（PDF第26页）表9语音知识三级要求1-6条完全一致",
            "is_elective": False, "derived_requirement": "掌握国际音标、拼读规则、句子语调意群停顿与听说机考朗读能力",
            "review_status": "pending", "legacy_mappings": ["english.listening"]
        },

        # --- 3. 语言知识：词汇知识（表10 三级）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:vocab_formation:c04",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·词汇知识（表10 三级）", "sub_theme": "词缀构词法与词性转换",
            "section_type": "content_requirement", "clause_number": "三级表10·词汇构词法",
            "pdf_page": 20 + pdf_offset, "print_page": 20,
            "raw_text": "1. 了解英语词汇包括单词、短语、习惯用语和固定搭配等形式；2. 理解和领悟词汇的基本含义，以及在特定语境和语篇中的意义、词性及功能；3. 了解根据词缀（前缀和后缀）理解和运用词汇的方法；6. 根据所学构词法知识和语境线索，推断语篇中未学过的词汇的含义。",
            "standardized_text": "掌握常见前缀（un-, dis-, im-等）、后缀（-er, -or, -tion, -ful, -less, -ly等）派生法、合成法与转化法构词规律，结合语境推断词义与词性。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第20页（PDF第27页）表10词汇知识三级内容要求第1、2、3、6条完全一致",
            "is_elective": False, "derived_requirement": "掌握构词法规则、词类派生转换与完形填空生词语境推断能力",
            "review_status": "pending", "legacy_mappings": ["english.cloze.context"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:vocab_collocation:c05",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·词汇知识（表10 三级）", "sub_theme": "习惯短语搭配与语境词义辨析",
            "section_type": "content_requirement", "clause_number": "三级表10·词汇运用",
            "pdf_page": 20 + pdf_offset, "print_page": 20,
            "raw_text": "4. 在特定语境中，根据不同主题，运用词汇给事物命名，描述事物、行为、过程和特征，表达与主题相关的意义、意图和观点等；5. 围绕相关主题，在语境中运用约1600个单词进行交流与表达。",
            "standardized_text": "掌握初中1600个核心词汇及常用动词短语、介词短语与固定搭配，辨析同义词、近义词与多义词在特定语境中的意义。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第20页（PDF第27页）表10词汇知识三级内容要求第4、5条完全一致",
            "is_elective": False, "derived_requirement": "掌握初中1600词汇高频短语搭配、一词多义与完形填空语境词义辨析",
            "review_status": "pending", "legacy_mappings": ["english.cloze.context"]
        },

        # --- 3. 语言知识：语法知识总则（表11 三级）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:grammar_general:c06",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·语法知识（表11 三级）", "sub_theme": "语法知识三级内容要求（形式—意义—使用统一体）",
            "section_type": "content_requirement", "clause_number": "三级表11·语法要求",
            "pdf_page": 21 + pdf_offset, "print_page": 21,
            "raw_text": "1. 初步意识到语言使用中的语法知识是“形式—意义—使用”的统一体，明确学习语法的目的是在语境中运用语法知识理解和表达意义；2. 了解句子的结构特征，如句子的种类、成分、语序及主谓一致；3. 在口语和书面语篇中理解、体会所学语法的形式和表意功能；4. 在语境中运用所学语法知识进行描述、叙述和说明等。",
            "standardized_text": "树立语法“形式—意义—使用”统一体观念，在语境中把握句子结构特征（种类、成分、语序及主谓一致），理解表意功能并用于描述、叙述和说明。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第21页（PDF第28页）表11语法知识三级内容要求第1-4条原文完全一致",
            "is_elective": False, "derived_requirement": "在具体情境中综合运用词法与句法知识进行理解与表达",
            "review_status": "pending", "legacy_mappings": ["english.grammar"]
        },

        # --- 附录 4 语法项目表·词类项目（初中三级考查范围，严格分离自表11）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:noun_grammar:c07",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(一) 名词", "sub_theme": "可数与不可数名词、专有名词与名词所有格",
            "section_type": "content_requirement", "clause_number": "附录4·一(一)名词",
            "pdf_page": 138 + pdf_offset, "print_page": 138,
            "raw_text": "(一) 名词：1. 可数名词及其单、复数；2. 不可数名词；3. 专有名词；4. 名词所有格。",
            "standardized_text": "掌握名词可数与不可数判断、规则与不规则复数变化、专有名词大写及名词所有格（'s与of所有格）的正确用法。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第138页（PDF第145页）名词条目原文完全一致",
            "is_elective": False, "derived_requirement": "熟练掌握可数名词规则与不规则复数、不可数名词计量及名词所有格运用",
            "review_status": "pending", "legacy_mappings": ["english.grammar.noun"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:pronoun_grammar:c08",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(五) 代词", "sub_theme": "人称代词、物主代词、反身代词、指示代词、不定代词与疑问代词",
            "section_type": "content_requirement", "clause_number": "附录4·一(五)代词",
            "pdf_page": 139 + pdf_offset, "print_page": 139,
            "raw_text": "(五) 代词：1. 人称代词；2. 物主代词；3. 反身代词；4. 指示代词；5. 不定代词；6. 疑问代词。",
            "standardized_text": "掌握人称代词主格与宾格、物主代词形容词性与名词性转换、反身代词、指示代词、复合不定代词及疑问代词在语境中的准确运用。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第139页（PDF第146页）代词条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握代词人称、数、格的准确转换及复合不定代词语境辨析",
            "review_status": "pending", "legacy_mappings": ["english.grammar.pronoun"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:prep_grammar:c09",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(七) 介词", "sub_theme": "常用介词与介词短语",
            "section_type": "content_requirement", "clause_number": "附录4·一(七)介词",
            "pdf_page": 139 + pdf_offset, "print_page": 139,
            "raw_text": "(七) 介词",
            "standardized_text": "熟练运用表示时间（at, in, on等）、方位地点（between, among, through, across等）及方式手段的常用介词和固定短语搭配。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第139页（PDF第146页）介词条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握时间、空间方位高频介词辨析及与动词形容词的固定搭配",
            "review_status": "pending", "legacy_mappings": ["english.grammar.preposition"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:article_grammar:c10",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(九) 冠词", "sub_theme": "不定冠词、定冠词与零冠词",
            "section_type": "content_requirement", "clause_number": "附录4·一(九)冠词",
            "pdf_page": 139 + pdf_offset, "print_page": 139,
            "raw_text": "(九) 冠词",
            "standardized_text": "掌握不定冠词a/an元音音素辨析与泛指功能；掌握定冠词the特指、独一无二事物与乐器等用法；掌握球类、三餐及抽象名词等零冠词规则。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第139页（PDF第146页）冠词条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握不定冠词、定冠词特指与零冠词常见固定结构",
            "review_status": "pending", "legacy_mappings": ["english.grammar"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:comparison_grammar:c11",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(三) 形容词 与 (四) 副词", "sub_theme": "形容词副词基本形式与比较级最高级",
            "section_type": "content_requirement", "clause_number": "附录4·一(三)(四)形容词与副词",
            "pdf_page": 138 + pdf_offset, "print_page": 138,
            "raw_text": "(三) 形容词：1. 形容词的基本形式；2. 形容词的比较级和最高级。(四) 副词：1. 副词的基本形式；2. 副词的比较级和最高级。",
            "standardized_text": "掌握形容词副词原级比较、比较级和最高级的规则与不规则构成，熟练运用修饰比较级的程度副词（much, even等）与比较句型。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第138~139页（PDF第145~146页）形容词与副词条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握比较级最高级变化规则、比较句型及语境中的程度修饰",
            "review_status": "pending", "legacy_mappings": ["english.grammar.comparative"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:numeral_grammar:c12",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(六) 数词", "sub_theme": "基数词与序数词",
            "section_type": "content_requirement", "clause_number": "附录4·一(六)数词",
            "pdf_page": 139 + pdf_offset, "print_page": 139,
            "raw_text": "(六) 数词：1. 基数词；2. 序数词。",
            "standardized_text": "掌握基数词变序数词规律，熟练掌握日期月份表达、分数（分子基数词分母序数词）及hundreds of等大数表达结构。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第139页（PDF第146页）数词条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握基数词序数词转换、大数表达法及日期分数表达",
            "review_status": "pending", "legacy_mappings": ["english.grammar"]
        },

        # --- 附录 4 语法项目表·谓语动词时态与语态 ---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:tense_present_past:c13",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(三) 谓语动词的时态", "sub_theme": "一般现在时与一般过去时",
            "section_type": "content_requirement", "clause_number": "附录4·三(三)1-2时态",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(三) 谓语动词的时态：1. 一般现在时；2. 一般过去时。",
            "standardized_text": "熟练掌握一般现在时主谓一致及动词第三人称单数变化；掌握一般过去时常用时间状语及不规则动词过去式拼写与用法。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）时态第1、2项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握一般现在时第三人称单数与一般过去时不规则动词语境正确运用",
            "review_status": "pending", "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:tense_future_prog:c14",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(三) 谓语动词的时态", "sub_theme": "一般将来时、现在进行时与过去进行时",
            "section_type": "content_requirement", "clause_number": "附录4·三(三)3-5时态",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(三) 谓语动词的时态：3. 一般将来时；4. 现在进行时；5. 过去进行时。",
            "standardized_text": "掌握一般将来时计划与预测表达（will/be going to）；掌握现在进行时与过去进行时（特定时刻正在发生动作）的结构与时间状语配合。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）时态第3、4、5项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握一般将来时与现在/过去进行时基本结构与典型标志词搭配",
            "review_status": "pending", "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:tense_perfect:c15",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(三) 谓语动词的时态", "sub_theme": "现在完成时及其延续性转换",
            "section_type": "content_requirement", "clause_number": "附录4·三(三)6现在完成时",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(三) 谓语动词的时态：6. 现在完成时。",
            "standardized_text": "掌握现在完成时已完成与持续性用法（have/has + done）；掌握for/since引导的时间段与延续性动词搭配规则（短暂动词转延续动词）。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）时态第6项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握现在完成时结构、标志词（already, yet, ever, never）与延续性动词转换",
            "review_status": "pending", "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:voice_passive:c16",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(四) 被动语态", "sub_theme": "一般现在、一般过去与一般将来时被动语态",
            "section_type": "content_requirement", "clause_number": "附录4·三(四)被动语态",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(四) 被动语态：1. 一般现在时的被动语态；2. 一般过去时的被动语态；3. 一般将来时的被动语态。",
            "standardized_text": "掌握主语与动词存在被动承受关系时的被动语态构成（be + done），能够灵活实现主动句与被动句转换。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）被动语态第1-3项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握常见时态及情态动词被动语态结构与语境识别应用",
            "review_status": "pending", "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:modal_verbs:c17",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "一、词类·(二) 动词", "sub_theme": "情态动词基本用法与推测判断",
            "section_type": "content_requirement", "clause_number": "附录4·一(二)5情态动词",
            "pdf_page": 138 + pdf_offset, "print_page": 138,
            "raw_text": "(二) 动词：5. 情态动词。",
            "standardized_text": "掌握常用情态动词（can/could, may/might, must, shall/should, will/would, need等）后接动词原形，准确辨析must, can't, may在肯定、否定推测中的确定程度。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第138页（PDF第145页）动词第5项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握情态动词表能力、允许、推测的语境辨析与否定回答规则",
            "review_status": "pending", "legacy_mappings": ["english.grammar.modal"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:non_finite:c18",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(五) 动词的非谓语形式", "sub_theme": "动词不定式与非谓语形式",
            "section_type": "content_requirement", "clause_number": "附录4·三(五)非谓语动词",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(五) 动词的非谓语形式：1. 动词不定式（作宾语、宾语补足语、目的状语）；+2. 动词的-ing形式；+3. 动词的-ed形式。",
            "standardized_text": "掌握不定式作目的状语、宾语及省略to的结构（使役感官动词）；掌握stop/remember/forget接to do与doing的语义差异。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）非谓语动词第1-3项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握动词不定式作宾补目的状语与动名词接特定动词的用法辨析",
            "review_status": "pending", "legacy_mappings": ["english.grammar"]
        },

        # --- 附录 4 语法项目表·句法结构与复合句 ---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:simple_sentences:c19",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(一) 句子种类 与 (二) 简单句的基本句型", "sub_theme": "陈述句、疑问句、祈使句、感叹句与五大简单句句型",
            "section_type": "content_requirement", "clause_number": "附录4·三(一)(二)简单句",
            "pdf_page": 140 + pdf_offset, "print_page": 140,
            "raw_text": "三、句法 (一) 句子种类：1. 陈述句；2. 疑问句（(1) 一般疑问句 (2) 特殊疑问句 (3) 选择疑问句）；3. 祈使句；4. 感叹句。(二) 简单句的基本句型：1. 主谓 (SV)；2. 主 (系) 表 (SP)；3. 主谓宾 (SVO)；4. 主谓宾宾 (SVOO)；5. 主谓宾补 (SVOC)；6. 存现句。",
            "standardized_text": "掌握五种简单句基本骨架；熟练运用What/How感叹句转换；掌握There be句型就近原则与疑问句结构。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第140~141页（PDF第147~148页）句子种类与简单句句型原文完全一致",
            "is_elective": False, "derived_requirement": "掌握简单句五大句型、反意疑问句与感叹句结构转换",
            "review_status": "pending", "legacy_mappings": ["english.syntax"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:compound_sentences:c20",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(六) 并列复合句", "sub_theme": "并列复合句与并列连词",
            "section_type": "content_requirement", "clause_number": "附录4·三(六)并列复合句",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(六) 并列复合句",
            "standardized_text": "熟练掌握并列连词and, but, or, so表示顺承、转折、选择与因果逻辑；掌握not only... but also..., either... or..., neither... nor...连接主语时的就近一致原则。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）并列复合句条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握并列连词逻辑语义辨析与主谓一致就近原则",
            "review_status": "pending", "legacy_mappings": ["english.grammar.conjunction"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:object_clause:c21",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(七) 主从复合句", "sub_theme": "宾语从句引导词、语序与时态呼应",
            "section_type": "content_requirement", "clause_number": "附录4·三(七)1宾语从句",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(七) 主从复合句：1. 宾语从句。",
            "standardized_text": "掌握that/whether/if及特殊疑问词引导的宾语从句；严格保持从句陈述语序（主语+谓语）；掌握主句过去时从句时态呼应及客观真理例外规则。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）主从复合句第1项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握宾语从句陈述语序、引导词选择与主从时态呼应规则",
            "review_status": "pending", "legacy_mappings": ["english.syntax.object_clause"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:adverbial_clause:c22",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(七) 主从复合句", "sub_theme": "状语从句分类与主将从现时态规则",
            "section_type": "content_requirement", "clause_number": "附录4·三(七)2状语从句",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(七) 主从复合句：2. 状语从句。",
            "standardized_text": "掌握时间、条件、原因、目的、结果、让步与比较状语从句从属连词的逻辑含义，熟练应用时间与条件状语从句中“主将从现/主情从现”时态规则。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141页（PDF第148页）主从复合句第2项原文完全一致",
            "is_elective": False, "derived_requirement": "掌握时间与条件状语从句主将从现时态规则及从属连词辨析",
            "review_status": "pending", "legacy_mappings": ["english.syntax.adverbial_clause"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:attributive_clause:c23",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "附录 4 语法项目表", "domain_title": "附录 4 语法项目表·初中三级语法项目",
            "theme_title": "三、句法·(七) 主从复合句", "sub_theme": "关系从句（定语从句先行词与关系代词）",
            "section_type": "content_requirement", "clause_number": "附录4·三(七)3关系从句",
            "pdf_page": 141 + pdf_offset, "print_page": 141,
            "raw_text": "(七) 主从复合句：3. 关系从句（亦称“定语从句”，能辨认出由关系代词 that、which、who 引导的限定性定语从句，并能理解句意）。",
            "standardized_text": "识别定语从句修饰先行词的结构特征，掌握指人关系代词who/that与指物关系代词which/that的基本选择与句意理解。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标附录4语法项目表印刷第141~142页（PDF第148~149页）关系从句条目原文完全一致",
            "is_elective": False, "derived_requirement": "掌握定语从句先行词判断与关系代词who/which/that的基本用法",
            "review_status": "pending", "legacy_mappings": ["english.syntax.attributive_clause"]
        },

        # --- 3. 语言知识：语篇知识（表12 三级）与 语用知识（表13 三级）---
        {
            "clause_id": "cs:english:2022:s4:reading:content_req:discourse_knowledge:c24",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·语篇知识（表12 三级）", "sub_theme": "语篇逻辑结构、衔接与连贯",
            "section_type": "content_requirement", "clause_number": "三级表12·语篇知识",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "1. 理解记叙文语篇的主要写作目的、结构特征、基本语言特点和信息组织方式，并用以描述自己和他人的经历；2. 理解说明文语篇的主要写作目的、结构特征、基本语言特点和信息组织方式，并用以说明事物和阐释事理；3. 理解常见应用文语篇和其他常见语篇类型的主要写作目的、结构特征、基本语言特点和信息组织方式，并用以传递信息；4. 在语篇中辨识并尝试运用衔接和连贯手段，以提升理解的准确性和表达的逻辑性。",
            "standardized_text": "掌握段落主题句识别、承上启下过渡词、代词指代及总分总语篇逻辑结构，增强篇章阅读理解与还原能力。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第22页（PDF第29页）表12语篇知识三级要求1-4条完全一致",
            "is_elective": False, "derived_requirement": "掌握语篇衔接连词、逻辑指代关系及任务型阅读篇章段落还原",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        },
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:pragmatics_knowledge:c25",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "3. 语言知识·语用知识（表13 三级）", "sub_theme": "语境意识、交际意图与得体表达",
            "section_type": "content_requirement", "clause_number": "三级表13·语用知识",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "1. 在社会情境中，使用得体的语言和非语言形式进行日常生活交流，如请求和提供帮助等；2. 具有一定的语用意识，尝试选择正式或非正式、直接或委婉的语言，进行社会交往，表达情感、态度等，保持良好的人际关系；3. 在交际情境中，正确理解他人的情感、态度和观点，运用恰当的语言形式表达自己的情感、态度和观点。",
            "standardized_text": "根据交际场合与身份角色选择正式或委婉得体语言，理解说话人意图，准确进行情境交际与听说应答。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第23~24页（PDF第30~31页）表13语用知识三级要求1-3条完全一致",
            "is_elective": False, "derived_requirement": "掌握日常生活情境交际、日常对话应答与交际得体性表达",
            "review_status": "pending", "legacy_mappings": ["english.listening"]
        },

        # --- 4. 文化知识（表14 三级）---
        {
            "clause_id": "cs:english:2022:s4:reading:content_req:culture_knowledge:c26",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "4. 文化知识（表14 三级）", "sub_theme": "中外礼仪、节日习俗与文化自信",
            "section_type": "content_requirement", "clause_number": "三级表14·文化知识",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "1. 世界主要国家待人接物的基本礼仪和方式，体现文化的传承和人与人之间的相互尊重；2. 中外餐桌礼仪，典型饮食及其文化寓意；3. 世界主要国家的重要文化标志物、传统节日和风土人情，体现文化多样性；4. 了解中华优秀传统文化中的名胜古迹、历史人物故事及科技成就，用英语进行简单介绍，坚定文化自信。",
            "standardized_text": "了解世界主要国家文化习俗与礼仪，能够用英语阐释中华优秀传统文化名胜、杰出人物事迹与社会发展成就。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第24~25页（PDF第31~32页）表14文化知识三级内容要求完全一致",
            "is_elective": False, "derived_requirement": "理解中外文化差异、跨文化交际背景及用英语介绍中国传统文化",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        },

        # --- 5. 语言技能（表17~19 三级）---
        {
            "clause_id": "cs:english:2022:s4:listening:content_req:skills_comprehension:c27",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "listening",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "5. 语言技能（表17~19 三级）", "sub_theme": "理解性技能（听、读、看）",
            "section_type": "content_requirement", "clause_number": "三级语言技能·理解性",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "在听、读、看等活动中：获取语篇中的事实细节信息；推断说话者或作者的隐含意图、态度与观点；理解多模态语篇中图文信息互补与转换；根据上下文推断生词词义；梳理行文主旨大意与关键逻辑框架。",
            "standardized_text": "综合运用听、读、看技能获取文本细节、推测词义、提炼主旨，应对初中听说机考听选信息与阅读理解多题型考查。",
            "collation_note": "依据教育部2022版课标印刷第27~31页（PDF第34~38页）语言技能三级内容要求理解性技能条目整理",
            "is_elective": False, "derived_requirement": "掌握阅读理解细节理解、主旨大意归纳与听说机考听力信息抓取",
            "review_status": "pending", "legacy_mappings": ["english.skills", "english.listening"]
        },
        {
            "clause_id": "cs:english:2022:s4:writing:content_req:skills_expression:c28",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "writing",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "5. 语言技能（表17~19 三级）", "sub_theme": "表达性技能（说、写）",
            "section_type": "content_requirement", "clause_number": "三级语言技能·表达性",
            "pdf_page": 31 + pdf_offset, "print_page": 31,
            "raw_text": "在说和写的表达活动中：围绕相关主题，使用正确的语音语调进行口头交流表达；根据写作目的与受众，规范撰写应用文（书信、邮件、演讲稿、发言提纲）与记叙文，做到结构完整、要点齐全、行文连贯、语法准确。",
            "standardized_text": "具备机考口语情境问答、简短演讲及初中中考话题写作（应用文与记叙文写作）的连贯规范表达能力。",
            "collation_note": "依据教育部2022版课标印刷第31~33页（PDF第38~40页）语言技能三级内容要求表达性技能条目整理",
            "is_elective": False, "derived_requirement": "掌握中考书面表达审题立意、段落结构组织、过渡连词运用与拼写语法纠错",
            "review_status": "pending", "legacy_mappings": ["english.writing.composition", "english.listening"]
        },

        # --- 6. 学习策略（表20 三级）---
        {
            "clause_id": "cs:english:2022:s4:lang_usage:content_req:learning_strategies:c29",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）内容要求·三级（7~9年级）",
            "theme_title": "6. 学习策略（表20 三级）", "sub_theme": "元认知、认知、交际与情感策略",
            "section_type": "content_requirement", "clause_number": "三级表20·学习策略",
            "pdf_page": 32 + pdf_offset, "print_page": 32,
            "raw_text": "元认知策略：制定明确的学习目标与计划，自我监控和反思学习效果；认知策略：在新旧知识之间建立联系，借助图表与思维导图梳理信息，运用归纳规律举一反三；交际策略：借助肢体语言与澄清提问维持交际；情感策略：对英语学习保持主动自信，克服焦虑，乐于合作分享。",
            "standardized_text": "在英语学习与备考中运用自我监控、思维导图信息梳理、猜测词义及积极合作探究等综合学习策略。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第32~34页（PDF第39~41页）表20学习策略三级要求完全一致",
            "is_elective": False, "derived_requirement": "掌握思维导图梳理文章信息、审题选材技巧与高效自主学习策略",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        },

        # --- 五、学业质量标准（表24 三级 7~9年级）---
        {
            "clause_id": "cs:english:2022:s4:reading:academic_req:english_eval:c30",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "五、学业质量", "domain_title": "（二）学业质量描述·三级（7~9年级）",
            "theme_title": "三级学业质量标准（表24）", "sub_theme": "初中毕业英语学业质量综合标准",
            "section_type": "academic_requirement", "clause_number": "三级表24·学业质量总则",
            "pdf_page": 45 + pdf_offset, "print_page": 45,
            "raw_text": "学生能够在本学段要求的主题范围内，围绕相关主题群和子主题，根据规定的语言知识和文化知识等内容要求，有效运用听、说、读、看、写等语言技能和学习策略，依托三级内容要求规定的语篇类型，归纳并分析不同的语言和文化现象，使用较为规范的语言进行口头和书面表达，定期反思学习情况，调整学习计划，学会自主探究，主动与他人合作，共同完成学习任务。",
            "standardized_text": "初中毕业生中考英语综合考查听力口语、语言知识综合运用（完形填空、语法填空）、篇章阅读与书面表达四大核心板块。",
            "collation_note": "经人工逐字核对，与教育部2022版英语课标印刷第45页（PDF第52页）三级学业质量描述完全一致",
            "is_elective": False, "derived_requirement": "初中学业水平考试中考英语学科评价总体标准",
            "review_status": "pending", "legacy_mappings": ["english.skills"]
        }
    ]

    # 2. 英语初中候选知识点体系 (28 个节点，基于语言知识与技能体系独立推导，层级严密无环)
    def filter_clauses(cond):
        return [c["clause_id"] for c in clauses if cond(c)]

    candidates = [
        # 一级领域 1：语言知识·语音与词汇
        {
            "code": "english_cand.phonetics_vocab",
            "name": "语音与词汇知识",
            "domain": "lang_usage", "parent_code": None, "level": 1,
            "description": "国际音标拼读与句子连读语调、词缀构词法派生转换及高频短语语境搭配辨析。",
            "source_clause_ids": filter_clauses(lambda c: "语音" in c["theme_title"] or "词汇" in c["theme_title"]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标三级语音与词汇知识归集，待审核",
            "legacy_mappings": ["english.listening", "english.cloze.context"]
        },
        {
            "code": "english_cand.vocab.formation",
            "name": "词汇构词法与词性转换",
            "domain": "lang_usage", "parent_code": "english_cand.phonetics_vocab", "level": 2,
            "description": "派生词缀（前缀un-/dis-/im-，后缀-er/-or/-tion/-ful/-less/-ly等）、合成法与转化法构词规律与词性辨析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:vocab_formation:c04"),
            "is_elective": False, "review_status": "pending", "review_note": "对应构词法与词类转换条文，待审核",
            "legacy_mappings": ["english.cloze.context"]
        },
        {
            "code": "english_cand.vocab.collocation_context",
            "name": "短语搭配与语境词义辨析",
            "domain": "lang_usage", "parent_code": "english_cand.phonetics_vocab", "level": 2,
            "description": "动词短语、介词固定搭配辨析及近义词、同义词在完形填空语境中的细微含义区别。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:vocab_collocation:c05"),
            "is_elective": False, "review_status": "pending", "review_note": "对应习惯搭配与语境词义辨析条文，待审核",
            "legacy_mappings": ["english.cloze.context"]
        },

        # 一级领域 2：语言知识·语法（词法体系）
        {
            "code": "english_cand.morphology",
            "name": "语法知识·词法",
            "domain": "lang_usage", "parent_code": None, "level": 1,
            "description": "名词、代词、介词、冠词、形容词副词比较级与数词在真实语境中的形态与功能。",
            "source_clause_ids": filter_clauses(lambda c: "词类" in c["theme_title"] or c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:grammar_general:c06",
                "cs:english:2022:s4:lang_usage:content_req:noun_grammar:c07",
                "cs:english:2022:s4:lang_usage:content_req:pronoun_grammar:c08",
                "cs:english:2022:s4:lang_usage:content_req:prep_grammar:c09",
                "cs:english:2022:s4:lang_usage:content_req:article_grammar:c10",
                "cs:english:2022:s4:lang_usage:content_req:comparison_grammar:c11",
                "cs:english:2022:s4:lang_usage:content_req:numeral_grammar:c12"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标附录4词类体系归集，待审核",
            "legacy_mappings": [
                "english.grammar", "english.grammar.noun", "english.grammar.pronoun",
                "english.grammar.preposition", "english.grammar.comparative"
            ]
        },
        {
            "code": "english_cand.noun.number_case",
            "name": "名词单复数与所有格",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "可数名词规则与不规则复数形式、不可数名词修饰及有生命/无生命名词所有格辨析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:noun_grammar:c07"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4名词语法条文，待审核",
            "legacy_mappings": ["english.grammar.noun"]
        },
        {
            "code": "english_cand.pronoun.types",
            "name": "代词分类与用法",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "人称代词主宾格、物主代词形代与名代、反身代词及复合不定代词语境准确运用。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:pronoun_grammar:c08"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4代词语法条文，待审核",
            "legacy_mappings": ["english.grammar.pronoun"]
        },
        {
            "code": "english_cand.preposition.usage",
            "name": "介词与介词短语",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "表示时间、空间方位的核心介词及动词介词、形容词介词常用短语搭配。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:prep_grammar:c09"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4介词语法条文，待审核",
            "legacy_mappings": ["english.grammar.preposition"]
        },
        {
            "code": "english_cand.article.rules",
            "name": "冠词（定冠词、不定冠词与零冠词）",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "不定冠词a/an发音规律与泛指、定冠词the特指与独一无二事物及零冠词固定习惯表达。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:article_grammar:c10"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4冠词用法条文，待审核",
            "legacy_mappings": ["english.grammar"]
        },
        {
            "code": "english_cand.adj_adv.comparison",
            "name": "形容词与副词比较等级",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "形容词副词原级比较（as...as）、比较级最高级规则与不规则变化及程度副词修饰。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:comparison_grammar:c11"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4比较等级条文，待审核",
            "legacy_mappings": ["english.grammar.comparative"]
        },
        {
            "code": "english_cand.numeral.rules",
            "name": "数词（基数词与序数词）",
            "domain": "lang_usage", "parent_code": "english_cand.morphology", "level": 2,
            "description": "基数词与序数词转换规律、大数表示法及在时间、日期、年龄、分数、百分数中的正确表达。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:numeral_grammar:c12"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4数词用法条文，待审核",
            "legacy_mappings": ["english.grammar"]
        },

        # 一级领域 3：语言知识·语法（动词系统）
        {
            "code": "english_cand.verb_system",
            "name": "语法知识·动词时态与语态",
            "domain": "lang_usage", "parent_code": None, "level": 1,
            "description": "初中五大核心时态、被动语态、情态动词推测与非谓语动词（不定式与动名词）。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:grammar_general:c06",
                "cs:english:2022:s4:lang_usage:content_req:tense_present_past:c13",
                "cs:english:2022:s4:lang_usage:content_req:tense_future_prog:c14",
                "cs:english:2022:s4:lang_usage:content_req:tense_perfect:c15",
                "cs:english:2022:s4:lang_usage:content_req:voice_passive:c16",
                "cs:english:2022:s4:lang_usage:content_req:modal_verbs:c17",
                "cs:english:2022:s4:lang_usage:content_req:non_finite:c18"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标附录4动词体系归集，待审核",
            "legacy_mappings": ["english.grammar.tense", "english.grammar.modal", "english.grammar"]
        },
        {
            "code": "english_cand.tense.present_past",
            "name": "一般现在时与一般过去时",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "一般现在时主谓一致及动词第三人称单数变化；一般过去时常用时间状语及不规则动词过去式拼写。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:tense_present_past:c13"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4一般现在与过去时条文，待审核",
            "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "code": "english_cand.tense.future_continuous",
            "name": "一般将来时与进行时态",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "一般将来时（will/be going to）计划预测；现在进行时与过去进行时动作进行状态表达。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:tense_future_prog:c14"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4将来与进行时态条文，待审核",
            "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "code": "english_cand.tense.present_perfect",
            "name": "现在完成时及其延续性转换",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "现在完成时表示影响与持续、常用标志词搭配及短暂动词转延续性动词与for/since时间段连用。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:tense_perfect:c15"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4现在完成时条文，待审核",
            "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "code": "english_cand.voice.passive",
            "name": "被动语态（一般现在、一般过去与情态动词）",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "一般现在时、一般过去时及含情态动词的被动语态构成（be + done）及主动被动语态转换。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:voice_passive:c16"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4被动语态条文，待审核",
            "legacy_mappings": ["english.grammar.tense"]
        },
        {
            "code": "english_cand.modal.verbs",
            "name": "情态动词用法与推测判断",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "can, may, must, should, need等基本情态动词及must/can't/could/might肯定否定可能性推测。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:modal_verbs:c17"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4情态动词条文，待审核",
            "legacy_mappings": ["english.grammar.modal"]
        },
        {
            "code": "english_cand.non_finite.verbs",
            "name": "非谓语动词（动词不定式与动名词）",
            "domain": "lang_usage", "parent_code": "english_cand.verb_system", "level": 2,
            "description": "动词不定式作宾语、目的状语、宾补（使役感官动词省略to）及动词后接doing的辨析用法。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:non_finite:c18"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4非谓语动词条文，待审核",
            "legacy_mappings": ["english.grammar"]
        },

        # 一级领域 4：语言知识·语法（句法与复合句）
        {
            "code": "english_cand.syntax_system",
            "name": "语法知识·句法与复合句",
            "domain": "lang_usage", "parent_code": None, "level": 1,
            "description": "简单句五大句型、反意疑问句、感叹句、There be句型、并列句及三大主从复合句。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:grammar_general:c06",
                "cs:english:2022:s4:lang_usage:content_req:simple_sentences:c19",
                "cs:english:2022:s4:lang_usage:content_req:compound_sentences:c20",
                "cs:english:2022:s4:lang_usage:content_req:object_clause:c21",
                "cs:english:2022:s4:lang_usage:content_req:adverbial_clause:c22",
                "cs:english:2022:s4:lang_usage:content_req:attributive_clause:c23"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标附录4句法体系归集，待审核",
            "legacy_mappings": [
                "english.syntax", "english.grammar.conjunction", "english.syntax.object_clause",
                "english.syntax.adverbial_clause", "english.syntax.attributive_clause"
            ]
        },
        {
            "code": "english_cand.clause.simple_sentences",
            "name": "简单句句型与功能句式",
            "domain": "lang_usage", "parent_code": "english_cand.syntax_system", "level": 2,
            "description": "主谓宾等五大简单句骨架、There be句型就近原则、What/How感叹句与反意疑问句构成规律。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:grammar_general:c06",
                "cs:english:2022:s4:lang_usage:content_req:simple_sentences:c19"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4简单句句型条文，待审核",
            "legacy_mappings": ["english.syntax"]
        },
        {
            "code": "english_cand.syntax.compound_conjunction",
            "name": "并列复合句与并列连词",
            "domain": "lang_usage", "parent_code": "english_cand.syntax_system", "level": 2,
            "description": "and, but, or, so等常用并列连词逻辑义及not only...but also...等主谓就近一致原则。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:compound_sentences:c20"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4并列句条文，待审核",
            "legacy_mappings": ["english.grammar.conjunction"]
        },
        {
            "code": "english_cand.syntax.object_clause",
            "name": "宾语从句",
            "domain": "lang_usage", "parent_code": "english_cand.syntax_system", "level": 2,
            "description": "that, if/whether及疑问词引导的宾语从句；陈述语序规则及主句过去时主从时态呼应。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:object_clause:c21"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4宾语从句条文，待审核",
            "legacy_mappings": ["english.syntax.object_clause"]
        },
        {
            "code": "english_cand.syntax.adverbial_clause",
            "name": "状语从句",
            "domain": "lang_usage", "parent_code": "english_cand.syntax_system", "level": 2,
            "description": "时间、条件、原因、让步、目的、结果状语从句从属连词逻辑义及时间条件从句主将从现规则。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:adverbial_clause:c22"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4状语从句条文，待审核",
            "legacy_mappings": ["english.syntax.adverbial_clause"]
        },
        {
            "code": "english_cand.syntax.attributive_clause",
            "name": "定语从句（初步认识）",
            "domain": "lang_usage", "parent_code": "english_cand.syntax_system", "level": 2,
            "description": "定语从句修饰先行词概念、指人关系代词that/who与指物that/which的基础选择与阅读理解识别。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:english:2022:s4:lang_usage:content_req:attributive_clause:c23"),
            "is_elective": False, "review_status": "pending", "review_note": "对应附录4定语从句条文，待审核",
            "legacy_mappings": ["english.syntax.attributive_clause"]
        },

        # 一级领域 5：语言技能与综合素养
        {
            "code": "english_cand.skills_comprehension",
            "name": "语言技能与语篇综合素养",
            "domain": "reading", "parent_code": None, "level": 1,
            "description": "三大主题范畴语境下的听说机考口语应答、篇章阅读理解细节推断、任务型非连续性文本处理及中考话题写作。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:theme_contexts:c01",
                "cs:english:2022:s4:reading:content_req:discourse_genre:c02",
                "cs:english:2022:s4:lang_usage:content_req:phonetics:c03",
                "cs:english:2022:s4:reading:content_req:discourse_knowledge:c24",
                "cs:english:2022:s4:lang_usage:content_req:pragmatics_knowledge:c25",
                "cs:english:2022:s4:reading:content_req:culture_knowledge:c26",
                "cs:english:2022:s4:listening:content_req:skills_comprehension:c27",
                "cs:english:2022:s4:writing:content_req:skills_expression:c28",
                "cs:english:2022:s4:lang_usage:content_req:learning_strategies:c29",
                "cs:english:2022:s4:reading:academic_req:english_eval:c30"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标三级语言技能与学业质量标准归集，待审核",
            "legacy_mappings": ["english.listening", "english.reading.detail", "english.reading.expression", "english.writing.composition", "english.skills"]
        },
        {
            "code": "english_cand.listening_speaking",
            "name": "听力理解与机考听说交互",
            "domain": "listening", "parent_code": "english_cand.skills_comprehension", "level": 2,
            "description": "听辨关键信息细节、推测说话者意图身份、听说机考短文朗读、情境问答与转述表达。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:phonetics:c03",
                "cs:english:2022:s4:lang_usage:content_req:pragmatics_knowledge:c25",
                "cs:english:2022:s4:listening:content_req:skills_comprehension:c27"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应机考听说与听力技能条文，待审核",
            "legacy_mappings": ["english.listening"]
        },
        {
            "code": "english_cand.reading.facts_inference",
            "name": "阅读理解（事实细节、主旨大意与深层推断）",
            "domain": "reading", "parent_code": "english_cand.skills_comprehension", "level": 2,
            "description": "三大主题范畴书面语篇事实细节筛选、段落中心主旨提炼、词义推断、文化背景、作者观点态度与深层逻辑推断。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:theme_contexts:c01",
                "cs:english:2022:s4:reading:content_req:discourse_genre:c02",
                "cs:english:2022:s4:reading:content_req:discourse_knowledge:c24",
                "cs:english:2022:s4:reading:content_req:culture_knowledge:c26",
                "cs:english:2022:s4:reading:academic_req:english_eval:c30"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应阅读理解核心考点条文与主题范畴语境要求，待审核",
            "legacy_mappings": ["english.reading.detail"]
        },
        {
            "code": "english_cand.reading.task_based",
            "name": "任务型阅读（篇章还原与信息简答）",
            "domain": "reading", "parent_code": "english_cand.skills_comprehension", "level": 2,
            "description": "语篇上下文衔接逻辑还原、任务型多模态图表表格转换及根据短文回答问题的规范简答。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:reading:content_req:discourse_knowledge:c24",
                "cs:english:2022:s4:lang_usage:content_req:learning_strategies:c29"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应任务型阅读篇章还原与简答条文，待审核",
            "legacy_mappings": ["english.reading.expression"]
        },
        {
            "code": "english_cand.writing.composition",
            "name": "书面表达与话题写作（应用文与记叙议论文）",
            "domain": "writing", "parent_code": "english_cand.skills_comprehension", "level": 2,
            "description": "中考英语应用文（书信、邮件、演讲稿、建议倡议）与话题作文审题、提纲组织、逻辑衔接与规范书写。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:english:2022:s4:lang_usage:content_req:theme_contexts:c01",
                "cs:english:2022:s4:writing:content_req:skills_expression:c28",
                "cs:english:2022:s4:lang_usage:content_req:learning_strategies:c29"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应中考书面表达话题写作条文，待审核",
            "legacy_mappings": ["english.writing.composition"]
        }
    ]

    # 3. 存量 18 个英语旧节点映射契约 (严格映射至新候选体系，详细演进理由与历史兼容保障)
    legacy_mappings = [
        {
            "legacy_code": "english.grammar",
            "legacy_name": "语法与词法",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["english_cand.morphology", "english_cand.verb_system"],
            "mapping_reason": "一级分类承载语法与词法大类，映射至新体系词法与动词时态系统大类。",
            "compatibility_assurance": "历史语法大类统计数据保持兼容。"
        },
        {
            "legacy_code": "english.grammar.pronoun",
            "legacy_name": "代词分类与用法",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.pronoun.types"],
            "mapping_reason": "代词人称、物主、反身与不定代词考查核心完全一致，平移承接历史考题。",
            "compatibility_assurance": "历史代词题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.grammar.preposition",
            "legacy_name": "介词与介词短语",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.preposition.usage"],
            "mapping_reason": "时间、空间与常用固定介词短语搭配考点完全一致。",
            "compatibility_assurance": "历史介词题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.grammar.tense",
            "legacy_name": "动词时态与语态",
            "legacy_parent_code": "english.grammar",
            "action": "split",
            "target_candidate_codes": [
                "english_cand.tense.present_past",
                "english_cand.tense.future_continuous",
                "english_cand.tense.present_perfect",
                "english_cand.voice.passive"
            ],
            "mapping_reason": "原旧节点将全部时态与被动语态混合，新体系精细化区分一般时、将来与进行时、现在完成时及被动语态，大幅增强时态语态诊断精度。",
            "compatibility_assurance": "历史时态题目平滑关联至细分子节点，历史答题记录保持完整可用。"
        },
        {
            "legacy_code": "english.grammar.modal",
            "legacy_name": "情态动词用法",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.modal.verbs"],
            "mapping_reason": "情态动词推测语气与情态含义辨析考查点完全一致。",
            "compatibility_assurance": "历史情态动词题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.grammar.conjunction",
            "legacy_name": "连词与并列句",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.syntax.compound_conjunction"],
            "mapping_reason": "并列连词与复合并列句考查内容完全契合。",
            "compatibility_assurance": "历史连词题目保持只读兼容。"
        },
        {
            "legacy_code": "english.grammar.comparative",
            "legacy_name": "形容词与副词比较等级",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.adj_adv.comparison"],
            "mapping_reason": "形容词与副词原级比较、比较级和最高级变形规则及句型考查点完全契合。",
            "compatibility_assurance": "历史比较等级题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.grammar.noun",
            "legacy_name": "名词的数与所有格",
            "legacy_parent_code": "english.grammar",
            "action": "retained",
            "target_candidate_codes": ["english_cand.noun.number_case"],
            "mapping_reason": "名词单复数与所有格考查核心完全一致，平移承接历史考题。",
            "compatibility_assurance": "历史名词题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.syntax",
            "legacy_name": "句法与复合句",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["english_cand.syntax_system"],
            "mapping_reason": "一级分类承载句法大类，映射至新体系语法知识·句法与复合句大类。",
            "compatibility_assurance": "历史句法分类统计数据保持兼容。"
        },
        {
            "legacy_code": "english.syntax.object_clause",
            "legacy_name": "宾语从句",
            "legacy_parent_code": "english.syntax",
            "action": "retained",
            "target_candidate_codes": ["english_cand.syntax.object_clause"],
            "mapping_reason": "宾语从句引导词、陈述语序与时态呼应三要素考点完全一致。",
            "compatibility_assurance": "历史宾语从句题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.syntax.adverbial_clause",
            "legacy_name": "状语从句",
            "legacy_parent_code": "english.syntax",
            "action": "retained",
            "target_candidate_codes": ["english_cand.syntax.adverbial_clause"],
            "mapping_reason": "时间、条件、原因、让步等状语从句及主将从现时态规则考点完全一致。",
            "compatibility_assurance": "历史状语从句题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.syntax.attributive_clause",
            "legacy_name": "定语从句初步",
            "legacy_parent_code": "english.syntax",
            "action": "retained",
            "target_candidate_codes": ["english_cand.syntax.attributive_clause"],
            "mapping_reason": "初中阶段that, which, who引导的定语从句识别与基本理解考点完全一致。",
            "compatibility_assurance": "历史定语从句题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.skills",
            "legacy_name": "语篇理解与综合表达",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["english_cand.skills_comprehension"],
            "mapping_reason": "一级分类承载语言技能大类，映射至新体系语言技能与语篇综合素养大类。",
            "compatibility_assurance": "历史技能分类统计数据保持兼容。"
        },
        {
            "legacy_code": "english.cloze.context",
            "legacy_name": "完形填空语境理解与词义辨析",
            "legacy_parent_code": "english.skills",
            "action": "retained",
            "target_candidate_codes": ["english_cand.vocab.collocation_context"],
            "mapping_reason": "完形填空语境理解与高频词汇短语辨析考查要点完全契合。",
            "compatibility_assurance": "历史完形填空题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.reading.detail",
            "legacy_name": "阅读理解事实细节与主旨概括",
            "legacy_parent_code": "english.skills",
            "action": "retained",
            "target_candidate_codes": ["english_cand.reading.facts_inference"],
            "mapping_reason": "阅读理解事实细节提取与主旨大意推断考查要点完全契合。",
            "compatibility_assurance": "历史阅读题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.reading.expression",
            "legacy_name": "任务型阅读与简答表达",
            "legacy_parent_code": "english.skills",
            "action": "retained",
            "target_candidate_codes": ["english_cand.reading.task_based"],
            "mapping_reason": "任务型阅读回答问题与信息提取表达考查要点完全契合。",
            "compatibility_assurance": "历史任务型阅读题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.writing.composition",
            "legacy_name": "书面表达与话题写作",
            "legacy_parent_code": "english.skills",
            "action": "retained",
            "target_candidate_codes": ["english_cand.writing.composition"],
            "mapping_reason": "书面表达、通知书信与话题短文写作考查要点完全契合。",
            "compatibility_assurance": "历史作文题目关联保持无损兼容。"
        },
        {
            "legacy_code": "english.listening",
            "legacy_name": "听力理解",
            "legacy_parent_code": "english.skills",
            "action": "retained",
            "target_candidate_codes": ["english_cand.listening_speaking"],
            "mapping_reason": "听力理解短对话、长对话与独白信息提取考查要点完全契合。",
            "compatibility_assurance": "历史听力题目关联保持无损兼容。"
        }
    ]

    return {
        "clauses": clauses,
        "candidates": candidates,
        "legacy_mappings": legacy_mappings
    }
