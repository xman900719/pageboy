# -*- coding: utf-8 -*-
"""
语文学科官方课程标准初中条款全集、候选知识体系与存量考点映射构建器。
依据教育部《义务教育语文课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-CHINESE）初中第四学段要求。
"""

from __future__ import annotations


def build_chinese_data():
    source_id = "MOE-2022-CHINESE"
    subject = "chinese"
    stage = "stage4"
    pdf_offset = 7  # 印刷第1页对应 PDF 物理第8页

    # 1. 语文课程标准第四学段全量条款集合 (覆盖六大学习任务群、学段目标与第四学段学业质量标准)
    clauses = [
        # --- 课程目标·学段要求（第四学段 7~9年级）---
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:goals:character_accumulation:c00a",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "识字与写字",
            "section_type": "content_requirement", "clause_number": "学段要求·识字写字①",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "能熟练地使用字典、词典独立识字，会用多种检字方法。累计认识常用汉字3500个左右。",
            "standardized_text": "熟练掌握音序检字法与部首检字法，能借助工具书独立识字，累计掌握3500个初中常用汉字识字量。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第14页（PDF第21页）第四学段识字与写字要求第1条完全一致",
            "is_elective": False, "derived_requirement": "运用工具书独立识字，掌握初中3500常用字字形与字音",
            "review_status": "pending", "legacy_mappings": ["chinese.base.character"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:goals:handwriting_norm:c00b",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "识字与写字",
            "section_type": "content_requirement", "clause_number": "学段要求·识字写字②",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "写字姿势正确，保持良好的书写习惯。在使用硬笔熟练地书写正楷字的基础上，学写规范、通行的行楷字，提高书写的速度。临摹、欣赏名家书法，体会书法的审美价值。",
            "standardized_text": "保持规范硬笔书写姿势，熟练书写正楷字与通行行楷字，提高书写流利度与规范性，具备名家书法审美意识。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第14页（PDF第21页）第四学段识字与写字要求第2条完全一致",
            "is_elective": False, "derived_requirement": "规范端正整洁书写汉字，掌握书法基础审美与临摹常识",
            "review_status": "pending", "legacy_mappings": ["chinese.base.character", "chinese.base.calligraphy"]
        },

        # --- 基础型学习任务群：语言文字积累与梳理 ---
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:phonetics:c01",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "语言文字文化内涵与实践活动",
            "section_type": "content_requirement", "clause_number": "积累与梳理四级①",
            "pdf_page": 21 + pdf_offset, "print_page": 21,
            "raw_text": "在语言文字运用情境中，发现、感受和表现语言文字的魅力。围绕汉字、书法、成语典故、对联、诗文等方面内容，策划并开展语文学习、展示和交流活动，加深对语言文字及其文化内涵的认识和理解。",
            "standardized_text": "在具体情境中辨析字音字义，探究语言文字运用规律，围绕汉字、成语典故与诗文开展学习展示活动。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第21页（PDF第28页）基础型学习任务群第四学段第(1)条完全一致",
            "is_elective": False, "derived_requirement": "辨析字音，掌握统编教材常见多音字、多音多义字与形声字易错读音，规范使用汉语拼音",
            "review_status": "pending", "legacy_mappings": ["chinese.base.phonetics"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:character:c02",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "语言现象梳理与语法修辞规律",
            "section_type": "content_requirement", "clause_number": "积累与梳理四级②",
            "pdf_page": 21 + pdf_offset, "print_page": 21,
            "raw_text": "梳理学过的语言现象，欣赏优秀作品的语言表达技巧，初步探究语言文字的运用规律。学习按照词类梳理字词，学习整理典型的语法、修辞应用实例。",
            "standardized_text": "按照词类梳理字词，掌握汉字字形结构规律，准确辨析字形，纠正常见音近、形近、义混错别字。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第21页（PDF第28页）基础型学习任务群第四学段第(2)条完全一致",
            "is_elective": False, "derived_requirement": "精准识别与订正各类常见错别字，分类梳理字词与语法修辞实例",
            "review_status": "pending", "legacy_mappings": ["chinese.base.character"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:vocabulary:c03",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "词语积累与典故运用",
            "section_type": "teaching_hint", "clause_number": "积累与梳理教学提示③",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "诵读、积累与梳理，重在培养兴趣、语感和习惯。引导学生增强语言积累和梳理的意识，教给学生语言积累和梳理的方法，注重积累、梳理与运用相结合。诵读材料要选择脍炙人口的千古名篇和名言名句，既要有文化内涵，又要短小精悍，朗朗上口。提倡日积月累，不要贪多求快，提倡熟读成诵，不要死记硬背。引导学生借助信息技术等多种方式汇总、梳理自己积累的语言材料，建立自己的创意语言资料库，并能学以致用。",
            "standardized_text": "分类整理成语典故与名句名篇，准确理解词语在具体语境中的感情色彩、词义与搭配，学以致用。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第22页（PDF第29页）教学提示第(3)条完全一致",
            "is_elective": False, "derived_requirement": "掌握词语与成语在特定语境中的语义辨析、褒贬色彩与得体运用",
            "review_status": "pending", "legacy_mappings": ["chinese.base.idiom"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:syntax:c04",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "语法修辞实例与病句修改",
            "section_type": "teaching_hint", "clause_number": "积累与梳理教学提示④",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "语音、文字、词汇、语法、修辞等方面的知识，要避免围绕相关知识的概念、脱离实际运用进行机械训练。在教学中应根据语言文字运用的实际需要，从遇到的具体语言实例出发进行指导。",
            "standardized_text": "从语言运用实际实例出发，掌握语法修辞规律，辨析搭配不当、成分残缺赘余、语序不当、句式杂糅等病句并规范修改。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第22页（PDF第29页）教学提示第(4)条完全一致",
            "is_elective": False, "derived_requirement": "从具体语言实例出发辨析修改六大常见病句，掌握常见修辞手法表达效果",
            "review_status": "pending", "legacy_mappings": ["chinese.base.grammar"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:punctuation:c05",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "标点符号规范运用评价",
            "section_type": "teaching_hint", "clause_number": "积累与梳理教学提示⑤",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "识字评价要考察学生认清字形、读准字音、掌握汉字基本意义的情况，在具体语言环境中运用汉字的能力，借助字典、词典等工具书查检字词的能力，帮助学生养成写规范字的习惯，减少错别字。第一、第二学段应多关注学生主动识字的兴趣，第三、第四学段要重视考察学生独立识字的能力。写字评价要考察学生对要求“会写”的字的掌握情况，重视书写的正确、端正、整洁，在此基础上，逐步要求书写流利。语文知识的概念不作为考试内容。",
            "standardized_text": "考察在具体语境中准确运用汉字、工具书查检及规范使用标点符号能力，避免死记硬背语文知识概念。",
            "collation_note": "经人工逐字核对，与教育部2022年版语文课程标准原件第23页（PDF第30页）教学提示第(5)条完全一致",
            "is_elective": False, "derived_requirement": "掌握顿号、逗号、分号、冒号、引号、书名号等常用标点符号在具体语境中的规范运用与纠错",
            "review_status": "pending", "legacy_mappings": ["chinese.base.punctuation"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:culture:c06",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "文化常识与书法鉴赏",
            "section_type": "content_requirement", "clause_number": "积累与梳理四级·文化书法",
            "pdf_page": 21 + pdf_offset, "print_page": 21,
            "raw_text": "在语言文字运用情境中，发现、感受和表现语言文字的魅力。围绕汉字、书法、成语典故、对联、诗文等方面内容，策划并开展语文学习、展示和交流活动，加深对语言文字及其文化内涵的认识和理解。",
            "standardized_text": "掌握统编教材涉及的中国传统文化常识、文学文体常识与名家书法艺术特征，加深文化内涵认识与理解。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第21页原件一致",
            "is_elective": False, "derived_requirement": "掌握节气民俗、古代称谓、文学流派与名家书法作品鉴赏常识",
            "review_status": "pending", "legacy_mappings": ["chinese.base.literature", "chinese.base.calligraphy"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:content_req:expression:c07",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "四、课程内容", "domain_title": "（一）基础型学习任务群",
            "theme_title": "1. 语言文字积累与梳理", "sub_theme": "情境表达与综合性学习",
            "section_type": "content_requirement", "clause_number": "积累与梳理四级·实践活动",
            "pdf_page": 21 + pdf_offset, "print_page": 21,
            "raw_text": "在语言文字运用情境中，发现、感受和表现语言文字的魅力。围绕汉字、书法、成语典故、对联、诗文等方面内容，策划并开展语文学习、展示和交流活动，加深对语言文字及其文化内涵的认识和理解。",
            "standardized_text": "结合校园生活与社会热点情境，规范拟写宣传标语、活动方案、主持词、邀请函与得体交流发言。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第21页原件一致",
            "is_elective": False, "derived_requirement": "掌握情境拟写标语通知、提炼活动主题与得体交流口语交际能力",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },

        # --- 发展型学习任务群 1：实用性阅读与交流 ---
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:informative:c08",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "2. 实用性阅读与交流", "sub_theme": "叙事性与说明性文本阅读",
            "section_type": "content_requirement", "clause_number": "实用性阅读四级①",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "阅读叙事性和说明性文本，发现、欣赏、表达和交流家庭生活、学校生活、社会生活和大自然的美好，热爱生活，感恩生活。",
            "standardized_text": "快速通读说明性文本，筛选提取关键事实信息，概括段落核心要点，把握说明对象的形态特征与本质规律。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第25页（PDF第32页）实用性阅读第四学段第(1)条一致",
            "is_elective": False, "derived_requirement": "说明性文本信息筛选、主要内容概括与说明对象特征把握",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.practical"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:explain_methods:c09",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "2. 实用性阅读与交流", "sub_theme": "科技作品与科学创造欣赏",
            "section_type": "content_requirement", "clause_number": "实用性阅读四级②",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "阅读科技作品，欣赏人类的科学创造，关注祖国的科技创新和社会主义建设成就，交流自己的发现与体会；学习为创造人类美好生活作出重要贡献的杰出人物的事迹，激发创造精神。",
            "standardized_text": "辨析说明文常用说明方法（列数字、举例子、作比较、打比方、下定义、分类别）的说明效果，品析说明文语言准确严密性。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第25页（PDF第32页）实用性阅读第四学段第(2)条一致",
            "is_elective": False, "derived_requirement": "科技说明文说明方法辨析与说明语言准确性严密性品析",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.practical"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:non_continuous:c10",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "2. 实用性阅读与交流", "sub_theme": "跨媒介阅读与多模态文本交流",
            "section_type": "content_requirement", "clause_number": "实用性阅读四级③",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "学习跨媒介阅读与交流。通过多种媒介关注国内外政治、经济、社会、科技、文化等方面的新鲜事，比较不同媒介的表达效果，尝试探究不同媒介的表达特点；阅读新闻报道、时事评论等作品，关注社会主义建设新成果，就感兴趣的话题与同学进行线上线下讨论，根据目的与对象选择合适的媒介进行交流沟通。",
            "standardized_text": "从非连续性文本（图表、数据、问卷报告、图画、材料节选）中整合提取关键信息，进行跨材料比对、推断论证并得出结论。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第25页（PDF第32页）实用性阅读第四学段第(3)条一致",
            "is_elective": False, "derived_requirement": "非连续性文本图文信息转换、图表趋势分析与多材料信息对比整合",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.non_continuous"]
        },

        # --- 发展型学习任务群 2：文学阅读与创意表达 ---
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:narrative_plot:c11",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "革命文学作品与叙事脉络",
            "section_type": "content_requirement", "clause_number": "文学阅读四级①",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "阅读反映中国革命各个时期的重大事件、伟大成就、代表性人物及其感人事迹的优秀文学作品，感悟革命领袖、革命英雄、模范人物的理想信念和奋斗精神，运用多种方式交流自己的阅读感受。",
            "standardized_text": "梳理叙事性散文和小说的开端、发展、高潮、结局脉络，理清行文线索（物线、事线、情线），概括核心情节事件。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第27页（PDF第34页）文学阅读第四学段第(1)条一致",
            "is_elective": False, "derived_requirement": "把握记叙文散文小说的叙事脉络、叙述顺序与行文线索",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:character_profile:c12",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "人与自然文学作品与写作手法",
            "section_type": "content_requirement", "clause_number": "文学阅读四级②",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "阅读表现人与自然的优秀文学作品，包括古诗文名篇，体会作者通过语言和形象构建的艺术世界，借鉴其中的写作手法，表达自己对自然的观察和思考，抒发自己的情感。",
            "standardized_text": "分析文学作品中的人物形象特征，掌握外貌、语言、动作、神态、心理及正面描写、侧面烘托等塑造手法。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第27页（PDF第34页）文学阅读第四学段第(2)条一致",
            "is_elective": False, "derived_requirement": "分析文学作品中的人物形象特征与性格品格，掌握多种人物描写手法",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:language_taste:c13",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "人与社会文学作品与语言品味",
            "section_type": "content_requirement", "clause_number": "文学阅读四级③",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "阅读表现人与社会、人与他人的古今优秀诗歌、散文、小说、戏剧等文学作品，学习欣赏、品味作品的语言、形象等，交流审美感受，体会作品的情感和思想内涵；尝试写诗歌、小小说等。",
            "standardized_text": "品味文学语言的生动性与富有表现力的词句，分析修辞手法（比喻、拟人等）与表现手法（托物言志、象征、抑扬）的艺术效果。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第27页（PDF第34页）文学阅读第四学段第(3)条一致",
            "is_elective": False, "derived_requirement": "品味文学语言的生动性与富有表现力词句，分析修辞与表现手法的作用",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:theme_sentiment:c14",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "数字时代文学与艺术魅力",
            "section_type": "content_requirement", "clause_number": "文学阅读四级④",
            "pdf_page": 28 + pdf_offset, "print_page": 28,
            "raw_text": "领略数字时代精彩的文学世界，欣赏由经典文学作品改编的影视作品，感受不同媒介的艺术魅力。",
            "standardized_text": "深入领悟文学作品的思想内涵、主旨情感与时代价值，结合生活体验发表个性化审美见解。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第28页（PDF第35页）文学阅读第四学段第(4)条一致",
            "is_elective": False, "derived_requirement": "感悟作品主旨与作者情感态度，进行个性化审美探究与启示感悟",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:poetry_appreciation:c15",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "古诗文名篇意象与情感鉴赏",
            "section_type": "content_requirement", "clause_number": "文学阅读四级·古诗词",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "阅读表现人与自然的优秀文学作品，包括古诗文名篇，体会作者通过语言和形象构建的艺术世界，借鉴其中的写作手法，表达自己对自然的观察和思考，抒发自己的情感。",
            "standardized_text": "鉴赏古代经典诗词的典型意象与意境，把握诗歌主旨与作者思想感情，品析炼字、用典与修辞手法。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第27页原件一致",
            "is_elective": False, "derived_requirement": "鉴赏古代诗词意象与意境，把握诗歌主旨与作者思想感情，品析炼字与修辞手法",
            "review_status": "pending", "legacy_mappings": ["chinese.ancient.poetry_appreciate"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:writing:content_req:creative_writing:c16",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "writing",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "3. 文学阅读与创意表达", "sub_theme": "创意表达与记叙文写作",
            "section_type": "content_requirement", "clause_number": "文学阅读四级·创意写作",
            "pdf_page": 27 + pdf_offset, "print_page": 27,
            "raw_text": "阅读表现人与社会、人与他人的古今优秀诗歌、散文、小说、戏剧等文学作品，学习欣赏、品味作品的语言、形象等，交流审美感受，体会作品的情感和思想内涵；尝试写诗歌、小小说等。",
            "standardized_text": "在中考记叙文写作中准确审题立意，精选典型真实素材，合理安排详略，运用人物景物细节描摹抒发真情实感。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第27页原件一致",
            "is_elective": False, "derived_requirement": "记叙文大作文审题立意构思、选材剪裁、人物景物细节描摹与真情实感表达",
            "review_status": "pending", "legacy_mappings": ["chinese.writing.composition"]
        },

        # --- 发展型学习任务群 3：思辨性阅读与表达 ---
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:argument_claim:c17",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "4. 思辨性阅读与表达", "sub_theme": "生活感悟哲理文本与观点阐述",
            "section_type": "content_requirement", "clause_number": "思辨性阅读四级①",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "阅读关于生活感悟、生活哲理方面的优秀作品，学习思考与表达的方法，结合生活经验和阅读材料，阐述自己的思考和观点。",
            "standardized_text": "准确提炼与归纳议论文的中心论点与分论点，分析论点提出的位置与方式，清晰区分论题与论点。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第30页（PDF第37页）思辨性阅读第四学段第(1)条一致",
            "is_elective": False, "derived_requirement": "准确提炼与归纳议论文中心论点与分论点，区分论点与论题",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.argumentative"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:argument_evidence:c18",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "4. 思辨性阅读与表达", "sub_theme": "科学探究文本与研讨演讲",
            "section_type": "content_requirement", "clause_number": "思辨性阅读四级②",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "学习关于科学探究方面的文本，联系自己的科学学习经历，围绕问题提出、探究过程、解决方法等进行专题式的研讨、演讲和写作。",
            "standardized_text": "辨析事实论据与道理论据，剖析论据对中心论点和分论点的支撑关系，并结合实际论述要求补充合适论据。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第30页（PDF第37页）思辨性阅读第四学段第(2)条一致",
            "is_elective": False, "derived_requirement": "辨析事实论据与道理论据，分析论据对论点的证明作用并补充合适论据",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.argumentative"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:argument_methods:c19",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "4. 思辨性阅读与表达", "sub_theme": "经典艺论文艺片段评析",
            "section_type": "content_requirement", "clause_number": "思辨性阅读四级③",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "阅读诗话、文论、书画艺术论的经典片段，尝试运用其中的观点欣赏、评析作品。",
            "standardized_text": "掌握举例论证、道理论证、对比论证、比喻论证四大常见论证方法的作用，理清议论文段落或全文论证思路结构。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第30页（PDF第37页）思辨性阅读第四学段第(3)条一致",
            "is_elective": False, "derived_requirement": "辨析四大论证方法的作用，理清议论文行文思路与论证结构",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.argumentative"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:writing:content_req:critical_writing:c20",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "writing",
            "part_title": "四、课程内容", "domain_title": "（二）发展型学习任务群",
            "theme_title": "4. 思辨性阅读与表达", "sub_theme": "理论思辨文本与社会热点讨论",
            "section_type": "content_requirement", "clause_number": "思辨性阅读四级④",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "学习革命领袖的理论文章、经典的思辨性文本（包括短小的文言经典），理解作者的立场、观点与方法。围绕社会热点问题，以口头或书面方式参与讨论。",
            "standardized_text": "在中考微写作中针对现实生活与社会热点材料发表明确观点，有理有据展开精炼议论，提升辩证思维。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第30页（PDF第37页）思辨性阅读第四学段第(4)条一致",
            "is_elective": False, "derived_requirement": "中考思辨性微写作，就社会热点或材料发表明确观点，有理有据展开精炼论述",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.argumentative"]
        },

        # --- 拓展型学习任务群 1：整本书阅读 ---
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:whole_book_reading:c21",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "5. 整本书阅读", "sub_theme": "名著整本书通读研读与笔记心得",
            "section_type": "content_requirement", "clause_number": "整本书阅读四级②",
            "pdf_page": 33 + pdf_offset, "print_page": 33,
            "raw_text": "独立阅读古今中外诗歌集、中长篇小说、散文集等文学名著，如《朝花夕拾》《骆驼祥子》《艾青诗选》《西游记》《格列佛游记》《钢铁是怎样炼成的》等。根据阅读进度完成读书笔记，针对作品的语言、形象、主题等方面的话题展开研讨。",
            "standardized_text": "通读统编教材必读名著，理清核心人物命运轨迹与关键情节脉络，撰写读书心得笔记并开展专题探究。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第33页（PDF第40页）整本书阅读第四学段第(2)条一致",
            "is_elective": False, "derived_requirement": "初中必读名著关键情节脉络、核心人物性格专题探究与阅读体会笔记",
            "review_status": "pending", "legacy_mappings": ["chinese.reading.literary"]
        },

        # --- 拓展型学习任务群 2：跨学科学习 (第四学段 5 条全集) ---
        {
            "clause_id": "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_science:c22",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "6. 跨学科学习", "sub_theme": "理科观察与科技实验研究报告",
            "section_type": "content_requirement", "clause_number": "跨学科学习四级①",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "结合数学、物理、化学、生物学等学科学习，或者自己参与的科技活动，学习撰写并分享观察、实验研究报告。",
            "standardized_text": "综合运用数理化生等多学科学习及科技实践所得，规范撰写观察记录与科学小论文报告。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第35页（PDF第42页）跨学科学习第四学段第(1)条一致",
            "is_elective": False, "derived_requirement": "综合运用多学科实验与观察所得，规范撰写实验研究报告与科学小论文",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_health:c23",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "6. 跨学科学习", "sub_theme": "身心健康校园调查报告",
            "section_type": "content_requirement", "clause_number": "跨学科学习四级②",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "在心理健康、身体素质等方面，选择师生共同关心的问题，组织小课题组，开展校园调查，学习设计问卷、访谈、统计、分析，撰写并发布调查报告。",
            "standardized_text": "围绕校园身心健康问题组织课题调查，设计问卷、访谈记录、统计数据并撰写发布调研报告。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第35页（PDF第42页）跨学科学习第四学段第(2)条一致",
            "is_elective": False, "derived_requirement": "设计问卷访谈，完成统计分析并规范撰写校园调查报告",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_social:c24",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "6. 跨学科学习", "sub_theme": "社会热点问题检索与讨论",
            "section_type": "content_requirement", "clause_number": "跨学科学习四级③",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "在环境、安全、人口、资源、公共卫生等方面，选择感兴趣的社会热点问题，查找和阅读相关资料，记录重要内容，列出发言提纲，参加班级讨论。",
            "standardized_text": "围绕环境、安全等社会热点问题检索多方资料，提取核心信息，列出发言提纲并有条理地参与班级研讨。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第35页（PDF第42页）跨学科学习第四学段第(3)条一致",
            "is_elective": False, "derived_requirement": "围绕社会热点检索整理材料，列出发言提纲并清晰有理表达观点",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_virtue:c25",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "6. 跨学科学习", "sub_theme": "专题研究与中华传统美德",
            "section_type": "content_requirement", "clause_number": "跨学科学习四级④",
            "pdf_page": 36 + pdf_offset, "print_page": 36,
            "raw_text": "围绕仁爱诚信、天下为公、和谐包容、精忠报国、英勇奋斗、自强不息、明礼守法，以及科学理性、艺术精神等，选择专题，组建小组，开展学习与研究，运用多种形式分享学习与研究成果。",
            "standardized_text": "围绕传统美德与科学理性专题开展跨学科小组探究，运用多种形式呈现与交流研究成果。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第36页（PDF第43页）跨学科学习第四学段第(4)条一致",
            "is_elective": False, "derived_requirement": "围绕核心价值观与科学理性专题开展合作探究与成果汇报",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_culture_club:c26",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（三）拓展型学习任务群",
            "theme_title": "6. 跨学科学习", "sub_theme": "社团文化活动策划与多媒介展示",
            "section_type": "content_requirement", "clause_number": "跨学科学习四级⑤",
            "pdf_page": 36 + pdf_offset, "print_page": 36,
            "raw_text": "组建文学艺术社团，开展相关文化活动，参与社区文化活动与文化建设；在参与过程中写出策划方案，制作海报，记录活动过程，运用多种媒介发布学习成果。",
            "standardized_text": "参与文化社团与社区文化建设，撰写活动策划方案，制作图文海报并运用多媒介发布展示成果。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第36页（PDF第43页）跨学科学习第四学段第(5)条一致",
            "is_elective": False, "derived_requirement": "撰写文化活动策划方案，制作宣传海报并运用多种媒介展示成果",
            "review_status": "pending", "legacy_mappings": ["chinese.base.comprehensive"]
        },

        # --- 古诗文与文言文阅读（依据课程目标与附录推荐篇目）---
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:poetry_dictation:c27",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "古代诗文诵读与背诵推荐",
            "section_type": "content_requirement", "clause_number": "诗文背诵四级·推荐篇目",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。背诵优秀诗文80篇（段）。",
            "standardized_text": "熟练背诵统编初中教材附录推荐背诵的61篇古代诗文名篇名句，理解句意并准确默写关键字词。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第15页（PDF第22页）第四学段阅读与鉴赏要求第7条完全一致",
            "is_elective": False, "derived_requirement": "中考统编初中古诗文名句理解性默写，无添字、漏字、错别字",
            "review_status": "pending", "legacy_mappings": ["chinese.ancient.poetry_recite"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:classical_vocab:c28",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "浅易文言文阅读实词虚词",
            "section_type": "content_requirement", "clause_number": "文言文阅读四级·实词虚词",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。",
            "standardized_text": "借助注释与工具书理解浅易文言文，掌握常见文言实词（通假字、古今异义、词类活用、一词多义）及高频虚词的意义和用法。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第15页原件一致",
            "is_elective": False, "derived_requirement": "掌握常见文言实词通假活用、古今异义与常见文言虚词在语境中的含义",
            "review_status": "pending", "legacy_mappings": ["chinese.ancient.prose_word"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:classical_sentence:c29",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "文言文断句与重点句子翻译",
            "section_type": "content_requirement", "clause_number": "文言文阅读四级·断句翻译",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。",
            "standardized_text": "掌握浅易文言文节奏停顿与断句规律，遵循直译为主、意译为辅原则，准确翻译文中关键语句。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第15页原件一致",
            "is_elective": False, "derived_requirement": "文言文断句停顿划分与文中重点陈述句、判断句、被动句、倒装句的准确翻译",
            "review_status": "pending", "legacy_mappings": ["chinese.ancient.prose_sentence"]
        },
        {
            "clause_id": "cs:chinese:2022:s4:reading:content_req:classical_comp:c30",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "reading",
            "part_title": "三、课程目标", "domain_title": "（二）学段要求",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "文言文内容理解与主旨对比探究",
            "section_type": "content_requirement", "clause_number": "文言文阅读四级·主旨探究",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "诵读古代诗词，阅读浅易文言文，能借助注释和工具书理解基本内容。注重积累、感悟和运用，提高自己的欣赏品位。",
            "standardized_text": "全面理解浅易文言文思想内容与作者主旨情感，能够针对课内与课外文言材料就观点主旨开展对比探究。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第15页原件一致",
            "is_elective": False, "derived_requirement": "文言文思想内容整体把握、作者观点态度分析与课内外对比阅读探究",
            "review_status": "pending", "legacy_mappings": ["chinese.ancient.prose_content"]
        },

        # --- 学业质量标准（第四学段）---
        {
            "clause_id": "cs:chinese:2022:s4:lang_usage:academic_req:chinese_eval:c31",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "lang_usage",
            "part_title": "五、学业质量", "domain_title": "（二）学业质量描述",
            "theme_title": "第四学段（7~9年级）", "sub_theme": "日常生活语言运用情境学业表现",
            "section_type": "academic_requirement", "clause_number": "第四学段学业质量",
            "pdf_page": 42 + pdf_offset, "print_page": 42,
            "raw_text": "能根据语境，借助工具书，认清字形、读准字音、正确理解汉字的意思。在学习与生活中，累计认识3500个左右常用汉字，能规范、端正、整洁地书写常用汉字；在日常记录中使用规范、通行的行楷字，提高书写的速度。有探究汉字规律的意识，在社会生活中能根据字音、字形、字义三者的关系准确认读、正确理解遇到的生字新词；发现并积累不同语境下具有个性化特征的词句和段落，能根据自己的表达需要和习惯选择使用。",
            "standardized_text": "在日常生活与语文实践中，认清字形、读准字音，累计掌握3500个常用字，规范书写，区分事实与观点，达到初中毕业生学业水平评价要求。",
            "collation_note": "经人工逐字核对，与教育部2022版课标第42页（PDF第49页）第四学段学业质量描述完全一致",
            "is_elective": False, "derived_requirement": "初中学业水平考试中考语文核心素养综合评价标准",
            "review_status": "pending", "legacy_mappings": ["chinese.base"]
        }
    ]

    # 2. 语文初中候选知识点体系 (25 个节点，基于任务群独立推导，层级严密无环)
    def filter_clauses(cond):
        return [c["clause_id"] for c in clauses if cond(c)]

    candidates = [
        # 一级领域 1：基础型任务群·语言文字积累与基础运用
        {
            "code": "chinese_cand.base_accumulation",
            "name": "语言文字积累与基础运用",
            "domain": "lang_usage", "parent_code": None, "level": 1,
            "description": "字音字形、词语成语、语法修辞与病句标点、文化常识与书法鉴赏、情境综合表达。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "lang_usage"),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标基础型任务群归集，待审核",
            "legacy_mappings": ["chinese.base", "chinese.base.phonetics", "chinese.base.character", "chinese.base.idiom", "chinese.base.grammar", "chinese.base.punctuation", "chinese.base.literature", "chinese.base.calligraphy", "chinese.base.comprehensive"]
        },
        {
            "code": "chinese_cand.base.phonetics",
            "name": "字音辨析与拼读规范",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "常见多音字、多音多义字、易读错字、形声字易错读音辨析及汉语拼音正确拼写。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:lang_usage:content_req:phonetics:c01",
                "cs:chinese:2022:s4:lang_usage:academic_req:chinese_eval:c31"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应字音认读条文，待审核",
            "legacy_mappings": ["chinese.base.phonetics"]
        },
        {
            "code": "chinese_cand.base.character_orthography",
            "name": "汉字字形与错别字纠正",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "音近致错、形近致错、义混致错等常见错别字识别纠正及汉字规范书写。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:lang_usage:goals:character_accumulation:c00a",
                "cs:chinese:2022:s4:lang_usage:goals:handwriting_norm:c00b",
                "cs:chinese:2022:s4:lang_usage:content_req:character:c02"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应字形规范书写条文，待审核",
            "legacy_mappings": ["chinese.base.character"]
        },
        {
            "code": "chinese_cand.base.idiom_vocabulary",
            "name": "词语与成语语境运用",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "初中常用词语与成语含义理解、感情色彩褒贬辨析、适用对象及语境搭配正误判断。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:lang_usage:content_req:vocabulary:c03"),
            "is_elective": False, "review_status": "pending", "review_note": "对应成语词语积累运用条文，待审核",
            "legacy_mappings": ["chinese.base.idiom"]
        },
        {
            "code": "chinese_cand.base.syntax_revision",
            "name": "语法修辞与病句辨析修改",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "搭配不当、成分残缺赘余、语序不当、句式杂糅、不合逻辑等六大病句辨析与规范修改。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:lang_usage:content_req:syntax:c04"),
            "is_elective": False, "review_status": "pending", "review_note": "对应语法修辞与病句修改条文，待审核",
            "legacy_mappings": ["chinese.base.grammar"]
        },
        {
            "code": "chinese_cand.base.punctuation",
            "name": "标点符号规范运用与纠错",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "顿号、逗号、分号、冒号、引号、问号、书名号等在复合语境中的规范用法与正误辨析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:lang_usage:content_req:punctuation:c05"),
            "is_elective": False, "review_status": "pending", "review_note": "对应标点符号规范运用条文，待审核",
            "legacy_mappings": ["chinese.base.punctuation"]
        },
        {
            "code": "chinese_cand.base.culture_calligraphy",
            "name": "文学文化常识与书法鉴赏",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "中国传统节气民俗、古代称谓、文学流派与楷书、行书等名家书法字体源流审美鉴赏。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:lang_usage:goals:handwriting_norm:c00b",
                "cs:chinese:2022:s4:lang_usage:content_req:culture:c06"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应文化常识与名家书法鉴赏条文，待审核",
            "legacy_mappings": ["chinese.base.literature", "chinese.base.calligraphy"]
        },
        {
            "code": "chinese_cand.base.contextual_expression",
            "name": "情境表达与综合性学习",
            "domain": "lang_usage", "parent_code": "chinese_cand.base_accumulation", "level": 2,
            "description": "图表转写、标语撰写、通知邀请函拟写、活动方案策划及得体口语交际应对。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:lang_usage:content_req:expression:c07",
                "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_science:c22",
                "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_health:c23",
                "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_social:c24",
                "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_virtue:c25",
                "cs:chinese:2022:s4:comp_prac:content_req:interdisciplinary_culture_club:c26"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应情境表达与跨学科综合性学习，待审核",
            "legacy_mappings": ["chinese.base.comprehensive"]
        },

        # 一级领域 2：发展型任务群·古诗文阅读与传统文化
        {
            "code": "chinese_cand.classical_literature",
            "name": "古诗文阅读与传统文化",
            "domain": "reading", "parent_code": None, "level": 1,
            "description": "古代诗词默写鉴赏、文言实词虚词、断句翻译与内容主旨对比探究。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:reading:content_req:poetry_appreciation:c15",
                "cs:chinese:2022:s4:reading:content_req:poetry_dictation:c27",
                "cs:chinese:2022:s4:reading:content_req:classical_vocab:c28",
                "cs:chinese:2022:s4:reading:content_req:classical_sentence:c29",
                "cs:chinese:2022:s4:reading:content_req:classical_comp:c30"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标古诗文阅读要求归集，待审核",
            "legacy_mappings": ["chinese.ancient", "chinese.ancient.poetry_recite", "chinese.ancient.poetry_appreciate", "chinese.ancient.prose_word", "chinese.ancient.prose_sentence", "chinese.ancient.prose_content"]
        },
        {
            "code": "chinese_cand.poetry.dictation",
            "name": "古诗文名句理解性默写",
            "domain": "reading", "parent_code": "chinese_cand.classical_literature", "level": 2,
            "description": "中考统编初中61篇必背古诗文名篇名句识记、语境理解性填空与关键字词准确书写。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:poetry_dictation:c27"),
            "is_elective": False, "review_status": "pending", "review_note": "对应初中必背诗文背诵默写要求，待审核",
            "legacy_mappings": ["chinese.ancient.poetry_recite"]
        },
        {
            "code": "chinese_cand.poetry.appreciation",
            "name": "古代诗词意象意境与手法鉴赏",
            "domain": "reading", "parent_code": "chinese_cand.classical_literature", "level": 2,
            "description": "古代诗词经典意象意境把握、炼字炼句品析、表现手法（虚实结合、动静结合）与情感主旨领悟。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:poetry_appreciation:c15"),
            "is_elective": False, "review_status": "pending", "review_note": "对应古代诗词意境艺术手法鉴赏，待审核",
            "legacy_mappings": ["chinese.ancient.poetry_appreciate"]
        },
        {
            "code": "chinese_cand.prose.classical_vocab",
            "name": "文言实词通假活用与虚词理解",
            "domain": "reading", "parent_code": "chinese_cand.classical_literature", "level": 2,
            "description": "文言实词一词多义、词类活用、通假字、古今异义辨析及之其而以于等高频文言虚词在语境中的含义。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:classical_vocab:c28"),
            "is_elective": False, "review_status": "pending", "review_note": "对应文言实词虚词理解要求，待审核",
            "legacy_mappings": ["chinese.ancient.prose_word"]
        },
        {
            "code": "chinese_cand.prose.classical_syntax_trans",
            "name": "文言断句停顿与重点句子翻译",
            "domain": "reading", "parent_code": "chinese_cand.classical_literature", "level": 2,
            "description": "文言句子节奏停顿与句读断句、判断句倒装句被动句等特殊句式把握与重点文言语句规范直译。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:classical_sentence:c29"),
            "is_elective": False, "review_status": "pending", "review_note": "对应文言断句与翻译要求，待审核",
            "legacy_mappings": ["chinese.ancient.prose_sentence"]
        },
        {
            "code": "chinese_cand.prose.classical_comprehension",
            "name": "文言文内容理解与主旨对比探究",
            "domain": "reading", "parent_code": "chinese_cand.classical_literature", "level": 2,
            "description": "文言文文本事实信息提取归纳、人物品行性格评析、主旨观点阐述及课内与课外联读对比分析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:classical_comp:c30"),
            "is_elective": False, "review_status": "pending", "review_note": "对应文言文主旨理解与对比探究，待审核",
            "legacy_mappings": ["chinese.ancient.prose_content"]
        },

        # 一级领域 3：现代文多文本阅读与整本书阅读
        {
            "code": "chinese_cand.modern_reading",
            "name": "现代文多文本阅读与整本书阅读",
            "domain": "reading", "parent_code": None, "level": 1,
            "description": "说明文实用文、多材料非连续性文本、记叙文散文小说文学作品、议论文思辨性文本与名著整本书探究。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "reading" and c["clause_id"] not in [
                "cs:chinese:2022:s4:reading:content_req:poetry_appreciation:c15",
                "cs:chinese:2022:s4:reading:content_req:poetry_dictation:c27",
                "cs:chinese:2022:s4:reading:content_req:classical_vocab:c28",
                "cs:chinese:2022:s4:reading:content_req:classical_sentence:c29",
                "cs:chinese:2022:s4:reading:content_req:classical_comp:c30"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标现代文多文体阅读与整本书阅读归集，待审核",
            "legacy_mappings": ["chinese.reading", "chinese.reading.practical", "chinese.reading.non_continuous", "chinese.reading.literary", "chinese.reading.argumentative"]
        },
        {
            "code": "chinese_cand.reading.informative_skills",
            "name": "说明性文本信息筛选与说明方法品析",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "说明对象及其特征概括、事实信息要点提炼、列数字作比较打比方等说明方法作用分析与语言准确性品析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:reading:content_req:informative:c08",
                "cs:chinese:2022:s4:reading:content_req:explain_methods:c09"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应说明性文本信息筛选与说明方法品析，待审核",
            "legacy_mappings": ["chinese.reading.practical"]
        },
        {
            "code": "chinese_cand.reading.multimodal_non_continuous",
            "name": "多材料非连续性文本信息图表综合分析",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "跨文本、图表、调查问卷等多模态材料信息提取、图文转换、异同对比归纳与结论合理推断。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:non_continuous:c10"),
            "is_elective": False, "review_status": "pending", "review_note": "对应多模态非连续性文本综合分析，待审核",
            "legacy_mappings": ["chinese.reading.non_continuous"]
        },
        {
            "code": "chinese_cand.reading.narrative_plot_character",
            "name": "记叙文散文小说情节脉络与人物形象",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "记叙文、散文、小说情节起伏脉络梳理、行文线索把握及多维度人物性格品质肖像心理描写分析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:reading:content_req:narrative_plot:c11",
                "cs:chinese:2022:s4:reading:content_req:character_profile:c12"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应文学作品情节脉络与人物塑造，待审核",
            "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "code": "chinese_cand.reading.narrative_language_theme",
            "name": "记叙文语言修辞品味与文章主旨感悟",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "记叙文精彩语句词语含义与修辞赏析、环境描写与表现手法作用及作品中心主旨与情感感悟领会。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:reading:content_req:language_taste:c13",
                "cs:chinese:2022:s4:reading:content_req:theme_sentiment:c14"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应文学语言品味与主旨领悟，待审核",
            "legacy_mappings": ["chinese.reading.literary"]
        },
        {
            "code": "chinese_cand.reading.argument_claims_evidence",
            "name": "议论文中心论点提炼与论据分析",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "议论文论题与中心论点提取判断、分论点梳理、事实论据与道理论据辨析及其与论点的证明关系、补充论据。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:reading:content_req:argument_claim:c17",
                "cs:chinese:2022:s4:reading:content_req:argument_evidence:c18"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "对应议论文论点论据要求，待审核",
            "legacy_mappings": ["chinese.reading.argumentative"]
        },
        {
            "code": "chinese_cand.reading.argument_methods_structure",
            "name": "议论文论证方法与行文思路结构",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "举例、道理、对比、比喻四大论证方法作用分析及全文或段落引论本论结论思路逻辑剖析。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:argument_methods:c19"),
            "is_elective": False, "review_status": "pending", "review_note": "对应议论文论证方法与论证结构，待审核",
            "legacy_mappings": ["chinese.reading.argumentative"]
        },
        {
            "code": "chinese_cand.reading.classic_whole_book",
            "name": "必读名著情节人物专题探究与读书心得",
            "domain": "reading", "parent_code": "chinese_cand.modern_reading", "level": 2,
            "description": "统编初中必读名著关键情节脉络、核心人物命运性格对比分析、主题思想探究及读书心得笔记。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:reading:content_req:whole_book_reading:c21"),
            "is_elective": False, "review_status": "pending", "review_note": "对应整本书阅读任务群核心要求，待审核",
            "legacy_mappings": ["chinese.reading.literary"]
        },

        # 一级领域 4：表达交流与写作素养
        {
            "code": "chinese_cand.composition_expression",
            "name": "表达交流与写作素养",
            "domain": "writing", "parent_code": None, "level": 1,
            "description": "记叙文大作文审题立意构思、细节描摹创意表达与思辨性微写作简评论述。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] in [
                "cs:chinese:2022:s4:writing:content_req:creative_writing:c16",
                "cs:chinese:2022:s4:writing:content_req:critical_writing:c20"
            ]),
            "is_elective": False, "review_status": "pending", "review_note": "依据课标写作表达与微写作归集，待审核",
            "legacy_mappings": ["chinese.writing.composition", "chinese.reading.argumentative"]
        },
        {
            "code": "chinese_cand.writing.composition_narrative",
            "name": "记叙文大作文立意选材构思与细节描摹",
            "domain": "writing", "parent_code": "chinese_cand.composition_expression", "level": 2,
            "description": "中考记叙文审题立意、典型选材、巧妙详略剪裁、生动人物景物细节描摹与真情实感规范表达。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:writing:content_req:creative_writing:c16"),
            "is_elective": False, "review_status": "pending", "review_note": "对应记叙文大作文写作要求，待审核",
            "legacy_mappings": ["chinese.writing.composition"]
        },
        {
            "code": "chinese_cand.writing.critical_micro_writing",
            "name": "思辨性微写作观点论述与评论",
            "domain": "writing", "parent_code": "chinese_cand.composition_expression", "level": 2,
            "description": "中考微写作针对社会现象、材料话题发表明确观点，摆事实讲道理，150字逻辑严密精炼论述。",
            "source_clause_ids": filter_clauses(lambda c: c["clause_id"] == "cs:chinese:2022:s4:writing:content_req:critical_writing:c20"),
            "is_elective": False, "review_status": "pending", "review_note": "对应中考微写作思辨性论述要求，待审核",
            "legacy_mappings": ["chinese.reading.argumentative"]
        }
    ]

    # 3. 存量 18 个语文旧节点映射契约 (严格映射至新候选体系，详细演进理由与历史兼容保障)
    legacy_mappings = [
        {
            "legacy_code": "chinese.base",
            "legacy_name": "基础·运用",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base_accumulation"],
            "mapping_reason": "一级分类承载基础积累与运用，映射至新体系语言文字积累与梳理大类。",
            "compatibility_assurance": "历史试卷基础板块统计数据保持兼容。"
        },
        {
            "legacy_code": "chinese.base.phonetics",
            "legacy_name": "字音辨析与注音拼读",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.phonetics"],
            "mapping_reason": "多音字、易错字读音辨析核心考查点完全一致。",
            "compatibility_assurance": "历史字音题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.base.character",
            "legacy_name": "汉字字形与错别字纠正",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.character_orthography"],
            "mapping_reason": "错别字纠正与同音形近字辨析核心考查点完全一致。",
            "compatibility_assurance": "历史字形题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.base.idiom",
            "legacy_name": "成语与词语语境运用",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.idiom_vocabulary"],
            "mapping_reason": "词语和成语语境理解与色彩辨析核心考查点完全一致。",
            "compatibility_assurance": "历史成语词语题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.base.syntax",
            "legacy_name": "病句辨析与句子修改",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.syntax_revision"],
            "mapping_reason": "病句类型识别与规范修改核心考查点完全一致。",
            "compatibility_assurance": "历史病句题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.base.punctuation",
            "legacy_name": "标点符号规范使用",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.punctuation"],
            "mapping_reason": "常用标点符号用法与辨析核心考查点完全一致。",
            "compatibility_assurance": "历史标点题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.base.culture",
            "legacy_name": "文学文化常识与书法鉴赏",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.culture_calligraphy"],
            "mapping_reason": "文学文化常识与书法五体鉴赏考点完全一致，平移保留。",
            "compatibility_assurance": "历史常识与书法鉴赏题目无损保留。"
        },
        {
            "legacy_code": "chinese.base.expression",
            "legacy_name": "情境表达与综合性学习",
            "legacy_parent_code": "chinese.base",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.base.contextual_expression"],
            "mapping_reason": "情境表达、活动方案、宣传标语与口语交际核心考查点完全一致。",
            "compatibility_assurance": "历史综合性学习题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.poetry_classical",
            "legacy_name": "古诗文阅读",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.classical_literature"],
            "mapping_reason": "一级分类承载古诗文阅读大类，对应新体系古诗文阅读领域。",
            "compatibility_assurance": "历史答题统计数据保持不变。"
        },
        {
            "legacy_code": "chinese.poetry.dictation",
            "legacy_name": "古诗文名句理解性默写",
            "legacy_parent_code": "chinese.poetry_classical",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.poetry.dictation"],
            "mapping_reason": "中考古诗文理解性默写考查核心完全一致。",
            "compatibility_assurance": "历史默写题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.poetry.appreciation",
            "legacy_name": "古代诗歌意象鉴赏与情感感悟",
            "legacy_parent_code": "chinese.poetry_classical",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.poetry.appreciation"],
            "mapping_reason": "古诗意象意境、表现手法与主旨情感鉴赏考查核心完全一致。",
            "compatibility_assurance": "历史诗歌赏析题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.prose.classical",
            "legacy_name": "文言文实词、断句与对比理解",
            "legacy_parent_code": "chinese.poetry_classical",
            "action": "split",
            "target_candidate_codes": [
                "chinese_cand.prose.classical_vocab",
                "chinese_cand.prose.classical_syntax_trans",
                "chinese_cand.prose.classical_comprehension"
            ],
            "mapping_reason": "原旧节点将实词、断句翻译与内容理解对比混杂，新体系将其精细化拆解为字词、句法翻译与对比探究三项，极大提升弱项诊断颗粒度。",
            "compatibility_assurance": "历史文言文试题引用保持只读兼容。"
        },
        {
            "legacy_code": "chinese.reading",
            "legacy_name": "现代文与整本书阅读",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.modern_reading"],
            "mapping_reason": "一级分类承载现代文多文本阅读与整本书阅读大类，概念完全一致。",
            "compatibility_assurance": "历史答题统计数据保持不变。"
        },
        {
            "legacy_code": "chinese.classic.reading",
            "legacy_name": "名著阅读人物与主题探究",
            "legacy_parent_code": "chinese.reading",
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.reading.classic_whole_book"],
            "mapping_reason": "必读名著情节梳理、人物分析与主题探究考查完全一致。",
            "compatibility_assurance": "历史名著阅读题目关联无缝保留。"
        },
        {
            "legacy_code": "chinese.reading.narrative",
            "legacy_name": "记叙文语言品味与主旨理解",
            "legacy_parent_code": "chinese.reading",
            "action": "split",
            "target_candidate_codes": [
                "chinese_cand.reading.narrative_plot_character",
                "chinese_cand.reading.narrative_language_theme"
            ],
            "mapping_reason": "新体系将情节脉络人物塑造与语句赏析主旨感悟精细划分，支持记叙文分类诊断。",
            "compatibility_assurance": "历史记叙文题目保持只读兼容。"
        },
        {
            "legacy_code": "chinese.reading.informative",
            "legacy_name": "说明文与非连续性文本信息提取",
            "legacy_parent_code": "chinese.reading",
            "action": "split",
            "target_candidate_codes": [
                "chinese_cand.reading.informative_skills",
                "chinese_cand.reading.multimodal_non_continuous"
            ],
            "mapping_reason": "新体系将传统科技说明文与现代多模态非连续性图表文本分立，契合北京新中考命题方向。",
            "compatibility_assurance": "历史题目保持只读兼容。"
        },
        {
            "legacy_code": "chinese.reading.argumentative",
            "legacy_name": "议论文论点论据论证分析",
            "legacy_parent_code": "chinese.reading",
            "action": "split",
            "target_candidate_codes": [
                "chinese_cand.reading.argument_claims_evidence",
                "chinese_cand.reading.argument_methods_structure"
            ],
            "mapping_reason": "新体系细分论点论据提炼与论证方法思路分析，利于议论文专项攻关。",
            "compatibility_assurance": "历史议论文题目保持只读兼容。"
        },
        {
            "legacy_code": "chinese.writing.composition",
            "legacy_name": "写作表达与立意构思",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["chinese_cand.writing.composition_narrative"],
            "mapping_reason": "中考记叙文大作文审题立意构思与细节描摹，考查核心完全对应。",
            "compatibility_assurance": "历史答题记录保持不变。"
        }
    ]

    return {
        "clauses": clauses,
        "candidates": candidates,
        "legacy_mappings": legacy_mappings
    }
