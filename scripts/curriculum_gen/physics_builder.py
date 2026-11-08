# -*- coding: utf-8 -*-
"""
物理学科官方课程标准初中条款全集、候选知识体系与存量考点映射构建器。
依据教育部《义务教育物理课程标准（2022年版）》（教材〔2022〕2号，MOE-2022-PHYSICS）。
"""

from __future__ import annotations


def build_physics_data():
    source_id = "MOE-2022-PHYSICS"
    subject = "physics"
    stage = "stage4"
    pdf_offset = 7  # 印刷第1页对应 PDF 物理第8页，如印刷第9页对应PDF第16页

    # 1. 物理课程标准全量条款集合 (覆盖 5 个一级主题、二级主题所有官方编号条文、必做实验与学业质量要求)
    clauses = [
        # =========================================================================
        # 一级主题 1：物质 (matter)
        # =========================================================================
        # --- 1.1 物质的形态和变化 ---
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:state_features:c01",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.1 物质的形态和变化", "sub_theme": "三态基本特征与应用",
            "section_type": "content_requirement", "clause_number": "1.1.1",
            "pdf_page": 9 + pdf_offset, "print_page": 9,
            "raw_text": "能描述固态、液态和气态三种物态的基本特征，并列举自然界和日常生活中不同物态的物质及其应用。",
            "standardized_text": "能从宏观形状、体积及微观分子排列特征描述固态、液态、气态的基本物理特征，并结合水、冰、水蒸气等常见物质列举在生活与科技中的实际应用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第9页（PDF第16页）条文1.1.1完全一致",
            "is_elective": False, "derived_requirement": "掌握固态、液态、气态的宏观与微观特征辨析及日常应用",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:thermometer:c02",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.1 物质的形态和变化", "sub_theme": "液体温度计原理与使用",
            "section_type": "content_requirement", "clause_number": "1.1.2",
            "pdf_page": 9 + pdf_offset, "print_page": 9,
            "raw_text": "了解液体温度计的工作原理。会用常见温度计测量温度。能说出生活环境中常见的温度值，尝试对环境温度问题发表自己的见解。",
            "standardized_text": "理解液体温度计根据液体热胀冷缩规律制成；掌握实验室温度计与体温计的量程、分度值与规范读数；知道人的正常体温、水沸点等常见温度值；关注热岛效应等环境温度问题。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第9页（PDF第16页）条文1.1.2完全一致",
            "is_elective": False, "derived_requirement": "液体温度计原理、规范使用测量与环境温度见解表达",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:phase_transition:c03",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.1 物质的形态和变化", "sub_theme": "物态变化探究与吸放热",
            "section_type": "content_requirement", "clause_number": "1.1.3",
            "pdf_page": 9 + pdf_offset, "print_page": 9,
            "raw_text": "经历物态变化的实验探究过程，知道物质的熔点、凝固点和沸点，了解物态变化过程中的吸热和放热现象。能运用物态变化知识说明自然界和生活中的有关现象。",
            "standardized_text": "实验探究晶体熔化、水沸腾等规律，理解熔点、凝固点和沸点；掌握熔化/汽化/升华吸热，凝固/液化/凝华放热；运用物态变化解释冰熔化、水沸腾、下雪不冷化雪冷等自然生活现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第9页（PDF第16页）条文1.1.3完全一致",
            "is_elective": False, "derived_requirement": "经历六种物态变化探究过程，掌握吸放热规律与自然生活现象解释",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:water_cycle:c04",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.1 物质的形态和变化", "sub_theme": "水循环与水资源保护",
            "section_type": "content_requirement", "clause_number": "1.1.4",
            "pdf_page": 9 + pdf_offset, "print_page": 9,
            "raw_text": "能运用物态变化知识，说明自然界中的水循环现象。了解我国和当地的水资源状况，有节约用水和保护环境的意识。",
            "standardized_text": "分析自然界中雨、雪、云、雾、露、霜形成的水循环全过程物态变化与热量转移，树立节约用水、水资源保护与生态文明意识。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第9页（PDF第16页）条文1.1.4完全一致",
            "is_elective": False, "derived_requirement": "分析自然界水循环物态变化系统过程，具备节水环保责任意识",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state"]
        },

        # --- 1.2 物质的属性 ---
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:prop_physical:c05",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.2 物质的属性", "sub_theme": "物质物理属性与描述",
            "section_type": "content_requirement", "clause_number": "1.2.1",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "通过实验，了解物质的一些物理属性，如弹性、磁性、导电性和导热性等，能用语言、文字或图表描述物质的物理属性。",
            "standardized_text": "通过对比实验了解弹性、磁性、导电性（导体/半导体/绝缘体）与导热性（良导体/不良导体）等物理属性，并结合生活材料进行属性描述与选材设计。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10页（PDF第17页）条文1.2.1完全一致",
            "is_elective": False, "derived_requirement": "实验探究物质物理属性，理解选材依据与图表文字描述",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:mass_measure:c06",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.2 物质的属性", "sub_theme": "质量概念与天平测量",
            "section_type": "content_requirement", "clause_number": "1.2.2",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "知道质量的含义。会测量固体和液体的质量。",
            "standardized_text": "理解质量是物体所含物质的多少，质量是物体的固有属性（不随形状、状态、空间位置而变）；掌握托盘天平调平、左物右码、游码读数等测量固体与液体的规范方法。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10页（PDF第17页）条文1.2.2完全一致",
            "is_elective": False, "derived_requirement": "质量属性理解、托盘天平规范调平称量与读数及常见物体质量估测",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:density_understand:c07",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.2 物质的属性", "sub_theme": "密度理解与测量解释",
            "section_type": "content_requirement", "clause_number": "1.2.3",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "通过实验，理解密度。会测量固体和液体的密度。能解释生活中与密度有关的一些物理现象。",
            "standardized_text": "实验探究同种物质质量与体积比值为定值，理解密度概念与公式 ρ=m/V；掌握天平和量筒测量固体/液体密度方法与误差分析；运用密度鉴别物质及解释生活物理现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10页（PDF第17页）条文1.2.3完全一致",
            "is_elective": False, "derived_requirement": "密度公式综合计算、天平量筒测密度实验流程与生活现象解释",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:prop_impact:c08",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.2 物质的属性", "sub_theme": "物质属性研究对生产生活影响",
            "section_type": "content_requirement", "clause_number": "1.2.4",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "了解关于物质属性的研究对生产生活和科技进步的影响。",
            "standardized_text": "了解青铜器铁器制造、新材料研发等物质属性探索在人类文明与科技革命中的重大推动作用，体会科学发展促进社会生产力提升。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10页（PDF第17页）条文1.2.4完全一致，补全R2报告指出遗漏条款",
            "is_elective": False, "derived_requirement": "理解物质属性研究对科技工程与人类生活进步的推动价值",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },

        # --- 1.3 物质的结构和物质世界的尺度 ---
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:molecule_atom:c09",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.3 物质的结构和物质世界的尺度", "sub_theme": "物质的微观分子原子构成",
            "section_type": "content_requirement", "clause_number": "1.3.1",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "知道常见的物质是由分子、原子构成的。",
            "standardized_text": "建立物质是由微观粒子（分子、原子）构成的微观观念，认识物质构成的微粒假说与实验证据。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10页（PDF第17页）条文1.3.1完全一致",
            "is_elective": False, "derived_requirement": "掌握物质由分子、原子构成的基本微观概念",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:nuclear_atom:c10",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.3 物质的结构和物质世界的尺度", "sub_theme": "原子核式结构与微观探索历程",
            "section_type": "content_requirement", "clause_number": "1.3.2",
            "pdf_page": 10 + pdf_offset, "print_page": 10,
            "raw_text": "知道原子是由原子核和电子构成的，了解原子的核式结构模型。了解人类探索微观世界的大致历程，关注人类探索微观世界的新进展。",
            "standardized_text": "掌握原子由带正电的原子核和核外带负电的电子构成；了解卢瑟福原子核式结构模型；了解从分子到夸克的微观探索历程与最新科研成果。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第10~11页（PDF第17~18页）条文1.3.2完全一致",
            "is_elective": False, "derived_requirement": "掌握原子核式结构模型与微观世界科学探索方法",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:universe_explore:c11",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.3 物质的结构和物质世界的尺度", "sub_theme": "人类探索宇宙重大历程",
            "section_type": "content_requirement", "clause_number": "1.3.3",
            "pdf_page": 11 + pdf_offset, "print_page": 11,
            "raw_text": "了解人类探索太阳系及宇宙的大致历程，知道人类对宇宙的探索将不断深入，关注人类探索宇宙的一些重大活动。",
            "standardized_text": "了解人类探索太阳系和宇宙的历程，关注中国空间站、“天问一号”、“中国天眼”FAST等航天科技成就，树立科学探索情怀。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第11页（PDF第18页）条文1.3.3完全一致",
            "is_elective": False, "derived_requirement": "了解宇宙宏观探索历程与我国航天事业重大成就",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:matter:content_req:scale_world:c12",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "1.3 物质的结构和物质世界的尺度", "sub_theme": "物质世界从宏观到微观的大致尺度",
            "section_type": "content_requirement", "clause_number": "1.3.4",
            "pdf_page": 11 + pdf_offset, "print_page": 11,
            "raw_text": "了解物质世界的大致尺度。",
            "standardized_text": "建立从微观粒子（夸克、质子、原子核、原子、分子）到宏观世界（细胞、人体、地球、太阳系、银河系、可观测宇宙）的数量级空间尺度梯次观念。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第11页（PDF第18页）条文1.3.4完全一致，补全R2报告指出遗漏条款",
            "is_elective": False, "derived_requirement": "建立物质世界从微观粒子到宏观天体的宏大空间尺度观念",
            "review_status": "pending", "legacy_mappings": ["physics.mech.density"]
        },
        # --- 物质学业要求 ---
        {
            "clause_id": "cs:physics:2022:s4:matter:acad_req:matter_overview:c13",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "四、课程内容", "domain_title": "（一）物质",
            "theme_title": "物质学业要求", "sub_theme": "物质观念与实验测量评价",
            "section_type": "academic_requirement", "clause_number": "物质学业要求①",
            "pdf_page": 11 + pdf_offset, "print_page": 11,
            "raw_text": "能描述固态、液态和气态的基本特征及在相互转化过程中的特点，能说出生活中常见的温度值，知道质量的含义，理解密度，能说出物质世界从宏观到微观的大致尺度；能根据这些知识解释有关自然现象，尝试运用这些知识解决日常生活中的有关问题，形成初步的物质观念。",
            "standardized_text": "形成从物态变化、物理属性到微观结构的物质观念，具备熟练运用天平量筒测密度及解释生活自然现象的综合素养。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第11~12页（PDF第18~19页）物质学业要求第(1)条完全一致",
            "is_elective": False, "derived_requirement": "物质主题综合素养考查与诊断核心要求",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state", "physics.mech.density"]
        },

        # =========================================================================
        # 一级主题 2：运动和相互作用 (motion_energy)
        # =========================================================================
        # --- 2.1 多种多样的运动形式 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:motion_relative:c14",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.1 多种多样的运动形式", "sub_theme": "机械运动与参照物相对性",
            "section_type": "content_requirement", "clause_number": "2.1.1",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "知道机械运动，举例说明机械运动的相对性。",
            "standardized_text": "理解机械运动是物体位置随时间的变化；掌握参照物的概念与选取原则；能结合行驶车辆、神舟对接等实例说明运动与静止的相对性。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第14页（PDF第21页）条文2.1.1完全一致",
            "is_elective": False, "derived_requirement": "掌握机械运动与参照物选择，说明运动和静止的相对性",
            "review_status": "pending", "legacy_mappings": ["physics.mech.motion"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:kinetic_theory:c15",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.1 多种多样的运动形式", "sub_theme": "分子热运动与分子动理论",
            "section_type": "content_requirement", "clause_number": "2.1.2",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "知道自然界和生活中简单的热现象。了解分子热运动的主要特点，知道分子动理论的基本观点。",
            "standardized_text": "了解自然界热现象；掌握分子动理论三个基本观点（物质由分子构成、分子不停做无规则热运动、分子间存在引力和斥力）；能用分子动理论解释扩散现象与温度对分子运动的影响。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第14页（PDF第21页）条文2.1.2完全一致",
            "is_elective": False, "derived_requirement": "掌握分子热运动与分子动理论基本观点，解释扩散与微观作用力现象",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:motion_forms:c16",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.1 多种多样的运动形式", "sub_theme": "运动形式的多样性与物质不停运动",
            "section_type": "content_requirement", "clause_number": "2.1.3",
            "pdf_page": 14 + pdf_offset, "print_page": 14,
            "raw_text": "举例说明自然界存在多种多样的运动形式。知道物质在不停地运动。",
            "standardized_text": "从机械运动、分子热运动、电磁运动等多种层面认识自然界运动形式的多样性，树立物质世界处于永恒运动之中的科学观念。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第14页（PDF第21页）条文2.1.3完全一致",
            "is_elective": False, "derived_requirement": "认识自然界多样化运动形式与物质永恒运动观点",
            "review_status": "pending", "legacy_mappings": ["physics.mech.motion"]
        },

        # --- 2.2 机械运动和力 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:length_time:c17",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "长度与时间测量及估测",
            "section_type": "content_requirement", "clause_number": "2.2.1",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "会选用适当的工具测量长度和时间，会根据生活经验估测长度和时间。",
            "standardized_text": "熟练掌握刻度尺的零刻度线、分度值与读数估读规则；会用停表测时间；能根据身体尺度或日常经验准确估测课桌高度、教室长度与活动时间。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.1完全一致",
            "is_elective": False, "derived_requirement": "规范使用刻度尺和秒表，具备生活经验的长度与时间估测能力",
            "review_status": "pending", "legacy_mappings": ["physics.mech.motion"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:speed_calc:c18",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "速度描述与测量计算",
            "section_type": "content_requirement", "clause_number": "2.2.2",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "能用速度描述物体运动的快慢，并能进行简单计算。会测量物体运动的速度。",
            "standardized_text": "掌握速度定义与公式 v=s/t 及单位换算；掌握利用斜面和小车测量物体运动平均速度的实验；能分析匀速与变速运动的 s-t 和 v-t 图像并计算速度。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.2完全一致",
            "is_elective": False, "derived_requirement": "速度公式综合计算、测小车平均速度实验与运动图像分析",
            "review_status": "pending", "legacy_mappings": ["physics.mech.motion"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:force_common:c19",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "重力弹力摩擦力与作用效果",
            "section_type": "content_requirement", "clause_number": "2.2.3",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "通过常见事例或实验，了解重力、弹力和摩擦力，认识力的作用效果。探究并了解滑动摩擦力的大小与哪些因素有关。",
            "standardized_text": "认识力的作用是相互的；掌握力的两大作用效果（形变、改变运动状态）；掌握重力（G=mg，竖直向下）、弹力（弹簧测力计）与摩擦力；探究滑动摩擦力影响因素并掌握增大或减小摩擦的方法。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.3完全一致",
            "is_elective": False, "derived_requirement": "三种常见力分析、力的作用效果及探究滑动摩擦力影响因素实验",
            "review_status": "pending", "legacy_mappings": ["physics.mech.forces"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:force_diagram:c20",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "力的示意图与二力合成平衡",
            "section_type": "content_requirement", "clause_number": "2.2.4",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "能用示意图描述力。会测量力的大小。了解同一直线上的二力合成。知道二力平衡条件。",
            "standardized_text": "掌握力的三要素与规范绘制受力分析示意图；会用弹簧测力计测量力；掌握同一直线上二力的合成法则；掌握二力平衡条件（等大、反向、共线、同体）及其与相互作用力的严格区别。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.4完全一致",
            "is_elective": False, "derived_requirement": "力的示意图规范作图、弹簧测力计测力及二力平衡状态分析",
            "review_status": "pending", "legacy_mappings": ["physics.mech.forces", "physics.mech.balance"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:newton_inertia:c21",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "牛顿第一定律与惯性现象",
            "section_type": "content_requirement", "clause_number": "2.2.5",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "通过实验和科学推理，认识牛顿第一定律。能运用物体的惯性解释自然界和生活中的有关现象。",
            "standardized_text": "经历阻力对物体运动影响的实验，运用伽利略理想实验科学推理建立牛顿第一定律；理解惯性是物体的固有属性（只与质量有关）；运用惯性解释刹车前倾、安全带与行车安全等现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.5完全一致",
            "is_elective": False, "derived_requirement": "牛顿第一定律科学推理方法、惯性属性理解与生活安全现象解释",
            "review_status": "pending", "legacy_mappings": ["physics.mech.balance"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:simple_machine:c22",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "简单机械与杠杆平衡条件",
            "section_type": "content_requirement", "clause_number": "2.2.6",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "知道简单机械。探究并了解杠杆的平衡条件。",
            "standardized_text": "认识杠杆五要素并准确画出动力臂和阻力臂；通过实验探究得出杠杆平衡条件 F1L1=F2L2；掌握省力/费力/等臂杠杆辨析；认识定滑轮、动滑轮与滑轮组省力特点。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.6完全一致",
            "is_elective": False, "derived_requirement": "力臂作图、探究杠杆平衡条件实验及滑轮组省力分析",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:solid_pressure:c23",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "压强概念与改变压强方法",
            "section_type": "content_requirement", "clause_number": "2.2.7",
            "pdf_page": 15 + pdf_offset, "print_page": 15,
            "raw_text": "通过实验，理解压强。知道增大和减小压强的方法，并了解其在生产生活中的应用。",
            "standardized_text": "实验探究压力的作用效果与压力和受力面积的关系，理解压强公式 p=F/S；掌握增大压强（刀刃锋利、图钉尖）和减小压强（履带、宽肩带）的实际方法及应用计算。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第15页（PDF第22页）条文2.2.7完全一致",
            "is_elective": False, "derived_requirement": "压强概念计算、增大减小压强方法辨析与实际应用",
            "review_status": "pending", "legacy_mappings": ["physics.mech.pressure"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:fluid_pressure:c24",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "液体压强与大气压强流体压强",
            "section_type": "content_requirement", "clause_number": "2.2.8",
            "pdf_page": 16 + pdf_offset, "print_page": 16,
            "raw_text": "探究并了解液体压强与哪些因素有关。知道大气压强及其与人类生活的关系。了解流体压强与流速的关系及其在生产生活中的应用。",
            "standardized_text": "探究液体内部压强特点（深度、液体密度，p=ρgh）；理解连通器；掌握证明大气压存在的实验（马德堡半球）与托里拆利测定标准大气压；掌握流速大压强小的伯努利原理与飞机升力解释。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第16页（PDF第23页）条文2.2.8完全一致",
            "is_elective": False, "derived_requirement": "液体压强探究、大气压强测定与流体压强流速关系应用",
            "review_status": "pending", "legacy_mappings": ["physics.mech.pressure"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:buoyancy_archimedes:c25",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.2 机械运动和力", "sub_theme": "浮力探究阿基米德原理与浮沉条件",
            "section_type": "content_requirement", "clause_number": "2.2.9",
            "pdf_page": 16 + pdf_offset, "print_page": 16,
            "raw_text": "通过实验，认识浮力。探究并了解浮力大小与哪些因素有关。知道阿基米德原理，能运用物体的浮沉条件说明生产生活中的有关现象。",
            "standardized_text": "理解浮力产生机理（上下表面压力差）；掌握阿基米德原理 F浮=G排=ρ液gV排；掌握物体浮沉条件（漂浮、悬浮、沉底受力与密度关系）及潜水艇、轮船、热气球的应用分析。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第16页（PDF第23页）条文2.2.9完全一致",
            "is_elective": False, "derived_requirement": "阿基米德原理探究实验、浮力多方法计算与浮沉条件综合应用",
            "review_status": "pending", "legacy_mappings": ["physics.mech.buoyancy"]
        },

        # --- 2.3 声和光 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:sound_produce:c26",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "声音产生与传播条件",
            "section_type": "content_requirement", "clause_number": "2.3.1",
            "pdf_page": 16 + pdf_offset, "print_page": 16,
            "raw_text": "通过实验，认识声的产生和传播条件。",
            "standardized_text": "实验认识声音由发声体振动产生（转换法显示微小振动）；掌握声音传播需要介质（固体、液体、气体），真空不能传声（真空罩实验科学推理）；掌握空气声速（15℃为340m/s）。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第16页（PDF第23页）条文2.3.1完全一致",
            "is_elective": False, "derived_requirement": "声音产生机理、真空罩实验科学推理与介质传播特点",
            "review_status": "pending", "legacy_mappings": ["physics.sound"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:sound_features:c27",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "声音特性与噪声危害控制",
            "section_type": "content_requirement", "clause_number": "2.3.2",
            "pdf_page": 17 + pdf_offset, "print_page": 17,
            "raw_text": "了解声音的特性。了解现代技术中声学知识的一些应用。知道噪声的危害及控制方法。",
            "standardized_text": "掌握声音三要素：音调（由频率决定）、响度（由振幅和距离决定）、音色（由发声体材料结构决定）；了解超声波与次声波应用；掌握在声源处、传播途径中、人耳处控制噪声的三种途径。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第17页（PDF第24页）条文2.3.2完全一致",
            "is_elective": False, "derived_requirement": "声音三要素特征辨析、超声波次声波应用与控制噪声途径",
            "review_status": "pending", "legacy_mappings": ["physics.sound"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:light_reflect_refract:c28",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "光的反射定律与折射现象",
            "section_type": "content_requirement", "clause_number": "2.3.3",
            "pdf_page": 17 + pdf_offset, "print_page": 17,
            "raw_text": "探究并了解光的反射定律。通过实验，了解光的折射现象及其特点。",
            "standardized_text": "探究光的反射定律（三线共面、法线居中、两角相等、光路可逆）；掌握镜面反射与漫反射；实验观察光从空气斜射入水或玻璃中的折射规律（折射角小于入射角），能作规范光路图并解释池水变浅等现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第17页（PDF第24页）条文2.3.3完全一致",
            "is_elective": False, "derived_requirement": "光的反射定律作图、光的折射规律与光路作图及生活折射现象分析",
            "review_status": "pending", "legacy_mappings": ["physics.light.reflection_refraction"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:plane_mirror:c29",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "平面镜成像特点与应用",
            "section_type": "content_requirement", "clause_number": "2.3.4",
            "pdf_page": 17 + pdf_offset, "print_page": 17,
            "raw_text": "探究并了解平面镜成像时像与物的关系。知道平面镜成像的特点及应用。",
            "standardized_text": "实验探究平面镜成像（薄玻璃板等效替代法确定虚像位置）；掌握平面镜成像特点（正立等大虚像、物像到镜面距离相等、连线与镜面垂直、关于镜面对称）；掌握平面镜成像作图与生活潜望镜应用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第17页（PDF第24页）条文2.3.4完全一致",
            "is_elective": False, "derived_requirement": "平面镜成像特点探究实验、对称法规范作图与虚像概念辨析",
            "review_status": "pending", "legacy_mappings": ["physics.light.reflection_refraction"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:lens_imaging:c30",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "透镜成像规律与应用",
            "section_type": "content_requirement", "clause_number": "2.3.5",
            "pdf_page": 17 + pdf_offset, "print_page": 17,
            "raw_text": "了解凸透镜对光的会聚作用和凹透镜对光的发散作用。探究并了解凸透镜成像的规律。了解凸透镜成像规律的应用。",
            "standardized_text": "掌握透镜的三条特殊光线；探究凸透镜成像规律（物距与焦距关系：u>2f成倒立缩小实像、f<u<2f成倒立放大实像、u<f成正立放大虚像）；掌握照相机、投影仪、放大镜原理及近视眼（凹透镜）和远视眼（凸透镜）矫正。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第17页（PDF第24页）条文2.3.5完全一致",
            "is_elective": False, "derived_requirement": "探究凸透镜成像规律实验、光学仪器原理及视力矫正辨析",
            "review_status": "pending", "legacy_mappings": ["physics.light.lens"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:light_dispersion:c31",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.3 声和光", "sub_theme": "白光色散与色光混合",
            "section_type": "content_requirement", "clause_number": "2.3.6",
            "pdf_page": 17 + pdf_offset, "print_page": 17,
            "raw_text": "通过实验，了解白光的组成和不同色光混合的现象。",
            "standardized_text": "通过三棱镜实验观察白光色散分解为红橙黄绿蓝靛紫七色光；知道彩虹形成原理；掌握色光三原色（红、绿、蓝）与物体的颜色成因；了解红外线热效应与紫外线荧光效应应用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第17页（PDF第24页）条文2.3.6完全一致",
            "is_elective": False, "derived_requirement": "白光色散实验、色光三原色混合与不可见光应用",
            "review_status": "pending", "legacy_mappings": ["physics.light.reflection_refraction"]
        },

        # --- 2.4 电和磁 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:static_electricity:c32",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "摩擦起电与静电现象防止利用",
            "section_type": "content_requirement", "clause_number": "2.4.1",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "观察摩擦起电现象，了解静电现象。了解生产生活中关于静电防止和利用的技术。",
            "standardized_text": "认识摩擦起电本质是电荷的转移；掌握两种电荷（正电荷与负电荷）及同种电荷相互排斥、异种电荷相互吸引；掌握验电器原理；了解静电除尘、静电喷涂利用及避雷针防静电危害措施。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.1完全一致",
            "is_elective": False, "derived_requirement": "摩擦起电本质、电荷间相互作用及静电防止与利用常识",
            "review_status": "pending", "legacy_mappings": ["physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:magnetic_field:c33",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "磁场概念与地磁场",
            "section_type": "content_requirement", "clause_number": "2.4.2",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "通过实验，认识磁场。知道地磁场。",
            "standardized_text": "认识磁体磁极间相互作用（同名磁极相斥、异名磁极相吸）；通过铁屑和小磁针认识磁场与磁感线模型（磁体外部磁感线从N极出来回到S极）；知道地球本身是一个大磁体及地磁南极在地理北极附近。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.2完全一致",
            "is_elective": False, "derived_requirement": "磁场基本性质、磁感线模型与地磁场特点",
            "review_status": "pending", "legacy_mappings": ["physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:current_magnetic:c34",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "电流磁效应通电螺线管与电磁铁",
            "section_type": "content_requirement", "clause_number": "2.4.3",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "通过实验，了解电流周围存在磁场。探究并了解通电螺线管外部磁场的方向。了解电磁铁在生产生活中的应用。",
            "standardized_text": "通过奥斯特实验认识电流周围存在磁场；探究通电螺线管外部磁场分布与条形磁体相似；熟练运用安培定则判定电流方向与螺线管磁极；探究影响电磁铁磁性强弱因素及电磁继电器应用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.3完全一致",
            "is_elective": False, "derived_requirement": "奥斯特实验、安培定则判定磁极及电磁铁探究与电磁继电器电路",
            "review_status": "pending", "legacy_mappings": ["physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:magnetic_force_wire:c35",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "磁场对通电导线作用与电动机",
            "section_type": "content_requirement", "clause_number": "2.4.4",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "通过实验，了解通电导线在磁场中会受到力的作用，并知道力的方向与哪些因素有关。",
            "standardized_text": "实验了解磁场对通电导体产生力的作用，知道受力方向与磁场方向、电流方向有关；掌握直流电动机的工作原理（通电线圈在磁场中受力转动、换向器的作用），认识电能转化为机械能。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.4完全一致",
            "is_elective": False, "derived_requirement": "磁场对通电导线作用实验、电动机工作原理及能量转化",
            "review_status": "pending", "legacy_mappings": ["physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:electromagnetic_induct:c36",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "电磁感应现象与发电机",
            "section_type": "content_requirement", "clause_number": "2.4.5",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "探究并了解导体在磁场中运动时产生感应电流的条件。了解电磁感应在生产生活中的应用。",
            "standardized_text": "探究闭合电路的一部分导体在磁场中做切割磁感线运动时产生感应电流的条件（法拉第电磁感应）；知道感应电流方向与磁场方向和导体运动方向有关；掌握交流发电机原理（机械能转化为电能）。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.5完全一致",
            "is_elective": False, "derived_requirement": "探究电磁感应产生条件实验、发电机原理及与电动机对比辨析",
            "review_status": "pending", "legacy_mappings": ["physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:electromagnetic_wave:c37",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "2.4 电和磁", "sub_theme": "电磁波特性与现代通信应用",
            "section_type": "content_requirement", "clause_number": "2.4.6",
            "pdf_page": 18 + pdf_offset, "print_page": 18,
            "raw_text": "知道电磁波。知道电磁波在真空中的传播速度。知道波长、频率和波速。了解电磁波的应用及其对人类生活和社会发展的影响。",
            "standardized_text": "知道电磁波的产生与真空传播速度 c=3×10^8 m/s；掌握波速、波长与频率的关系 c=λf；了解广播、电视、5G移动通信与北斗卫星通信中电磁波的广泛应用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第18页（PDF第25页）条文2.4.6完全一致",
            "is_elective": False, "derived_requirement": "电磁波波速公式计算与现代无线通信科技应用常识",
            "review_status": "pending", "legacy_mappings": ["physics.elec.circuit", "physics.elec.magnetism"]
        },
        # --- 运动和相互作用学业要求 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:acad_req:motion_overview:c38",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（二）运动和相互作用",
            "theme_title": "运动和相互作用学业要求", "sub_theme": "运动和力及声光电磁综合素养",
            "section_type": "academic_requirement", "clause_number": "运动学业要求①",
            "pdf_page": 19 + pdf_offset, "print_page": 19,
            "raw_text": "了解机械运动、分子热运动、声和光、电和磁，了解重力、弹力、摩擦力，通过牛顿第一定律和力的作用效果，认识机械运动和力的关系；能用这些知识解释自然界的有关现象，解决日常生活中的有关问题，形成初步的运动和相互作用观念。",
            "standardized_text": "系统掌握运动与力的关系、声光规律及电磁作用规律，建立因果分析与证据推理思维，形成运动和相互作用观念。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第19页（PDF第26页）运动和相互作用学业要求第(1)条完全一致",
            "is_elective": False, "derived_requirement": "运动和相互作用主题综合学业考查与诊断核心要求",
            "review_status": "pending", "legacy_mappings": ["physics.mech.motion", "physics.mech.forces", "physics.sound"]
        },

        # =========================================================================
        # 一级主题 3：能量 (motion_energy)
        # =========================================================================
        # --- 3.1 能量、能量的转化和转移 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_forms:c39",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.1 能量、能量的转化和转移", "sub_theme": "能量形式与生活生产联系",
            "section_type": "content_requirement", "clause_number": "3.1.1",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "了解能量及其存在的不同形式。能描述不同形式的能量和生产生活的联系。",
            "standardized_text": "认识机械能、内能、电能、光能、化学能、核能等不同存在形式；能结合日常电器、机械车辆与生命活动描述各种能量与人类生产生活的紧密联系。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第22页（PDF第29页）条文3.1.1完全一致，补全R2报告指出3.1主题遗漏条款",
            "is_elective": False, "derived_requirement": "认识能量不同形式与生活实际紧密联系",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_transfer:c40",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.1 能量、能量的转化和转移", "sub_theme": "能量转移与相互转化",
            "section_type": "content_requirement", "clause_number": "3.1.2",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "通过实验，认识能量可以从一个物体转移到其他物体，不同形式的能量可以相互转化。",
            "standardized_text": "通过碰撞、热传导等实验认识能量的转移；通过摩擦生热、水电站发电、太阳能利用等实例认识机械能、内能、电能、光能之间的相互转化规律。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第22页（PDF第29页）条文3.1.2完全一致，补全R2报告指出3.1主题遗漏条款",
            "is_elective": False, "derived_requirement": "实验认识能量的转移过程与不同形式能量相互转化规律",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work", "physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:work_concept:c41",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.1 能量、能量的转化和转移", "sub_theme": "功的概念与能量转化过程",
            "section_type": "content_requirement", "clause_number": "3.1.3",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "结合实例，认识功的概念。知道做功的过程就是能量转化或转移的过程。",
            "standardized_text": "理解力学中做功的两个必要因素（作用在物体上的力、物体在力的方向上移动的距离）；知道做功的实质是能量转化或转移的量度（做了多少功就有多少能量发生转化或转移）。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第22页（PDF第29页）条文3.1.3完全一致，补全R2报告指出3.1主题遗漏条款",
            "is_elective": False, "derived_requirement": "掌握做功两个必要因素及做功反映能量转化转移本质",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },

        # --- 3.2 机械能 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:mech_energy:c42",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.2 机械能", "sub_theme": "动能势能与机械能转化",
            "section_type": "content_requirement", "clause_number": "3.2.1",
            "pdf_page": 22 + pdf_offset, "print_page": 22,
            "raw_text": "知道动能、势能和机械能。通过实验，了解动能和势能的相互转化。举例说明机械能和其他形式能量的相互转化。",
            "standardized_text": "掌握动能（质量、速度）、重力势能（质量、高度）与弹性势能；掌握荡秋千、滚摆实验中动能与势能的相互转化与守恒；结合水电站与机械运行分析机械能与电能、内能转化。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第22页（PDF第29页）条文3.2.1完全一致",
            "is_elective": False, "derived_requirement": "动能重力势能弹性势能影响因素探究与机械能守恒分析",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:work_power:c43",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.2 机械能", "sub_theme": "机械功与功率含义计算",
            "section_type": "content_requirement", "clause_number": "3.2.2",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "知道机械功和功率。用生活中的实例说明机械功和功率的含义。",
            "standardized_text": "掌握机械功公式 W=Fs（单位J）；掌握功率概念（表示做功快慢的物理量）与计算公式 P=W/t=Fv（单位W、kW）；能运用功和功率公式解决起重机提物、汽车行驶等生活实际计算。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.2.2完全一致",
            "is_elective": False, "derived_requirement": "功和功率公式综合计算及做功快慢物理意义理解",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:mech_efficiency:c44",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.2 机械能", "sub_theme": "机械效率意义与提高途径",
            "section_type": "content_requirement", "clause_number": "3.2.3",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "知道机械效率。了解提高机械效率的意义和途径。",
            "standardized_text": "理解有用功、额外功与总功（W总=W有+W额）；掌握机械效率定义式 η=W有/W总×100%；会测量滑轮组或斜面的机械效率；了解减小机械自重与摩擦以提高机械效率的途径与意义。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.2.3完全一致",
            "is_elective": False, "derived_requirement": "测滑轮组机械效率实验、效率计算公式运用与提高效率途径分析",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:machinery_history:c45",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.2 机械能", "sub_theme": "机械利用对社会发展的作用",
            "section_type": "content_requirement", "clause_number": "3.2.4",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "能说出人类使用的一些机械。了解机械的使用对社会发展的作用。",
            "standardized_text": "列举水磨、天工开物汲水装置、现代工业起重机等机械应用，认识机械解放人力、提高生产力与推动社会文明进程的重要价值。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.2.4完全一致",
            "is_elective": False, "derived_requirement": "了解机械使用发展史与科技推动社会生产力进步的意义",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work"]
        },

        # --- 3.3 内能 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:internal_heat:c46",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.3 内能", "sub_theme": "内能热量与燃料热值",
            "section_type": "content_requirement", "clause_number": "3.3.1",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "了解内能和热量。从能量转化的角度认识燃料的热值。",
            "standardized_text": "掌握内能是分子动能与分子势能的总和；掌握改变内能的两种方式（做功和热传递实质相同）；理解热量含义；掌握燃料完全燃烧释放热量与热值公式 Q=mq 或 Q=Vq（单位J/kg、J/m³）。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.3.1完全一致",
            "is_elective": False, "derived_requirement": "改变内能方式辨析、热量计算及燃料热值公式综合应用",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:specific_heat:c47",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.3 内能", "sub_theme": "比热容探究与热量计算",
            "section_type": "content_requirement", "clause_number": "3.3.2",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "通过实验，了解比热容。能运用比热容说明简单的自然现象。",
            "standardized_text": "实验比较不同物质吸热升温特点（控制变量法），理解比热容概念；熟练运用热量计算公式 Q=cmΔt；运用水比热容大的特性解释沙漠昼夜温差大、沿海温和与汽车水冷散热等现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.3.2完全一致",
            "is_elective": False, "derived_requirement": "探究比热容实验、Q=cmΔt综合热量计算与水比热容大应用解释",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:heat_engine:c48",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.3 内能", "sub_theme": "热机工作原理与社会意义",
            "section_type": "content_requirement", "clause_number": "3.3.3",
            "pdf_page": 23 + pdf_offset, "print_page": 23,
            "raw_text": "了解热机的工作原理。知道内能的利用在人类社会发展史中的重要意义。",
            "standardized_text": "掌握四冲程内燃机（吸气、压缩、做功、排气）工作原理与能量转化过程（压缩冲程机械能转内能，做功冲程内能转机械能）；掌握热机效率概念；认识蒸汽机内燃机推动工业革命的重要作用与尾气环保问题。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第23页（PDF第30页）条文3.3.3完全一致",
            "is_elective": False, "derived_requirement": "四冲程内燃机工作过程辨析、能量转化分析及热机效率计算",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },

        # --- 3.4 电磁能 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:power_supply:c49",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "电源和用电器能量转化",
            "section_type": "content_requirement", "clause_number": "3.4.1",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "从能量转化的角度认识电源和用电器的作用。",
            "standardized_text": "理解电源是把其他形式能量（化学能、机械能等）转化为电能的装置；用电器是把电能转化为其他形式能量（内能、光能、机械能等）的装置。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.1完全一致",
            "is_elective": False, "derived_requirement": "从能量转化视角深刻理解电源与用电器的物理本质",
            "review_status": "pending", "legacy_mappings": ["physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:ohm_law:c50",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "电压电流电阻关系与欧姆定律",
            "section_type": "content_requirement", "clause_number": "3.4.2",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "知道电压、电流和电阻。探究电流与电压、电阻的关系，理解欧姆定律。",
            "standardized_text": "掌握电流形成与方向、电压作用（电源提供电压）、电阻概念及影响电阻因素；通过控制变量法探究电流与电压成正比、与电阻成反比；深刻理解欧姆定律公式 I=U/R 并进行动态电路综合计算。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.2完全一致",
            "is_elective": False, "derived_requirement": "探究电流与电压电阻关系实验、欧姆定律公式及动态电路极值综合计算",
            "review_status": "pending", "legacy_mappings": ["physics.elec.ohm"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:meters_use:c51",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "电流表与电压表使用",
            "section_type": "content_requirement", "clause_number": "3.4.3",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "会使用电流表和电压表。",
            "standardized_text": "掌握电流表（串联接入、正进负出、严禁短路）与电压表（并联接入、正进负出、可测电源电压）的选择量程、试触、连接规范与精确读数规则。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.3完全一致",
            "is_elective": False, "derived_requirement": "电流表与电压表规范连接、量程选取与读数读图技能",
            "review_status": "pending", "legacy_mappings": ["physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:circuit_rules:c52",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "电路图串并联连接与电流电压规律",
            "section_type": "content_requirement", "clause_number": "3.4.4",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "会看、会画简单的电路图。会连接简单的串联电路和并联电路。说出生产生活中采用简单串联或并联电路的实例。了解串并联电路电流和电压的特点。",
            "standardized_text": "掌握电路基本组成（电源、开关、用电器、导线）与电路图符号画法；掌握串联电路（I=I1=I2，U=U1+U2）和并联电路（I=I1+I2，U=U1=U2）的电流与电压规律；能根据实物图画电路图或按电路图连实物。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.4完全一致",
            "is_elective": False, "derived_requirement": "电路图规范作图、串并联连接与电路电流电压规律综合计算",
            "review_status": "pending", "legacy_mappings": ["physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:electric_power:c53",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "电功电功率与额定功率",
            "section_type": "content_requirement", "clause_number": "3.4.5",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "结合实例，了解电功和电功率。知道用电器的额定功率和实际功率。",
            "standardized_text": "掌握电能表读数与电功公式 W=UIt=Pt（单位J、kW·h）；掌握电功率物理意义（表示消耗电能快慢）及公式 P=UI=W/t；理解额定电压、额定功率与实际电压、实际功率的区别并进行电功率综合计算。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.5完全一致",
            "is_elective": False, "derived_requirement": "电能表计算、电功率综合计算（P=UI及其推导式）与额定实际功率辨析",
            "review_status": "pending", "legacy_mappings": ["physics.elec.power"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:joule_law:c54",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "焦耳定律探究与电热利用防止",
            "section_type": "content_requirement", "clause_number": "3.4.6",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "通过实验，了解焦耳定律。能用焦耳定律说明生产生活中的有关现象。",
            "standardized_text": "探究电流通过导体产生的热量与电流、电阻和通电时间的关系（转换法与控制变量法）；深刻理解焦耳定律公式 Q=I²Rt；能区分纯电阻电路（Q=W）与非纯电阻电路（W=Q+E机）；解释电炉、电烙铁利用电热与电脑风扇散热防电热现象。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.6完全一致",
            "is_elective": False, "derived_requirement": "探究焦耳定律实验、Q=I²Rt公式综合计算与电热利用防止分析",
            "review_status": "pending", "legacy_mappings": ["physics.elec.power"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:household_safety:c55",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.4 电磁能", "sub_theme": "家庭电路组成与安全节约用电",
            "section_type": "content_requirement", "clause_number": "3.4.7",
            "pdf_page": 24 + pdf_offset, "print_page": 24,
            "raw_text": "了解家庭电路的组成。有安全用电和节约用电的意识。",
            "standardized_text": "掌握家庭电路组成（进户线、电能表、总开关、保险装置、插座、用电器）；掌握火线与零线、试电笔的使用；掌握三孔插座（左零右火上接地）与金属外壳接地防触电；掌握安全用电原则（不接触低压带电体、不靠近高压带电体）与防雷避险常识。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第24页（PDF第31页）条文3.4.7完全一致",
            "is_elective": False, "derived_requirement": "家庭电路布线连接、试电笔规范使用与触电急救安全用电常识",
            "review_status": "pending", "legacy_mappings": ["physics.elec.power"]
        },

        # --- 3.5 能量守恒 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_conservation:c56",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.5 能量守恒", "sub_theme": "能量守恒定律与守恒分析",
            "section_type": "content_requirement", "clause_number": "3.5.1",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "知道能量守恒定律。列举日常生活中能量守恒的实例。有用能量转化与守恒的观点分析问题的意识。",
            "standardized_text": "理解能量既不会凭空产生，也不会凭空消失，只能从一种形式转化为其他形式，或从一个物体转移到其他物体，在转化和转移过程中能量的总量保持不变；能运用守恒观点分析机械运动、热机与电器的能流图。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.5.1完全一致",
            "is_elective": False, "derived_requirement": "深刻理解能量守恒定律并树立能量分析守恒思想",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work", "physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_efficiency:c57",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.5 能量守恒", "sub_theme": "能量转化与转移效率",
            "section_type": "content_requirement", "clause_number": "3.5.2",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "从能量转化和转移的角度认识效率。",
            "standardized_text": "认识任何能源利用过程中都不可能达到100%转化，理解输入总能量、输出有用能量与散失损耗能量的平衡关系，树立提升装置热效率与综合能源利用率的科学观念。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.5.2完全一致",
            "is_elective": False, "derived_requirement": "从能量转化转移角度认识效率并分析提升效率途径",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work", "physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_direction:c58",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.5 能量守恒", "sub_theme": "能量转化和转移的方向性",
            "section_type": "content_requirement", "clause_number": "3.5.3",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "列举能量转化和转移具有方向性的常见实例。",
            "standardized_text": "列举热传递自发从高温物体传向低温物体、汽车刹车后机械能转化的内能无法自动变回机械能等典型实例，深刻认识能量虽然守恒但品质退降，因此必须节约能源。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.5.3完全一致",
            "is_elective": False, "derived_requirement": "理解能量转化与转移的方向性，深刻领会节约能源的必要性",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },

        # --- 3.6 能源与可持续发展 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:energy_resources:c59",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.6 能源与可持续发展", "sub_theme": "可再生与不可再生能源分类",
            "section_type": "content_requirement", "clause_number": "3.6.1",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "列举常见的不可再生能源和可再生能源。",
            "standardized_text": "知道化石能源（煤、石油、天然气）是不可再生能源；太阳能、风能、水能、地热能、生物质能是可再生能源；理解能源结构的优化对可持续发展的战略意义。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.6.1完全一致，补全R2报告指出3.6主题遗漏条款",
            "is_elective": False, "derived_requirement": "不可再生与可再生能源准确分类与能源结构认识",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:nuclear_energy:c60",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.6 能源与可持续发展", "sub_theme": "核能等新能源特点与安全环保",
            "section_type": "content_requirement", "clause_number": "3.6.2",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "知道核能等新能源的特点和可能带来的问题。",
            "standardized_text": "了解原子核裂变（核电站受控链式反应）与核聚变（太阳内部反应、受控人造太阳EAST进展）；认识核能高效清洁特点及核泄漏防范与核废料安全处置问题。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.6.2完全一致，补全R2报告指出3.6主题遗漏条款",
            "is_elective": False, "derived_requirement": "核裂变与聚变特点、核电站原理及安全防护常识",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:content_req:solar_sustainable:c61",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "3.6 能源与可持续发展", "sub_theme": "太阳能利用与环境保护意识",
            "section_type": "content_requirement", "clause_number": "3.6.3",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "了解太阳能的利用。知道能源的利用对人类社会发展所产生的影响，树立节约能源和保护环境的意识。",
            "standardized_text": "了解光热转换（太阳能热水器）与光电转换（光伏发电）；认识过度消耗化石能源带来的温室效应、雾霾与酸雨危害；牢固树立绿水青山就是金山银山与低碳节能环保理念。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25页（PDF第32页）条文3.6.3完全一致，补全R2报告指出3.6主题遗漏条款",
            "is_elective": False, "derived_requirement": "太阳能利用形式、化石能源环境影响与低碳节能意识",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.heat"]
        },
        # --- 能量学业要求 ---
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:acad_req:energy_overview:c62",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "四、课程内容", "domain_title": "（三）能量",
            "theme_title": "能量学业要求", "sub_theme": "能量守恒与转化转移综合素养",
            "section_type": "academic_requirement", "clause_number": "能量学业要求①",
            "pdf_page": 25 + pdf_offset, "print_page": 25,
            "raw_text": "能列举能量转化和转移的实例，知道能量在转化和转移过程中是守恒的，认识机械功、热量、电功、热值等是与能量转化或转移密切相关的物理量，知道它们的含义；能用能量转化与守恒的观点解释常见的自然现象，解决日常生活中的有关问题，形成初步的能量观念。",
            "standardized_text": "形成贯通机械能、内能、电磁能与能源转化的能量观念，掌握机械功、热量、电功、焦耳定律与能量守恒的综合推理分析能力。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第25~26页（PDF第32~33页）能量学业要求第(1)条完全一致",
            "is_elective": False, "derived_requirement": "能量主题综合学业考查与诊断核心要求",
            "review_status": "pending", "legacy_mappings": ["physics.mech.work", "physics.thermal.heat", "physics.elec.power"]
        },

        # =========================================================================
        # 一级主题 4：实验探究 (experiment)
        # =========================================================================
        # --- 4.1 测量类学生必做实验 (9 项) ---
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_mass:c63",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "天平测量质量必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.1",
            "pdf_page": 28 + pdf_offset, "print_page": 28,
            "raw_text": "用托盘天平测量物体的质量。",
            "standardized_text": "规范使用托盘天平测量固体小木块与烧杯中液体的质量，掌握调零、放砝码与游码读数操作技能。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第28页（PDF第35页）条文4.1.1完全一致",
            "is_elective": False, "derived_requirement": "托盘天平测量物体质量必做实验操作与数据记录",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_density:c64",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "测量固体和液体的密度必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.2",
            "pdf_page": 28 + pdf_offset, "print_page": 28,
            "raw_text": "测量固体和液体的密度。",
            "standardized_text": "使用托盘天平和量筒测量不规则固体小石块与盐水液体密度的实验步骤设计、数据表格记录及误差控制分析。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第28页（PDF第35页）条文4.1.2完全一致",
            "is_elective": False, "derived_requirement": "测定固体液体密度必做实验流程设计与误差分析",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_temperature:c65",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "温度计测量温度必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.3",
            "pdf_page": 28 + pdf_offset, "print_page": 28,
            "raw_text": "用常见温度计测量温度。",
            "standardized_text": "用实验室常用温度计测定水温及用体温计测量体温，掌握温度计玻璃泡完全浸入、不碰壁底与视线平齐的读数要领。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第28页（PDF第35页）条文4.1.3完全一致",
            "is_elective": False, "derived_requirement": "温度计测量水温与体温计规范使用必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.thermal.state"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_length_time:c66",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "测量长度与时间必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.4",
            "pdf_page": 28 + pdf_offset, "print_page": 28,
            "raw_text": "用刻度尺测量长度，用表测量时间。",
            "standardized_text": "用毫米刻度尺规范测量教科书的长宽厚（估读至分度值下一位），用机械停表或电子表测量脉搏跳动所用时间。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第28页（PDF第35页）条文4.1.4完全一致",
            "is_elective": False, "derived_requirement": "刻度尺测量长度与秒表测时间必做实验规范操作",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.motion"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_speed:c67",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "测量物体运动速度必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.5",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "测量物体运动的速度。",
            "standardized_text": "用刻度尺测路程s、用停表测时间t，在倾斜小车轨道上测定小球或小车通过前半段、后半段及全程的平均速度，得出小车做加速运动结论。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.1.5完全一致",
            "is_elective": False, "derived_requirement": "测量物体运动平均速度必做实验设计与计算",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.motion"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_force:c68",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "弹簧测力计测力必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.6",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "用弹簧测力计测量力。",
            "standardized_text": "掌握弹簧测力计在力的测量方向上调零，拉动挂钩体验力的大小，规范测量钩码与物理教科书所受重力及水平拉力。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.1.6完全一致",
            "is_elective": False, "derived_requirement": "弹簧测力计测量力必做实验使用技巧与读数",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.forces"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_current:c69",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "电流表测量电流必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.7",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "用电流表测量电流。",
            "standardized_text": "使用实验室指针式直流电流表，将其正确串联接入直流电路，选用合适量程准确测量干路与支路电流大小。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.1.7完全一致",
            "is_elective": False, "derived_requirement": "电流表测量直流电流必做实验连接与读数技能",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_voltage:c70",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "电压表测量电压必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.8",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "用电压表测量电压。",
            "standardized_text": "使用实验室指针式直流电压表，将其正确并联在待测电路两端，准确测量电池电压及灯泡两端工作电压。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.1.8完全一致",
            "is_elective": False, "derived_requirement": "电压表测量直流电压必做实验连接与读数技能",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:exp_resistance:c71",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.1 测量类学生必做实验", "sub_theme": "伏安法测量电阻必做实验",
            "section_type": "content_requirement", "clause_number": "4.1.9",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "用电流表和电压表测量电阻。",
            "standardized_text": "伏安法测电阻（R=U/I）：连接电路、用滑动变阻器改变电压与电流实现多次测量求平均值减小误差，测定小灯泡电阻并发现灯丝电阻随温度升高而增大的物理规律。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.1.9完全一致",
            "is_elective": False, "derived_requirement": "伏安法测定定值电阻与小灯泡电阻必做实验全流程综合",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.ohm"]
        },

        # --- 4.2 探究类学生必做实验 (12 项) ---
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_boiling:c72",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "水沸腾前后温度变化特点",
            "section_type": "content_requirement", "clause_number": "4.2.1",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "探究水在沸腾前后温度变化的特点。",
            "standardized_text": "用酒精灯、烧杯、温度计探究水沸腾过程，绘制温度-时间曲线，得出水在沸腾时持续吸热但温度保持在沸点不变的结论，观察气泡在沸腾前后的上升变化。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.2.1完全一致",
            "is_elective": False, "derived_requirement": "探究水在沸腾前后温度变化图像与特点必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.thermal.state"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_sliding_friction:c73",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "滑动摩擦力大小影响因素探究",
            "section_type": "content_requirement", "clause_number": "4.2.2",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "探究滑动摩擦力大小与哪些因素有关。",
            "standardized_text": "运用控制变量法，用弹簧测力计匀速水平拉动木块（二力平衡使拉力等于摩擦力），探究压力大小、接触面粗糙程度对滑动摩擦力的影响。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.2.2完全一致",
            "is_elective": False, "derived_requirement": "探究滑动摩擦力大小影响因素控制变量法实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.forces"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_liquid_pressure:c74",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "液体压强影响因素探究",
            "section_type": "content_requirement", "clause_number": "4.2.3",
            "pdf_page": 29 + pdf_offset, "print_page": 29,
            "raw_text": "探究液体压强与哪些因素有关。",
            "standardized_text": "使用压强计（U形管液面高度差转换法反映压强大小），探究同一深度各方向压强相等、深度越深压强越大及液体密度越大压强越大等规律。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第29页（PDF第36页）条文4.2.3完全一致",
            "is_elective": False, "derived_requirement": "探究液体压强影响因素压强计转换法必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.pressure"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_buoyancy:c75",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "浮力大小影响因素探究",
            "section_type": "content_requirement", "clause_number": "4.2.4",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究浮力大小与哪些因素有关。",
            "standardized_text": "采用称重法（F浮=G-F示），探究金属块浸入液体的体积、液体密度与物体浸没深度对所受浮力大小的影响，验证浮力只与排开液体体积和液体密度有关。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.4完全一致",
            "is_elective": False, "derived_requirement": "探究浮力大小与哪些因素有关称重法实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.buoyancy"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_lever_balance:c76",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "杠杆平衡条件探究",
            "section_type": "content_requirement", "clause_number": "4.2.5",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究杠杆的平衡条件。",
            "standardized_text": "调平衡螺母使杠杆在水平位置平衡（便于直接从杠杆上读取力臂），改变钩码数量和位置多次实验，归纳得出动力×动力臂=阻力×阻力臂（F1L1=F2L2）。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.5完全一致",
            "is_elective": False, "derived_requirement": "探究杠杆平衡条件必做实验操作与水平平衡调节分析",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.work"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_light_reflection:c77",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "光的反射定律探究",
            "section_type": "content_requirement", "clause_number": "4.2.6",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究光的反射定律。",
            "standardized_text": "用激光笔、平面镜、可折转白色光屏探究三线共面（纸板前后翻折）、两线分居法线两侧，测量入射角与反射角得出两角相等结论并验证光路可逆。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.6完全一致",
            "is_elective": False, "derived_requirement": "探究光的反射定律可折转纸板实验与规律归纳",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.light.reflection_refraction"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_plane_mirror:c78",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "平面镜成像特点探究",
            "section_type": "content_requirement", "clause_number": "4.2.7",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究平面镜成像的特点。",
            "standardized_text": "用透明薄玻璃板代替平面镜，利用两支完全相同的蜡烛通过等效替代法确定虚像位置并比较像物大小，用刻度尺验证物距等于像距及虚像成因。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.7完全一致",
            "is_elective": False, "derived_requirement": "探究平面镜成像特点玻璃板等效替代必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.light.reflection_refraction"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_lens_imaging:c79",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "凸透镜成像规律探究",
            "section_type": "content_requirement", "clause_number": "4.2.8",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究凸透镜成像的规律。",
            "standardized_text": "在光具座上将烛焰中心、凸透镜光心、光屏中心调在同一高度，移动物体改变物距u，测量像距v并观察像的正倒、大小与虚实，总结成像规律。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.8完全一致",
            "is_elective": False, "derived_requirement": "光具座探究凸透镜成像规律必做实验全过程分析",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.light.lens"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_solenoid_magnetic:c80",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "通电螺线管外部磁场方向探究",
            "section_type": "content_requirement", "clause_number": "4.2.9",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究通电螺线管外部磁场的方向。",
            "standardized_text": "用小磁针和铁屑探究通电螺线管外部磁场分布，改变电流方向观察小磁针指向变化，总结右手安培定则。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.9完全一致",
            "is_elective": False, "derived_requirement": "探究通电螺线管磁场方向实验与安培定则验证",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_induction_current:c81",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "产生感应电流条件探究",
            "section_type": "content_requirement", "clause_number": "4.2.10",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究导体在磁场中运动时产生感应电流的条件。",
            "standardized_text": "用蹄形磁体、导线和灵敏电流计探究产生感应电流的必要条件（闭合电路、做切割磁感线运动），观察感应电流方向与磁场方向、运动方向的关系。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.10完全一致",
            "is_elective": False, "derived_requirement": "探究电磁感应产生条件必做实验与电流方向影响因素",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.magnetism"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_circuit_features:c82",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "串并联电路电流电压特点探究",
            "section_type": "content_requirement", "clause_number": "4.2.11",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究串联电路和并联电路中电流、电压的特点。",
            "standardized_text": "用电流表和电压表分别接入串联和并联电路各节点，测量多组数据，归纳串联电路电流处处相等/总电压等于各部分电压之和与并联电路总电流等于各支路电流之和/各支路电压相等的规律。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.11完全一致",
            "is_elective": False, "derived_requirement": "探究串联与并联电路电流电压特点必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:content_req:inq_ohm_relation:c83",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "4.2 探究类学生必做实验", "sub_theme": "电流与电压电阻关系探究",
            "section_type": "content_requirement", "clause_number": "4.2.12",
            "pdf_page": 30 + pdf_offset, "print_page": 30,
            "raw_text": "探究电流与电压、电阻的关系。",
            "standardized_text": "利用定值电阻、滑动变阻器、电压表和电流表，运用控制变量法分别探究电阻一定时电流与电压成正比及电压一定时电流与电阻成反比的实验设计与数据分析。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第30页（PDF第37页）条文4.2.12完全一致",
            "is_elective": False, "derived_requirement": "探究电流与电压电阻关系（欧姆定律探究）必做实验",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.ohm"]
        },
        # --- 实验探究学业要求 ---
        {
            "clause_id": "cs:physics:2022:s4:experiment:acad_req:experiment_overview:c84",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "四、课程内容", "domain_title": "（四）实验探究",
            "theme_title": "实验探究学业要求", "sub_theme": "实验规范操作与科学探究能力评价",
            "section_type": "academic_requirement", "clause_number": "实验学业要求①",
            "pdf_page": 31 + pdf_offset, "print_page": 31,
            "raw_text": "能在实验探究中遵守实验室规则，安全规范使用基本测量仪器，认真严谨采集实验数据，能运用控制变量法等科学方法分析实验现象并得出正确结论。",
            "standardized_text": "在21个必做实验中展现规范实验技能、控制变量与转换法设计能力、实验故障排除与科学探究报告撰写水平。",
            "collation_note": "依据教育部2022年版物理课标印刷第31~33页实验探究学业要求整体提炼",
            "is_elective": False, "derived_requirement": "物理实验操作与科学探究能力综合评价考核核心要求",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },

        # =========================================================================
        # 一级主题 5：跨学科实践 (comp_prac)
        # =========================================================================
        # --- 5.1 物理学与日常生活 ---
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:daily_problem:c85",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.1 物理学与日常生活", "sub_theme": "发现生活物理问题并提出方案",
            "section_type": "content_requirement", "clause_number": "5.1.1",
            "pdf_page": 34 + pdf_offset, "print_page": 34,
            "raw_text": "能发现日常生活中与物理学有关的问题，提出解决方案。",
            "standardized_text": "结合厨房用具、自行车机械构造等日常生活用品发现物理问题，提出技术改良方案，综合运用多学科知识论证方案合理性。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第34页（PDF第41页）条文5.1.1完全一致",
            "is_elective": False, "derived_requirement": "从日常生活情境中发现物理问题并制订解决方案",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:daily_safety:c86",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.1 物理学与日常生活", "sub_theme": "生活安全隐患分析与健康生活",
            "section_type": "content_requirement", "clause_number": "5.1.2",
            "pdf_page": 34 + pdf_offset, "print_page": 34,
            "raw_text": "能运用所学知识分析日常生活中的安全问题，提出解决方案，践行安全与健康生活。",
            "standardized_text": "分析用电安全、乘车惯性防护、高空坠物等生活安全隐患，提出防护与改进建议，践行健康与安全生活方式。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第34页（PDF第41页）条文5.1.2完全一致",
            "is_elective": False, "derived_requirement": "运用物理知识分析日常生活安全问题并提出防护方案",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.elec.power"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:daily_low_carbon:c87",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.1 物理学与日常生活", "sub_theme": "规范个人行为践行低碳生活",
            "section_type": "content_requirement", "clause_number": "5.1.3",
            "pdf_page": 34 + pdf_offset, "print_page": 34,
            "raw_text": "能运用所学知识指导和规范个人行为，践行低碳生活，具有节能环保意识。",
            "standardized_text": "调查空气质量与尾气排放，制订个人低碳生活行为指南，在家庭节电节水、垃圾分类中践行低碳环保行为。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第34页（PDF第41页）条文5.1.3完全一致",
            "is_elective": False, "derived_requirement": "指导规范个人行为践行低碳节能环保实践",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },

        # --- 5.2 物理学与工程实践 ---
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:eng_ancient:c88",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.2 物理学与工程实践", "sub_theme": "古代技术应用案例与科技文明",
            "section_type": "content_requirement", "clause_number": "5.2.1",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "了解我国古代的技术应用案例，体会我国古代科技对人类文明发展的促进作用。",
            "standardized_text": "研究我国古代“龙骨水车”、赵州桥拱券结构、铸造工艺等技术案例，制作古代机械模型，体会古代劳动人民的智慧与科技贡献。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第35页（PDF第42页）条文5.2.1完全一致",
            "is_elective": False, "derived_requirement": "了解我国古代工程科技案例并体会对文明发展的促进作用",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:eng_modern:c89",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.2 物理学与工程实践", "sub_theme": "现代工程技术案例与物理推动作用",
            "section_type": "content_requirement", "clause_number": "5.2.2",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "调查物理学应用于工程技术的案例，体会物理学对工程技术发展的促进作用。",
            "standardized_text": "调查物理在现代大型桥梁建设、高速铁路、水火箭制作或简易风力发电机模型中的应用，体会物理基础理论对现代工程技术的奠基与推动作用。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第35页（PDF第42页）条文5.2.2完全一致",
            "is_elective": False, "derived_requirement": "调查工程技术案例并动手制作工程实践样机模型",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:eng_info:c90",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.2 物理学与工程实践", "sub_theme": "物理学在现代信息技术中的应用",
            "section_type": "content_requirement", "clause_number": "5.2.3",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "了解物理学在信息技术中的应用。",
            "standardized_text": "了解磁记录、光纤通信、激光雷达与量子计算等前沿信息技术中的物理原理，体会物理学对现代信息社会的革命性支撑。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第35页（PDF第42页）条文5.2.3完全一致",
            "is_elective": False, "derived_requirement": "了解物理学在信息记录、传输与处理中的关键应用",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },

        # --- 5.3 物理学与社会发展 ---
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:soc_energy:c91",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.3 物理学与社会发展", "sub_theme": "能源开发利用对社会发展的影响",
            "section_type": "content_requirement", "clause_number": "5.3.1",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "结合实例，尝试分析能源的开发与利用对社会发展的影响。",
            "standardized_text": "结合化石燃料、风光水电与新能源开发实例，分析能源供给与生态环境保护平衡，撰写节能环保小屋方案或能源社会影响调查报告。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第35页（PDF第42页）条文5.3.1完全一致，补全R2报告指出5.3主题遗漏条款",
            "is_elective": False, "derived_requirement": "综合分析能源开发对经济社会与生态环境的深远影响",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.thermal.heat"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:soc_materials:c92",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.3 物理学与社会发展", "sub_theme": "新材料研发应用对社会发展的影响",
            "section_type": "content_requirement", "clause_number": "5.3.2",
            "pdf_page": 35 + pdf_offset, "print_page": 35,
            "raw_text": "结合实例，了解一些新材料的特点及其应用。了解新材料的研发与应用对社会发展的影响。",
            "standardized_text": "了解半导体、超导体、纳米材料、石墨烯等新材料特性与在芯片、超导磁悬浮中的应用，展望新材料技术突破对未来社会的革命性变革。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第35~36页（PDF第42~43页）条文5.3.2完全一致，补全R2报告指出5.3主题遗漏条款",
            "is_elective": False, "derived_requirement": "掌握前沿新材料特性及其对科技产业升级的影响",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry", "physics.mech.density"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:content_req:soc_achievements:c93",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "5.3 物理学与社会发展", "sub_theme": "我国科技成就与科技强国使命感",
            "section_type": "content_requirement", "clause_number": "5.3.3",
            "pdf_page": 36 + pdf_offset, "print_page": 36,
            "raw_text": "了解我国科技发展的成就，增强科技强国的责任感和使命感。",
            "standardized_text": "了解我国“两弹一星”、载人航天、深海探测等伟大科技成就，学习钱学森、邓稼先等老一辈科学家胸怀祖国、勇攀高峰的精神，树立科技报国志向。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第36页（PDF第43页）条文5.3.3完全一致，补全R2报告指出5.3主题遗漏条款",
            "is_elective": False, "derived_requirement": "知晓国家重大科技突破，传承科学家精神，厚植爱国情怀",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },
        # --- 跨学科实践学业要求 ---
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:acad_req:interdisciplinary_overview:c94",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "四、课程内容", "domain_title": "（五）跨学科实践",
            "theme_title": "跨学科实践学业要求", "sub_theme": "跨学科实践能力与社会责任评价",
            "section_type": "academic_requirement", "clause_number": "跨学科学业要求①",
            "pdf_page": 36 + pdf_offset, "print_page": 36,
            "raw_text": "能在跨学科实践中综合认识所涉及的知识；能用物理及其他学科知识解释与健康、安全等有关的日常生活问题，探索一些简单的工程与技术问题，分析与能源、环境等有关的社会热点问题，初步具有运用跨学科知识解决简单问题的能力。",
            "standardized_text": "在日常生活、工程技术与社会发展跨学科情境中，具备发现问题、设计方案、动手制作与合作交流的综合实践创新素养。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第36页（PDF第43页）跨学科实践学业要求第(1)条完全一致",
            "is_elective": False, "derived_requirement": "跨学科综合实践解决问题能力考查与评价核心要求",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },

        # =========================================================================
        # 五、学业质量标准 (academic quality standards)
        # =========================================================================
        {
            "clause_id": "cs:physics:2022:s4:matter:acad_qual:physics_concept:c95",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "matter",
            "part_title": "五、学业质量", "domain_title": "学业质量标准",
            "theme_title": "物理核心素养表现", "sub_theme": "物理观念发展水平",
            "section_type": "academic_requirement", "clause_number": "学业质量·物理观念",
            "pdf_page": 39 + pdf_offset, "print_page": 39,
            "raw_text": "能认识物质的形态、属性及结构，认识运动和力、声和光、电和磁，认识机械能、内能、电磁能及能量的转化与守恒，能掌握所学的物理概念和规律；在学习和日常生活中，能从物理学视角观察事物，把所学概念和规律与实际情境联系起来，解释常见自然现象和解决常见物理问题，能综合运用物理概念和规律，分析和解决熟悉情境下的简单物理问题，具有初步的物理观念。",
            "standardized_text": "整体建立物质观念、运动与相互作用观念、能量观念，掌握核心物理概念规律并能解决实际物理问题。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第39页（PDF第46页）学业质量描述第1段完全一致",
            "is_elective": False, "derived_requirement": "物理观念核心素养终结性评价总体标准",
            "review_status": "pending", "legacy_mappings": ["physics.thermal.state", "physics.mech.forces", "physics.elec.circuit"]
        },
        {
            "clause_id": "cs:physics:2022:s4:motion_energy:acad_qual:scientific_thinking:c96",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "motion_energy",
            "part_title": "五、学业质量", "domain_title": "学业质量标准",
            "theme_title": "物理核心素养表现", "sub_theme": "科学思维发展水平",
            "section_type": "academic_requirement", "clause_number": "学业质量·科学思维",
            "pdf_page": 39 + pdf_offset, "print_page": 39,
            "raw_text": "在熟悉的情境中，会用所学模型分析常见的实际问题；在进行简单的物理实验和其他实践活动中，能对活动中的信息进行归纳推理，得到物理结论，在面对日常生活中的实际问题时，能运用所学物理概念、规律进行简单的演绎推理，得到结论；能依照证据形成自己的看法，具有利用证据进行论证的意识；在获取信息时，有判断信息的可靠性和合理性的意识，能从物理学视角对生活中不合理的说法进行质疑并说出理由，发表自己的见解。",
            "standardized_text": "熟练运用物理模型分析实际问题，具备归纳推理、演绎推理、证据论证与批判性质疑能力。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第39~40页（PDF第46~47页）学业质量描述第2段完全一致",
            "is_elective": False, "derived_requirement": "科学思维核心素养模型建构与推理论证终结性评价标准",
            "review_status": "pending", "legacy_mappings": ["physics.mech.balance", "physics.light.lens"]
        },
        {
            "clause_id": "cs:physics:2022:s4:experiment:acad_qual:scientific_inquiry:c97",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "experiment",
            "part_title": "五、学业质量", "domain_title": "学业质量标准",
            "theme_title": "物理核心素养表现", "sub_theme": "科学探究发展水平",
            "section_type": "academic_requirement", "clause_number": "学业质量·科学探究",
            "pdf_page": 40 + pdf_offset, "print_page": 40,
            "raw_text": "能针对一些现象，发现并提出要探究的物理问题，能根据经验和已有知识作出猜想与假设；能针对提出的问题，运用控制变量法等制订比较合理的科学探究方案，会正确使用学生必做实验所涉及的实验器材，并根据实验方案进行规范、安全的实验操作，会正确读取和记录实验数据，能排除简单的实验故障；能根据实验目的整理信息，会用简单的图像或表格描述信息，能通过信息比较或图像分析发现其中的特点，进行初步的因果判断，形成结论并作出解释，能表述物理问题，会用物理学术语、符号、图表等描述探究过程，说明探究结果，撰写简单的科学探究报告。",
            "standardized_text": "经历问题提出、猜想假设、方案制订、实验操作、数据处理、结论解释与报告撰写的全流程探究能力。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第40页（PDF第47页）学业质量描述第3段完全一致",
            "is_elective": False, "derived_requirement": "科学探究核心素养全流程实验操作与证据分析终结性评价标准",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        },
        {
            "clause_id": "cs:physics:2022:s4:comp_prac:acad_qual:attitude_responsibility:c98",
            "source_id": source_id, "subject": subject, "stage": stage, "domain": "comp_prac",
            "part_title": "五、学业质量", "domain_title": "学业质量标准",
            "theme_title": "物理核心素养表现", "sub_theme": "科学态度与责任发展水平",
            "section_type": "academic_requirement", "clause_number": "学业质量·态度责任",
            "pdf_page": 40 + pdf_offset, "print_page": 40,
            "raw_text": "能初步认识科学本质，体会物理学对人类认识深化及社会发展的推动作用；能保持对自然的好奇、对物理学的兴趣，具有严谨认真和实事求是的科学态度，既坚持原则，又能与他人合作；知道科学探索、技术应用及成果发表具有一定的道德规范，初步了解科学、技术、社会、环境之间的关系，具有保护环境、节约资源、促进可持续发展的责任感和实现中华民族伟大复兴的使命感。",
            "standardized_text": "认识科学本质与社会价值，具备严谨实事求是的求实精神、团队协作道德意识与生态环保责任感。",
            "collation_note": "经人工逐字核对，与教育部2022年版物理课标原件印刷第40页（PDF第47页）学业质量描述第4段完全一致",
            "is_elective": False, "derived_requirement": "科学态度与社会责任核心素养终结性评价总体标准",
            "review_status": "pending", "legacy_mappings": ["physics.exp.inquiry"]
        }
    ]

    def filter_clauses(predicate):
        return [c["clause_id"] for c in clauses if predicate(c)]

    # 2. 物理权威候选知识体系契约 (遵循课标真实架构，覆盖初中物理教学与中考诊断能力)
    candidates = [
        # 一级领域 1：物质与微观结构
        {
            "code": "physics_cand.matter",
            "name": "物质与微观结构",
            "domain": "matter", "parent_code": None, "level": 1,
            "description": "涵盖物态变化、物质物理属性、质量与密度、微观分子原子结构及宏观宇宙尺度的核心物质观念。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "matter"),
            "is_elective": False, "review_status": "pending", "review_note": "对应课标第一主题物质，待审核",
            "legacy_mapping_codes": ["physics.thermal", "physics.mechanics"]
        },
        {
            "code": "physics_cand.matter.thermal_state",
            "name": "物态变化与吸放热",
            "domain": "matter", "parent_code": "physics_cand.matter", "level": 2,
            "description": "固液气三态特征、液体温度计原理使用、晶体非晶体熔化凝固、汽化液化、升华凝华吸放热规律与水循环应用。",
            "source_clause_ids": [
                "cs:physics:2022:s4:matter:content_req:state_features:c01",
                "cs:physics:2022:s4:matter:content_req:thermometer:c02",
                "cs:physics:2022:s4:matter:content_req:phase_transition:c03",
                "cs:physics:2022:s4:matter:content_req:water_cycle:c04",
                "cs:physics:2022:s4:experiment:content_req:exp_temperature:c65",
                "cs:physics:2022:s4:experiment:content_req:inq_boiling:c72"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "细化六大物态变化与吸放热，待审核",
            "legacy_mapping_codes": ["physics.thermal.state"]
        },
        {
            "code": "physics_cand.matter.density_prop",
            "name": "质量与密度及物质物理属性",
            "domain": "matter", "parent_code": "physics_cand.matter", "level": 2,
            "description": "物质的弹性、磁性、导电导热等物理属性；质量概念与天平测量；密度概念公式 ρ=m/V、天平量筒测密度实验与误差分析。",
            "source_clause_ids": [
                "cs:physics:2022:s4:matter:content_req:prop_physical:c05",
                "cs:physics:2022:s4:matter:content_req:mass_measure:c06",
                "cs:physics:2022:s4:matter:content_req:density_understand:c07",
                "cs:physics:2022:s4:matter:content_req:prop_impact:c08",
                "cs:physics:2022:s4:experiment:content_req:exp_mass:c63",
                "cs:physics:2022:s4:experiment:content_req:exp_density:c64"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "质量测量与密度实验考点，待审核",
            "legacy_mapping_codes": ["physics.mech.density"]
        },
        {
            "code": "physics_cand.matter.micro_structure",
            "name": "微观世界与分子动理论及尺度",
            "domain": "matter", "parent_code": "physics_cand.matter", "level": 2,
            "description": "物质的微观构成（分子、原子、原子核式结构模型）、人类对微观世界和宏观宇宙探索历程与物质世界空间尺度观念。",
            "source_clause_ids": [
                "cs:physics:2022:s4:matter:content_req:molecule_atom:c09",
                "cs:physics:2022:s4:matter:content_req:nuclear_atom:c10",
                "cs:physics:2022:s4:matter:content_req:universe_explore:c11",
                "cs:physics:2022:s4:matter:content_req:scale_world:c12"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "微观粒子结构与宇宙尺度考点，待审核",
            "legacy_mapping_codes": ["physics.mech.density"]
        },

        # 一级领域 2：运动和相互作用
        {
            "code": "physics_cand.motion_interaction",
            "name": "运动和相互作用",
            "domain": "motion_energy", "parent_code": None, "level": 1,
            "description": "涵盖多种多样的运动形式、机械运动和力、声和光、电和磁的相互作用规律与物理模型。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "motion_energy" and c["part_title"] == "四、课程内容" and "（二）运动和相互作用" in c["domain_title"]),
            "is_elective": False, "review_status": "pending", "review_note": "对应课标第二主题运动和相互作用，待审核",
            "legacy_mapping_codes": ["physics.acoustics_optics", "physics.mechanics", "physics.electromagnetism"]
        },
        {
            "code": "physics_cand.motion.speed",
            "name": "机械运动与速度计算",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "机械运动与参照物相对性、长度与时间测量、刻度尺停表规范使用、速度定义式 v=s/t 计算及测小车平均速度实验。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:motion_relative:c14",
                "cs:physics:2022:s4:motion_energy:content_req:motion_forms:c16",
                "cs:physics:2022:s4:motion_energy:content_req:length_time:c17",
                "cs:physics:2022:s4:motion_energy:content_req:speed_calc:c18",
                "cs:physics:2022:s4:experiment:content_req:exp_length_time:c66",
                "cs:physics:2022:s4:experiment:content_req:exp_speed:c67"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "速度公式计算与运动测量，待审核",
            "legacy_mapping_codes": ["physics.mech.motion"]
        },
        {
            "code": "physics_cand.force.basics",
            "name": "力的概念与三要素及示意图",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "力的概念与作用效果（形变、改变运动状态）、力的三要素、力的受力分析示意图规范作图与相互作用力特点。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:force_diagram:c20"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "受力分析示意图作图技能，待审核",
            "legacy_mapping_codes": ["physics.mech.forces"]
        },
        {
            "code": "physics_cand.force.gravity_friction",
            "name": "重力、弹力与摩擦力",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "重力计算 G=mg、重心与竖直向下方向；弹簧测力计原理与测力；滑动摩擦力大小影响因素探究实验及增大减小摩擦方法。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:force_common:c19",
                "cs:physics:2022:s4:experiment:content_req:exp_force:c68",
                "cs:physics:2022:s4:experiment:content_req:inq_sliding_friction:c73"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "三种常见力综合分析，待审核",
            "legacy_mapping_codes": ["physics.mech.forces"]
        },
        {
            "code": "physics_cand.force.newton_balance",
            "name": "牛顿第一定律与二力平衡",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "牛顿第一定律理想实验科学推理；惯性是物体固有属性的辨析与安全解释；同一直线二力合成与二力平衡条件应用；在熟悉情境中运用科学模型与归纳演绎推理分析运动与力的关系。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:force_diagram:c20",
                "cs:physics:2022:s4:motion_energy:content_req:newton_inertia:c21",
                "cs:physics:2022:s4:motion_energy:acad_qual:scientific_thinking:c96"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "牛顿第一定律、二力平衡及科学思维模型推理论证核心素养，待审核",
            "legacy_mapping_codes": ["physics.mech.balance"]
        },
        {
            "code": "physics_cand.force.pressure_fluid",
            "name": "固体液体压强与大气压强流体压强",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "固体压强计算 p=F/S；探究液体内部压强特点与公式 p=ρgh；连通器原理；托里拆利实验测定大气压；流体压强与流速关系伯努利原理。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:solid_pressure:c23",
                "cs:physics:2022:s4:motion_energy:content_req:fluid_pressure:c24",
                "cs:physics:2022:s4:experiment:content_req:inq_liquid_pressure:c74"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "压强四大板块综合诊断，待审核",
            "legacy_mapping_codes": ["physics.mech.pressure"]
        },
        {
            "code": "physics_cand.force.buoyancy",
            "name": "浮力与阿基米德原理及浮沉条件",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "浮力产生原因（压力差）；阿基米德原理探究实验 F浮=G排=ρ液gV排；物体浮沉条件（漂浮、悬浮、沉底）及轮船潜水艇应用综合计算。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:buoyancy_archimedes:c25",
                "cs:physics:2022:s4:experiment:content_req:inq_buoyancy:c75"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "阿基米德原理与浮沉条件中考重难点，待审核",
            "legacy_mapping_codes": ["physics.mech.buoyancy"]
        },
        {
            "code": "physics_cand.force.simple_machine",
            "name": "简单机械（杠杆与滑轮）",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "杠杆五要素与力臂作图；探究杠杆平衡条件 F1L1=F2L2 与省力费力杠杆分类；定滑轮、动滑轮与滑轮组省力及绳端距离计算。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:simple_machine:c22",
                "cs:physics:2022:s4:experiment:content_req:inq_lever_balance:c76"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "简单机械作图与平衡计算，待审核",
            "legacy_mapping_codes": ["physics.mech.work"]
        },
        {
            "code": "physics_cand.sound",
            "name": "声现象与特性及噪声防治",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "声音由物体振动产生；介质传播与真空不能传声科学推理；空气声速；音调响度音色三要素辨析；超声次声应用与控制噪声途径。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:sound_produce:c26",
                "cs:physics:2022:s4:motion_energy:content_req:sound_features:c27"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "声现象全要素，待审核",
            "legacy_mapping_codes": ["physics.sound"]
        },
        {
            "code": "physics_cand.light.propagate_reflect",
            "name": "光的直线传播与反射平面镜成像",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "光在同种均匀介质中沿直线传播与小孔成像；真空光速；光的反射定律探究实验与作图；平面镜成像特点探究实验与对称作图。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:light_reflect_refract:c28",
                "cs:physics:2022:s4:motion_energy:content_req:plane_mirror:c29",
                "cs:physics:2022:s4:experiment:content_req:inq_light_reflection:c77",
                "cs:physics:2022:s4:experiment:content_req:inq_plane_mirror:c78"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "光沿直线传播与反射成像作图，待审核",
            "legacy_mapping_codes": ["physics.light.reflection_refraction"]
        },
        {
            "code": "physics_cand.light.refract_dispersion",
            "name": "光的折射与色散及不可见光",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "光的折射规律与光路作图、池水变浅筷子折断等折射现象解释；三棱镜白光色散、色光三原色与红外线紫外线应用。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:light_reflect_refract:c28",
                "cs:physics:2022:s4:motion_energy:content_req:light_dispersion:c31"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "光的折射作图与色散规律，待审核",
            "legacy_mapping_codes": ["physics.light.reflection_refraction"]
        },
        {
            "code": "physics_cand.light.lens_application",
            "name": "透镜成像规律与眼睛视力矫正",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "凸透镜会聚与凹透镜发散特殊光线；探究凸透镜成像规律实验；照相机、投影仪、放大镜光学原理及近视远视眼成因与矫正方法。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:lens_imaging:c30",
                "cs:physics:2022:s4:experiment:content_req:inq_lens_imaging:c79"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "透镜规律探究与光学仪器视力矫正应用，待审核",
            "legacy_mapping_codes": ["physics.light.lens"]
        },
        {
            "code": "physics_cand.elec.charge_field",
            "name": "静电现象与磁现象磁场",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "摩擦起电本质（电子转移）、两种电荷相互作用与验电器；磁体磁极、磁场与磁感线模型、地磁场特点及静电防范利用常识。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:static_electricity:c32",
                "cs:physics:2022:s4:motion_energy:content_req:magnetic_field:c33"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "电荷基本性质与磁场基本模型，待审核",
            "legacy_mapping_codes": ["physics.elec.circuit", "physics.elec.magnetism"]
        },
        {
            "code": "physics_cand.elec.electromagnetism",
            "name": "电与磁（电流磁效应与电磁感应）",
            "domain": "motion_energy", "parent_code": "physics_cand.motion_interaction", "level": 2,
            "description": "奥斯特实验电流磁效应；通电螺线管磁场与安培定则；电磁铁与电磁继电器；磁场对通电导线作用与电动机；法拉第电磁感应与发电机；电磁波传播与无线通信。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:current_magnetic:c34",
                "cs:physics:2022:s4:motion_energy:content_req:magnetic_force_wire:c35",
                "cs:physics:2022:s4:motion_energy:content_req:electromagnetic_induct:c36",
                "cs:physics:2022:s4:motion_energy:content_req:electromagnetic_wave:c37",
                "cs:physics:2022:s4:experiment:content_req:inq_solenoid_magnetic:c80",
                "cs:physics:2022:s4:experiment:content_req:inq_induction_current:c81"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "电动机发电机原理对比与电磁感应，待审核",
            "legacy_mapping_codes": ["physics.elec.magnetism"]
        },

        # 一级领域 3：能量与能源
        {
            "code": "physics_cand.energy",
            "name": "能量与能源",
            "domain": "motion_energy", "parent_code": None, "level": 1,
            "description": "涵盖机械能、内能、电磁能、能量守恒与能源可持续发展的核心能量观念与计算综合。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "motion_energy" and c["part_title"] == "四、课程内容" and "（三）能量" in c["domain_title"]),
            "is_elective": False, "review_status": "pending", "review_note": "对应课标第三主题能量，待审核",
            "legacy_mapping_codes": ["physics.thermal", "physics.mechanics", "physics.electromagnetism"]
        },
        {
            "code": "physics_cand.energy.transfer_concept",
            "name": "能量、能量转化转移与功的概念",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "认识不同能量形式及其与生产生活的联系；实验认识能量转移与相互转化；理解功的两个必要因素及做功是能量转化的量度。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:energy_forms:c39",
                "cs:physics:2022:s4:motion_energy:content_req:energy_transfer:c40",
                "cs:physics:2022:s4:motion_energy:content_req:work_concept:c41"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "能量基本观念与做功量度本质，待审核",
            "legacy_mapping_codes": ["physics.mech.work"]
        },
        {
            "code": "physics_cand.energy.work_power_eff",
            "name": "机械功、功率与机械效率",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "机械功公式 W=Fs；功率物理意义及计算 P=W/t=Fv；有用功、总功与机械效率 η=W有/W总；测滑轮组斜面机械效率实验与提高效率途径。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:work_power:c43",
                "cs:physics:2022:s4:motion_energy:content_req:mech_efficiency:c44",
                "cs:physics:2022:s4:motion_energy:content_req:machinery_history:c45"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "机械功功率与效率综合计算，待审核",
            "legacy_mapping_codes": ["physics.mech.work"]
        },
        {
            "code": "physics_cand.energy.mech_energy_conserv",
            "name": "动能、势能与机械能转化守恒",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "动能势能影响因素探究；动能与势能相互转化过程分析；机械能守恒条件及能量转化转移具有方向性与能量守恒定律。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:mech_energy:c42",
                "cs:physics:2022:s4:motion_energy:content_req:energy_conservation:c56",
                "cs:physics:2022:s4:motion_energy:content_req:energy_efficiency:c57",
                "cs:physics:2022:s4:motion_energy:content_req:energy_direction:c58"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "机械能守恒与能量转化方向性，待审核",
            "legacy_mapping_codes": ["physics.mech.work"]
        },
        {
            "code": "physics_cand.energy.internal_heat",
            "name": "内能、比热容与热量计算",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "内能概念与改变内能两种方式（做功和热传递）；分子动理论；比热容探究实验；热量计算公式 Q=cmΔt 及水比热容大在生活中的应用。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:kinetic_theory:c15",
                "cs:physics:2022:s4:motion_energy:content_req:internal_heat:c46",
                "cs:physics:2022:s4:motion_energy:content_req:specific_heat:c47"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "内能比热容与热量综合计算，待审核",
            "legacy_mapping_codes": ["physics.thermal.heat"]
        },
        {
            "code": "physics_cand.energy.heat_engine",
            "name": "燃料热值与热机四冲程及效率",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "燃料热值公式 Q=mq 或 Q=Vq；四冲程内燃机（吸气、压缩、做功、排气）工作循环与能量转化；热机效率概念与提高效率途径。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:internal_heat:c46",
                "cs:physics:2022:s4:motion_energy:content_req:heat_engine:c48"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "内燃机冲程能量转化与热机效率，待审核",
            "legacy_mapping_codes": ["physics.thermal.heat"]
        },
        {
            "code": "physics_cand.energy.circuit_rules",
            "name": "电路规律（电流、电压、电阻与滑动变阻器）",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "电源用电器能量转化；电路图绘制与串并联实物连接；串联并联电路电流与电压规律；电阻影响因素与滑动变阻器规范使用接法。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:power_supply:c49",
                "cs:physics:2022:s4:motion_energy:content_req:meters_use:c51",
                "cs:physics:2022:s4:motion_energy:content_req:circuit_rules:c52",
                "cs:physics:2022:s4:experiment:content_req:exp_current:c69",
                "cs:physics:2022:s4:experiment:content_req:exp_voltage:c70",
                "cs:physics:2022:s4:experiment:content_req:inq_circuit_features:c82"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "电路基础连接与电表电学规律，待审核",
            "legacy_mapping_codes": ["physics.elec.circuit"]
        },
        {
            "code": "physics_cand.energy.ohm_law",
            "name": "欧姆定律及其电路综合应用",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "探究电流与电压电阻关系实验；欧姆定律公式 I=U/R；伏安法测定定值电阻与小灯泡电阻实验；动态电路分析与极值范围综合计算。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:ohm_law:c50",
                "cs:physics:2022:s4:experiment:content_req:exp_resistance:c71",
                "cs:physics:2022:s4:experiment:content_req:inq_ohm_relation:c83"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "欧姆定律动态电路中考核心考点，待审核",
            "legacy_mapping_codes": ["physics.elec.ohm"]
        },
        {
            "code": "physics_cand.energy.electric_power_joule",
            "name": "电功、电功率与焦耳定律",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "电能表参数读数与电功计算 W=UIt=Pt；电功率公式 P=UI 及推导式；额定与实际功率分析；焦耳定律探究实验与 Q=I²Rt 计算及电热利用防止。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:electric_power:c53",
                "cs:physics:2022:s4:motion_energy:content_req:joule_law:c54"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "电功率与焦耳定律综合电学大题，待审核",
            "legacy_mapping_codes": ["physics.elec.power"]
        },
        {
            "code": "physics_cand.energy.safety_and_conservation",
            "name": "家庭电路安全用电与能量守恒能源发展",
            "domain": "motion_energy", "parent_code": "physics_cand.energy", "level": 2,
            "description": "家庭电路组成与三孔插座接地；试电笔使用与触电防护安全用电原则；可再生与不可再生能源分类；核能特点与太阳能利用及可持续发展观念。",
            "source_clause_ids": [
                "cs:physics:2022:s4:motion_energy:content_req:household_safety:c55",
                "cs:physics:2022:s4:motion_energy:content_req:energy_resources:c59",
                "cs:physics:2022:s4:motion_energy:content_req:nuclear_energy:c60",
                "cs:physics:2022:s4:motion_energy:content_req:solar_sustainable:c61"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "家庭安全用电与能源可持续发展，待审核",
            "legacy_mapping_codes": ["physics.elec.power", "physics.thermal.heat"]
        },

        # 一级领域 4：实验探究
        {
            "code": "physics_cand.experiment",
            "name": "物理实验与科学探究能力",
            "domain": "experiment", "parent_code": None, "level": 1,
            "description": "涵盖21个必做实验、测量仪器规范操作、数据记录处理、误差分析及控制变量转换法科学探究能力。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "experiment"),
            "is_elective": False, "review_status": "pending", "review_note": "对应课标第四主题实验探究，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        },
        {
            "code": "physics_cand.exp.measuring_skills",
            "name": "基本测量仪器规范使用与数据处理",
            "domain": "experiment", "parent_code": "physics_cand.experiment", "level": 2,
            "description": "掌握托盘天平、量筒、刻度尺、秒表、温度计、弹簧测力计、电流表、电压表等基础测量仪器规范使用、调零、量程选取与数据记录误差估算。",
            "source_clause_ids": [
                "cs:physics:2022:s4:experiment:content_req:exp_mass:c63",
                "cs:physics:2022:s4:experiment:content_req:exp_density:c64",
                "cs:physics:2022:s4:experiment:content_req:exp_temperature:c65",
                "cs:physics:2022:s4:experiment:content_req:exp_length_time:c66",
                "cs:physics:2022:s4:experiment:content_req:exp_speed:c67",
                "cs:physics:2022:s4:experiment:content_req:exp_force:c68",
                "cs:physics:2022:s4:experiment:content_req:exp_current:c69",
                "cs:physics:2022:s4:experiment:content_req:exp_voltage:c70",
                "cs:physics:2022:s4:experiment:content_req:exp_resistance:c71"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "9类测量型必做实验综合考查，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        },
        {
            "code": "physics_cand.exp.inquiry_methods",
            "name": "科学探究方法（控制变量法、转换法与图像处理）",
            "domain": "experiment", "parent_code": "physics_cand.experiment", "level": 2,
            "description": "掌握控制变量法、转换法、等效替代法、科学推理法等物理研究方法；具备实验故障诊断、数据表格图像分析与探究结论科学表述能力。",
            "source_clause_ids": [
                "cs:physics:2022:s4:experiment:content_req:inq_boiling:c72",
                "cs:physics:2022:s4:experiment:content_req:inq_sliding_friction:c73",
                "cs:physics:2022:s4:experiment:content_req:inq_liquid_pressure:c74",
                "cs:physics:2022:s4:experiment:content_req:inq_buoyancy:c75",
                "cs:physics:2022:s4:experiment:content_req:inq_lever_balance:c76",
                "cs:physics:2022:s4:experiment:content_req:inq_light_reflection:c77",
                "cs:physics:2022:s4:experiment:content_req:inq_plane_mirror:c78",
                "cs:physics:2022:s4:experiment:content_req:inq_lens_imaging:c79",
                "cs:physics:2022:s4:experiment:content_req:inq_solenoid_magnetic:c80",
                "cs:physics:2022:s4:experiment:content_req:inq_induction_current:c81",
                "cs:physics:2022:s4:experiment:content_req:inq_circuit_features:c82",
                "cs:physics:2022:s4:experiment:content_req:inq_ohm_relation:c83"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "12类探究型必做实验方法归纳，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        },

        # 一级领域 5：跨学科实践
        {
            "code": "physics_cand.interdisciplinary",
            "name": "跨学科实践与现代工程技术",
            "domain": "comp_prac", "parent_code": None, "level": 1,
            "description": "物理与日常生活实践作品制作、物理与重大工程科技成就（航天、深潜、高铁）的跨学科综合应用分析及社会责任观念。",
            "source_clause_ids": filter_clauses(lambda c: c["domain"] == "comp_prac"),
            "is_elective": False, "review_status": "pending", "review_note": "对应课标第五主题跨学科实践，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        },
        {
            "code": "physics_cand.interdisciplinary.life_engineer",
            "name": "物理与日常生活及工程技术实践",
            "domain": "comp_prac", "parent_code": "physics_cand.interdisciplinary", "level": 2,
            "description": "发现日常生活物理问题改良生活用品、分析用电交通安全隐患、了解我国古代龙骨水车赵州桥及现代桥梁高铁信息技术工程案例。",
            "source_clause_ids": [
                "cs:physics:2022:s4:comp_prac:content_req:daily_problem:c85",
                "cs:physics:2022:s4:comp_prac:content_req:daily_safety:c86",
                "cs:physics:2022:s4:comp_prac:content_req:daily_low_carbon:c87",
                "cs:physics:2022:s4:comp_prac:content_req:eng_ancient:c88",
                "cs:physics:2022:s4:comp_prac:content_req:eng_modern:c89",
                "cs:physics:2022:s4:comp_prac:content_req:eng_info:c90"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "日常生活与工程技术跨学科实践，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        },
        {
            "code": "physics_cand.interdisciplinary.society_development",
            "name": "物理与社会发展及新材料科技成就",
            "domain": "comp_prac", "parent_code": "physics_cand.interdisciplinary", "level": 2,
            "description": "能源开发对社会发展影响、前沿新材料（半导体超导体纳米材料）科技变革、两弹一星与国家重大科技突破及爱国奉献科学家精神。",
            "source_clause_ids": [
                "cs:physics:2022:s4:comp_prac:content_req:soc_energy:c91",
                "cs:physics:2022:s4:comp_prac:content_req:soc_materials:c92",
                "cs:physics:2022:s4:comp_prac:content_req:soc_achievements:c93"
            ],
            "is_elective": False, "review_status": "pending", "review_note": "社会发展新材料与重大科技成就跨学科，待审核",
            "legacy_mapping_codes": ["physics.exp.inquiry"]
        }
    ]

    # 3. 存量 21 个物理旧节点映射契约 (严格映射至新候选体系，详细演进理由与历史兼容保障)
    legacy_mappings = [
        {
            "legacy_code": "physics.acoustics_optics",
            "legacy_name": "声学与光学",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["physics_cand.motion_interaction"],
            "mapping_reason": "原一级旧领域对应新课标运动和相互作用领域中声和光主题，保留大类映射。",
            "compatibility_assurance": "旧领域节点保留，历史试卷领域级引用不变。"
        },
        {
            "legacy_code": "physics.sound",
            "legacy_name": "声现象",
            "legacy_parent_code": "physics.acoustics_optics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.sound"],
            "mapping_reason": "考查声音产生、传播与特性，与新体系物理声现象完全对应。",
            "compatibility_assurance": "原有试题关联保持只读有效。"
        },
        {
            "legacy_code": "physics.light.reflection_refraction",
            "legacy_name": "光的直线传播、反射与折射",
            "legacy_parent_code": "physics.acoustics_optics",
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.light.propagate_reflect",
                "physics_cand.light.refract_dispersion"
            ],
            "mapping_reason": "原旧节点将反射与折射合并，新体系根据课标将光的直线传播反射与折射色散拆分为清晰考点以精准诊断光路作图与介质折射规律。",
            "compatibility_assurance": "历史题目对原旧节点的引用保持只读可用，新题目细分标记。"
        },
        {
            "legacy_code": "physics.light.lens",
            "legacy_name": "透镜及其成像规律",
            "legacy_parent_code": "physics.acoustics_optics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.light.lens_application"],
            "mapping_reason": "考查凸透镜成像规律及眼睛视力矫正应用，内涵完全一致。",
            "compatibility_assurance": "历史作答与诊断记录保持只读兼容。"
        },
        {
            "legacy_code": "physics.thermal",
            "legacy_name": "热学",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["physics_cand.matter", "physics_cand.energy"],
            "mapping_reason": "原旧热学跨越课标的物质（物态变化）与能量（内能比热容），新体系予以双向映射对应。",
            "compatibility_assurance": "旧领域节点保留，历史试卷引用不变。"
        },
        {
            "legacy_code": "physics.thermal.state",
            "legacy_name": "物态变化",
            "legacy_parent_code": "physics.thermal",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.matter.thermal_state"],
            "mapping_reason": "六大物态变化吸放热过程与新课标1.1完全对应。",
            "compatibility_assurance": "历史作答记录不变。"
        },
        {
            "legacy_code": "physics.thermal.heat",
            "legacy_name": "内能、比热容与热机",
            "legacy_parent_code": "physics.thermal",
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.energy.internal_heat",
                "physics_cand.energy.heat_engine"
            ],
            "mapping_reason": "原旧节点将内能比热容与热机混合，新体系将热机工作冲程效率独立划分，有利于中考热学专项诊断。",
            "compatibility_assurance": "历史试题引用不变。"
        },
        {
            "legacy_code": "physics.mechanics",
            "legacy_name": "力学",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["physics_cand.motion_interaction", "physics_cand.energy"],
            "mapping_reason": "原力学大类对应运动和相互作用力学部分与能量机械能部分。",
            "compatibility_assurance": "历史领域级引用不变。"
        },
        {
            "legacy_code": "physics.mech.motion",
            "legacy_name": "机械运动与参照物",
            "legacy_parent_code": "physics.mechanics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.motion.speed"],
            "mapping_reason": "参照物与速度计算，考查要点完全契合。",
            "compatibility_assurance": "历史数据保持只读兼容。"
        },
        {
            "legacy_code": "physics.mech.forces",
            "legacy_name": "常见力与重力摩擦力",
            "legacy_parent_code": "physics.mechanics",
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.force.basics",
                "physics_cand.force.gravity_friction"
            ],
            "mapping_reason": "新体系将力的基本概念三要素与重力弹力摩擦力分立，使受力分析作图技能独立考查。",
            "compatibility_assurance": "历史数据保持完整只读兼容。"
        },
        {
            "legacy_code": "physics.mech.balance",
            "legacy_name": "牛顿第一定律、惯性与二力平衡",
            "legacy_parent_code": "physics.mechanics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.force.newton_balance"],
            "mapping_reason": "牛顿第一定律与二力平衡条件，内容与考法完全契合。",
            "compatibility_assurance": "历史数据保持只读兼容。"
        },
        {
            "legacy_code": "physics.mech.density",
            "legacy_name": "质量与密度测量",
            "legacy_parent_code": "physics.mechanics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.matter.density_prop"],
            "mapping_reason": "课标将质量密度归入物质属性，新体系建立对应映射，教学内涵一致。",
            "compatibility_assurance": "历史题目对旧节点的引用保持只读有效。"
        },
        {
            "legacy_code": "physics.mech.pressure",
            "legacy_name": "固体与液体压强、大气压强",
            "legacy_parent_code": "physics.mechanics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.force.pressure_fluid"],
            "mapping_reason": "涵盖固体液体压强与大气压强流体压强，考查目标一致。",
            "compatibility_assurance": "历史作答保持不变。"
        },
        {
            "legacy_code": "physics.mech.buoyancy",
            "legacy_name": "浮力与阿基米德原理",
            "legacy_parent_code": "physics.mechanics",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.force.buoyancy"],
            "mapping_reason": "阿基米德原理与浮沉条件，考查要点完全契合。",
            "compatibility_assurance": "历史答题记录保持不变。"
        },
        {
            "legacy_code": "physics.mech.work",
            "legacy_name": "功、功率与机械效率",
            "legacy_parent_code": "physics.mechanics",
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.force.simple_machine",
                "physics_cand.energy.transfer_concept",
                "physics_cand.energy.work_power_eff",
                "physics_cand.energy.mech_energy_conserv"
            ],
            "mapping_reason": "原旧节点将简单机械、机械功功率及动能势能混杂，新体系精细化区分简单机械、机械功效率与机械能转化，利于初三精准诊断。",
            "compatibility_assurance": "历史引用保持只读可用。"
        },
        {
            "legacy_code": "physics.electromagnetism",
            "legacy_name": "电学与磁学",
            "legacy_parent_code": None,
            "action": "retained",
            "target_candidate_codes": ["physics_cand.motion_interaction", "physics_cand.energy"],
            "mapping_reason": "原电磁大类对应电磁相互作用与电磁能两个一级主题。",
            "compatibility_assurance": "旧领域节点保留。"
        },
        {
            "legacy_code": "physics.elec.circuit",
            "legacy_name": "电路基础与电流电压",
            "legacy_parent_code": "physics.electromagnetism",
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.elec.charge_field",
                "physics_cand.energy.circuit_rules",
                "physics_cand.energy.safety_and_conservation"
            ],
            "mapping_reason": "新体系将静电电荷、电路串并联规律与家庭安全用电分别确立考点，区分清晰。",
            "compatibility_assurance": "历史数据保持只读兼容。"
        },
        {
            "legacy_code": "physics.elec.ohm",
            "legacy_name": "电阻、滑动变阻器与欧姆定律",
            "legacy_parent_code": "physics.electromagnetism",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.energy.ohm_law"],
            "mapping_reason": "欧姆定律及其串并联应用为中考核心诊断模块，映射至新体系欧姆定律考点。",
            "compatibility_assurance": "历史数据保持只读兼容。"
        },
        {
            "legacy_code": "physics.elec.power",
            "legacy_name": "电功、电功率与焦耳定律",
            "legacy_parent_code": "physics.electromagnetism",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.energy.electric_power_joule"],
            "mapping_reason": "电功率额定功率与焦耳定律计算综合性强，映射至对应电功电功率考点。",
            "compatibility_assurance": "原有试题关联保持有效。"
        },
        {
            "legacy_code": "physics.elec.magnetism",
            "legacy_name": "电与磁、电磁感应",
            "legacy_parent_code": "physics.electromagnetism",
            "action": "retained",
            "target_candidate_codes": ["physics_cand.elec.electromagnetism"],
            "mapping_reason": "安培定则、电动机与发电机原理考查重点与新体系完全对应。",
            "compatibility_assurance": "历史答题记录保持不变。"
        },
        {
            "legacy_code": "physics.exp.inquiry",
            "legacy_name": "物理实验与科学探究方法",
            "legacy_parent_code": None,
            "action": "split",
            "target_candidate_codes": [
                "physics_cand.experiment",
                "physics_cand.exp.measuring_skills",
                "physics_cand.exp.inquiry_methods",
                "physics_cand.interdisciplinary"
            ],
            "mapping_reason": "原旧节点为实验笼统兜底项，新体系将其系统拆解为基本测量技能、科学探究方法与跨学科实践三大维度，全面覆盖21个必做实验。",
            "compatibility_assurance": "历史实验题目关联保持只读兼容。"
        }
    ]

    return {
        "clauses": clauses,
        "candidates": candidates,
        "legacy_mappings": legacy_mappings
    }
