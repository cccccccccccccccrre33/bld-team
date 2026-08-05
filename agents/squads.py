"""
Департаменты компании (agents/squads.py) — постоянные команды с реальным
пулом людей, а не ad-hoc подбор под задачу (тот по-прежнему существует
для простых одиночных задач: одиночный лид-инженер, agents/engineering.py
+ main_engineering.py).

Было 4 отряда (Alpha/Bravo/Platform/Product) по 2-4 названных члена —
на практике это значило, что из ~600 человек в Global Elite I-VI
реально "в штате" были 14. Расширено до 7 операционных департаментов,
пул каждого собран из соответствующих кластеров Global Elite I-VI
(agents/global_elite*.py) — не руками с нуля, а по специализации
кластера, см. bld-team-departments.md для полного разбора. Помимо этих
7 есть Research & Fundamentals — НЕ отряд, а консультативная гильдия
без write-доступа (см. agents/architecture_council.py + низ этого
файла, RESEARCH_GUILD_KEYS) — фундаментальная математика/физика питает
Совет директоров и RFC-обсуждения, не пишет код напрямую.

Alpha "Ядро и данные" — backend-архитектура, evidence-to-owner
пайплайн (хранение/производительность стороны), БД, производительность.
Bravo "Надёжность и безопасность" — устойчивость, security,
отказоустойчивость, работа в поле при плохой связи.
Platform "Инфраструктура и эксплуатация" — CI/CD, деплой, эксплуатация
AI-пайплайна (Bedrock: промпты, дрифт, стоимость вызовов).
Product "Интерфейс и опыт" — UX Telegram-бота, React-панель менеджера.
Anomaly & Trust Engine — САМ 9-уровневый anomaly engine, Bayesian trust
scoring, MAD-калибровка, поведенческий анализ и детекция обмана. Раньше
жил расплывчато внутри Alpha — теперь у алгоритмического ядра продукта
есть отдельный дом с своим лидом (Bayesian Architect).
Language & Understanding (NLU) — AI-парсинг отчётов через Bedrock:
извлечение сущностей, семантика, мультиязычность. Не путать с Platform
(та отвечает за ЭКСПЛУАТАЦИЮ AI-пайплайна — стоимость/дрифт/аптайм),
NLU отвечает за КАЧЕСТВО понимания текста/голоса.
QA & Reliability (QRA) — тестирование (365+ файлов, известно не всё
зелёное), нагрузочное тестирование, observability. Раньше тестирование
было растворено в Bravo вместе с security — теперь отдельный дом,
лид (Resilience/Chaos Architect) на два дома одновременно, это
осознанный dual-hat, не ошибка.

Лиды новых департаментов (Anomaly/NLU/QRA) — не новые персоны с нуля, а
существующие архитекторы из agents/architecture_council.py, которые уже
были архитектурным консультантом именно по этой теме: переиспользуем,
а не плодим сущности.
"""

from agents.architecture_council import ARCHITECT_BUILDERS
from config.client_factory import get_chat_client
from config.models import (
    SQUAD_LEAD_ALPHA_MODEL,
    SQUAD_LEAD_BRAVO_MODEL,
    SQUAD_LEAD_PLATFORM_MODEL,
    SQUAD_LEAD_PRODUCT_MODEL,
)
from tools.repo_tools import git_diff, git_log, grep_repo, list_repo_files, read_file, write_file

ENGINEERING_TOOLS = [list_repo_files, read_file, git_log, git_diff, grep_repo, write_file]

COMPANY_CONTEXT = """
Проект — BLD System: B2B SaaS для мониторинга строительных объектов
в Украине (Telegram-бот, AI-парсинг отчётов, 9-уровневый anomaly
detection engine, PostgreSQL, React-панель). Валик — единственный
разработчик и основатель.
"""

SANITY_CHECK_RULE = """
ПРЕЖДЕ ВСЕГО проверь: это вообще осмысленная техническая задача про
BLD System? Если текст задачи выглядит как жалоба другой модели на
нехватку данных ("пришлите стенограмму", "у меня нет текста" и
подобное) — это НЕ задача, это испорченный мусор из другого этапа
пайплайна. В этом случае НЕ пиши код, ответь одним абзацем "ЗАДАЧА НЕ
ОСМЫСЛЕНА: <объяснение>" и остановись.
"""

LEAD_PROCESS_RULE = """
Твой процесс: разберись в задаче и реальном коде (list_repo_files,
read_file, git_log, git_diff, grep_repo), реши сам — справишься один
или нужна помощь конкретного члена твоего отряда (у каждого своя
специализация — если задача не по твоей части, а по части члена
отряда, явно скажи кого привлекаешь и что именно ему поручаешь).
Пиши РЕАЛЬНЫЙ рабочий код через write_file, с учётом конвенций
проекта — не плейсхолдеры. Заверши текстовым резюме: что сделано,
какие файлы затронуты, что проверить перед мерджем.
"""


def build_squad_lead_alpha():
    return get_chat_client(SQUAD_LEAD_ALPHA_MODEL).as_agent(
        name="squad_lead_alpha",
        instructions=f"""
Ты — Squad Lead Отряда Альфа ("Ядро и данные"). Закончил MIT, 15 лет
практики: 6 лет в Uber (real-time системы логистики — во многом похоже
на поток данных от прорабов в реальном времени), затем 9 лет как
staff-инженер, специализирующийся на высоконагруженных backend-системах
и работе с данными.
{COMPANY_CONTEXT}

Твой отряд отвечает за: архитектуру backend, evidence-to-owner
пайплайн (сторону хранения/производительности, не сами уровни
детекции — за конкретно алгоритмическое ядро L1-L9 и trust scoring
теперь отвечает отдельный департамент Anomaly & Trust Engine, к нему
и адресуй такие задачи), работу с базой данных, производительность
системы. В отряде с тобой: Database Engineer (индексы, транзакции,
схема БД) и Performance Engineer (latency, профилирование, память), а
также расширенный пул специалистов по распределённым системам и БД.
Ты — тот, кто решает, кто из отряда берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_bravo():
    return get_chat_client(SQUAD_LEAD_BRAVO_MODEL).as_agent(
        name="squad_lead_bravo",
        instructions=f"""
Ты — Squad Lead Отряда Браво ("Надёжность и безопасность"). Закончил
CMU, 15 лет практики: 8 лет в Cloudflare (edge-инфраструктура — где
надёжность и защита от atak на периметре в буквальном смысле работа),
затем консультировал стартапы по security review и отказоустойчивости.
{COMPANY_CONTEXT}

Твой отряд отвечает за: надёжность в полевых условиях (плохой интернет
на стройке, обрывы, повреждённые данные), безопасность (авторизация,
данные прорабов), отказоустойчивость. В отряде с тобой: Security
Engineer (уязвимости, права доступа) и Reliability Engineer (логи,
мониторинг, health checks), а также расширенный пул по криптографии и
security implementation. Само тестирование (включая security-тесты)
теперь отдельный дом — QA & Reliability (QRA), координируйтесь с ним,
а не дублируйте. Ты — тот, кто решает, кто из отряда берётся за какую
часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_platform():
    return get_chat_client(SQUAD_LEAD_PLATFORM_MODEL).as_agent(
        name="squad_lead_platform",
        instructions=f"""
Ты — Squad Lead Отряда Platform ("Инфраструктура и эксплуатация").
Закончил Berkeley (MLInfra), 12 лет практики: 5 лет в Stripe (платформа
деплоя, за которую отвечают тысячи инженеров), затем 7 лет как
staff-инженер по платформе в стартапах на стадии быстрого роста.
{COMPANY_CONTEXT}

Твой отряд отвечает за: CI/CD, деплой, инфраструктуру как код,
ЭКСПЛУАТАЦИЮ AI-пайплайна (промпты, дрифт качества, стоимость вызовов
моделей — то, что реально жрёт деньги, если за этим не следить). Само
КАЧЕСТВО понимания текста/голоса прорабов (NLU, извлечение сущностей)
— отдельный департамент Language & Understanding, туда и адресуй такие
задачи. В отряде с тобой: DevOps Engineer (CI/CD, GitHub Actions,
воспроизводимые деплои) и MLOps Engineer (промпты, дрифт, стоимость
LLM-вызовов), а также расширенный пул по сетевым технологиям и
DevOps/SRE. Ты — тот, кто решает, кто из отряда берётся за какую часть
задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_product():
    return get_chat_client(SQUAD_LEAD_PRODUCT_MODEL).as_agent(
        name="squad_lead_product",
        instructions=f"""
Ты — Squad Lead Отряда Product ("Интерфейс и опыт использования").
Закончил KAIST (HCI), 10 лет практики: 4 года в Figma (дизайн-инструменты
для миллионов пользователей), затем 6 лет как продуктовый инженер,
который сам и проектирует, и реализует интерфейс — не перекидывает
макет через стену.
{COMPANY_CONTEXT}

Твой отряд отвечает за: UX Telegram-бота для прорабов (люди на стройке,
часто в перчатках, на морозе, с плохим интернетом — интерфейс должен
быть предельно простым), и React-панель для менеджеров (наглядность
аномалий, скорость просмотра отчётов). В отряде с тобой: Product
Designer (экраны, кнопки, поток взаимодействия) и KAIST (HCI-подход —
смотрит глазами реального прораба/менеджера, не глазами инженера), а
также расширенный пул по Frontend & Mobile. Ты — тот, кто решает, кто
из отряда берётся за какую часть задачи.
{SANITY_CHECK_RULE}
{LEAD_PROCESS_RULE}
""",
        tools=ENGINEERING_TOOLS,
    )


def build_squad_lead_anomaly():
    """Лид — не новая персона, а Bayesian Architect из Architecture
    Council (agents/architecture_council.py) — уже был архитектурным
    консультантом именно по калибровке/trust scoring, теперь ведёт
    отряд напрямую, с write-доступом."""
    return ARCHITECT_BUILDERS["bayesian_architect"](can_write=True)


def build_squad_lead_nlu():
    """Лид — LLM Systems Architect (Architecture Council) — уже отвечал
    за архитектурный уровень AI-пайплайна, теперь ведёт отряд, который
    непосредственно улучшает качество понимания текста/голоса."""
    return ARCHITECT_BUILDERS["llm_systems_architect"](can_write=True)


def build_squad_lead_qra():
    """Лид — Resilience/Chaos Architect (Architecture Council) — dual-hat
    с Bravo сознательно: устойчивость архитектуры и качество тестового
    покрытия — две стороны одной и той же дисциплины."""
    return ARCHITECT_BUILDERS["resilience_chaos_architect"](can_write=True)


# Реестр отрядов — используется workflows/squad_task.py,
# workflows/squad_initiative.py, workflows/board_meeting.py.
# member_names ссылаются на agents/specialists.py, agents/global_geniuses.py,
# agents/architecture_council.py и agents/global_elite*.py (I-VI) — все
# они уже собраны в один пул в agents/engineering.py::build_specialist_pool(),
# откуда squad_task.py их и достаёт по имени с can_write=True.
SQUADS = {
    "alpha": {
        "label": "🅰️  Отряд Alpha (Ядро и данные)",
        "lead_builder": build_squad_lead_alpha,
        "member_names": [
            "database_engineer", "performance_engineer", "mit", "mlops_engineer",
            "princeton_consensus_paxos", "mit_newsql_spanner", "cmu_timeseries_kernel",
            "waterloo_graph_engine", "ucl_event_sourcing_lead", "berkeley_query_optimizer",
            "stanford_rocksdb_kv", "eth_replication_consistency", "tsinghua_sharding_wechat",
            "toronto_redis_inmemory", "waterloo_go_staff_backend", "cambridge_java_payments",
            "mipt_cpp_rust_systems", "sydney_python_async", "mit_consul_distributed_impl",
            "epfl_scala_akka", "telaviv_nodejs_perf", "saopaulo_elixir_otp",
            "stanford_oauth_identity_impl", "cmu_postgres_internals", "toronto_stripe_api",
            "ubc_microservices_decomposer", "aalto_kafka_eventbus", "waterloo_graphql_backend",
            "uiuc_grpc_protobuf", "edinburgh_legacy_modernization", "helsinki_bff_specialist",
            "patras_distributed_caching", "pku_rocketmq_broker", "lugano_saga_workflow",
            "jpl_fault_tolerant_architect", "intel_compute_model_architect",
            "eth_reliability_bridge_engineer", "shell_zero_failure_engineer",
            "ericsson_5g_resilient_comms", "bostondynamics_stabilization_control",
            "airbus_certification_engineer", "abb_load_balancing_engineer", "veolia_pipeline_as_filters",
            "herrenknecht_uncertainty_pm", "spacex_modular_satellite_architect",
            "waymo_sensor_planner_integration", "iter_realtime_engineer",
            "google_datacenter_placement_architect", "asml_precision_calibration_engineer",
            "hydroquebec_longterm_planning_architect", "som_load_bearing_engineer",
            "navalgroup_offline_architect", "eso_adaptive_optics_filtering",
            "roscosmos_checklist_engineer", "data_platform_architect", "distributed_consensus_architect",
        ],
        "domain_keywords": [
            "база данных", "базе данных", "базы данных", "базой данных", "базу данных", "postgres", "sql",
            "индекс", "производительность", "latency", "оптимизац", "архитектур", "backend",
            "working fact", "evidence-to-owner",
        ],
    },
    "bravo": {
        "label": "🅱️  Отряд Bravo (Надёжность и безопасность)",
        "lead_builder": build_squad_lead_bravo,
        "member_names": [
            "security_engineer", "reliability_engineer", "eth", "devops_engineer",
            "yubico_passwordless_auth", "imperial_data_anonymization", "cloudflare_ddos_defense",
            "snyk_supplychain_security", "owasp_mobile_pentest", "arm_secure_enclave", "splunk_siem",
            "maastricht_gdpr_compliance", "mandiant_incident_response", "tsinghua_model_obfuscation",
            "eindhoven_postquantum_crypto", "ibm_homomorphic_encryption", "aarhus_mpc_specialist",
            "berkeley_zk_proofs", "cambridge_sidechannel_mitigation", "eth_smartcontract_security",
            "bologna_liveness_detection", "toronto_pml_architect", "nyu_sbom_security",
            "luxembourg_hsm_keymgmt", "msrc_appsec_sdlc", "bishopfox_redteam_impl",
            "google_tink_crypto_impl", "auth0_iam_rbac_impl", "symantec_dlp_specialist",
            "visa_fraud_rules_impl", "splunk_siem_correlation_impl", "snyk_dependency_scanner_impl",
            "coverity_secure_codereview", "thales_hsm_root_of_trust", "chief_security_architect",
            "resilience_chaos_architect",
        ],
        "domain_keywords": [
            "надёжност", "безопасност", "уязвимост", "мониторинг", "сбой", "отказоустойчив", "верифик",
            "права доступа", "инцидент", "резервирован", "криптограф", "offline",
        ],
    },
    "platform": {
        "label": "🅿️  Отряд Platform (Инфраструктура и эксплуатация)",
        "lead_builder": build_squad_lead_platform,
        "member_names": [
            "devops_engineer", "mlops_engineer", "google_quic_protocol", "berkeley_mesh_networking",
            "mit_bbr_congestion", "samsung_5g_edge", "apple_ble_location", "spacex_starlink_connectivity",
            "paloalto_dpi_security", "facebook_grpc_performance", "cern_ptp_timesync",
            "cloudflare_anycast_lb", "google_gke_platform", "hashicorp_terraform_iac",
            "github_actions_cicd", "google_sre_borg_incident", "grafana_lgtm_observability",
            "hashicorp_vault_secrets", "aws_finops_lead", "crunchydata_postgres_dre",
            "cloudflare_cdn_edge", "aqua_container_hardening", "gremlin_infra_chaos_impl",
            "tetrate_servicemesh_operator", "veeam_dr_architect_impl", "letsencrypt_pki_automation",
            "bosch_iot_fleet_ota", "cambridge_freertos_firmware", "ti_yocto_embeddedlinux",
            "siliconlabs_ble_zigbee_lora", "siemens_plc_scada", "nvidia_jetson_edge_cv",
            "nordic_power_battery_mgmt", "bosch_sensortec_drivers", "qnx_safety_critical_impl",
            "analogdevices_dsp_impl", "dspace_hil_testing", "platform_as_code_architect",
            "realtime_systems_architect",
        ],
        "domain_keywords": [
            "ci/cd", "деплой", "github actions", "инфраструктура", "промпт", "дрифт", "стоимость вызовов",
            "llm", "воркфлоу", "workflow", "cron", "azure", "render", "bedrock",
        ],
    },
    "product": {
        "label": "🎨 Отряд Product (Интерфейс и опыт использования)",
        "lead_builder": build_squad_lead_product,
        "member_names": [
            "product_designer", "kaist", "michigan_industrial_ux", "cmu_voice_ui", "mit_accessibility",
            "waterloo_pwa_offline", "nus_micro_animation", "ucl_information_architecture",
            "ms_ux_localization", "aalto_cognitive_load", "kaist_touch_interfaces",
            "rochester_gamification", "artcenter_react_designsystem", "usc_reactnative_lead",
            "bologna_swiftui_ios", "iitbombay_android_perf", "tsinghua_flutter_lark",
            "michigan_jest_frontend_qa", "eth_webgl_bim_viz", "google_pwa_devrel", "utaustin_wcag_impl",
            "mitmedialab_ui_animation", "utokyo_css_designsystem", "technion_mobile_security_impl",
            "twente_electron_desktop", "sydney_crdt_collab", "kaist_wearable_companion",
            "york_dashboard_perception_psychologist", "zahahadid_generative_structure_architect",
        ],
        "domain_keywords": [
            "ux", "интерфейс", "экран", "кнопк", "бот", "telegram", "панел", "react", "фронтенд",
            "юзабилити", "дашборд",
        ],
    },
    "anomaly": {
        "label": "🎯 Департамент Anomaly & Trust Engine",
        "lead_builder": build_squad_lead_anomaly,
        "member_names": [
            "princeton_algebraic_topology", "sorbonne_category_theory", "bonn_extreme_value_stats",
            "mit_inverse_problems", "grenoble_combinatorial_opt", "mit_complexity_theory",
            "pku_riemannian_geometry", "waterloo_graph_theory", "ens_functional_analysis",
            "weizmann_pq_crypto", "oxford_formal_logic", "south_carolina_approximation_theory",
            "eth_stochastic_calculus", "msu_pde_supply_chain", "amsterdam_information_theory",
            "stanford_mechanism_design", "hebrew_discrete_geometry", "utokyo_numerical_analysis",
            "harvard_error_correcting_codes", "caltech_stat_field_theory", "stanford_fewshot_metalearning",
            "maxplanck_causal_representation", "cambridge_bayesian_deep_learning", "cmu_nas_automl",
            "berkeley_rl_workflow", "maryland_adversarial_nlp", "utokyo_info_geometry",
            "helsinki_federated_privacy", "mit_tinyml_ondevice", "uw_ml_interpretability",
            "bonn_approximation_algorithms", "technion_online_algorithms", "rice_streaming_sketching",
            "harvard_algo_game_theory", "waterloo_quantum_algorithms", "mit_finegrained_complexity",
            "uw_randomized_algorithms", "amsterdam_kolmogorov_complexity",
            "bergen_parameterized_complexity", "harvard_deception_psych", "ucl_behavioral_data",
            "oxford_collusion_graph", "aston_forensic_linguistics", "mit_counterfactual_sim",
            "uiuc_input_anomaly", "caltech_trust_calibration", "insead_escalation_workflow",
            "fudan_behavior_robustness", "data_integrity_architect",
        ],
        "domain_keywords": [
            "mad-порог", "mad порог", "trust score", "калибровк", "l1-l9", "уровни l1", "deviation",
            "поведенческ анализ", "детекция обмана", "bayesian", "байесовск", "аномал", "anomaly",
        ],
    },
    "nlu": {
        "label": "🗣️  Департамент Language & Understanding (NLU)",
        "lead_builder": build_squad_lead_nlu,
        "member_names": [
            "msu_rggu_construction_nlu", "aalto_lowresource_nlp", "eth_multimodal_align", "pku_ner",
            "cambridge_coref", "cmu_relation_extraction", "cambridge_grammar_norm", "heidelberg_temporal",
            "utaustin_intent", "snu_multilingual", "appen_data_labeling", "oxford_active_learning",
            "deepmind_dialogue_rl", "apple_federated_learning", "nyu_semisupervised",
            "openai_curriculum_learning", "kaggle_ensemble_models", "ucla_probability_calibration",
            "uw_explainability", "google_automl_search", "mlops_engineer",
        ],
        "domain_keywords": [
            "nlu", "извлечен сущност", "семантик", "мультиязычн", "парсинг отчёт", "few-shot", "онтологи",
            "распознаван реч",
        ],
    },
    "qra": {
        "label": "🧪 Департамент QA & Reliability (QRA)",
        "lead_builder": build_squad_lead_qra,
        "member_names": [
            "meta_release_engineering", "k6_load_testing", "gremlin_chaos_testing",
            "hypothesis_property_testing", "percy_visual_regression", "huggingface_nlp_testing",
            "ibm_adversarial_ai_testing", "optimizely_network_ab", "datadog_synthetic_monitoring",
            "etsy_blameless_postmortem", "booking_pytest_test_architect", "gatling_load_testing_lead",
            "veracode_sast_dast_impl", "uber_appium_mobile_testing", "pactflow_contract_testing",
            "chromatic_visual_regression_impl", "deque_a11y_test_automation", "aws_fis_chaos_testing_impl",
            "deloitte_data_reconciliation", "microsoft_exploratory_tester", "reliability_engineer",
        ],
        "domain_keywords": [
            "тест", "покрыт", "pytest", "регресс", "observability", "slo", "нагрузочн тест", "chaos",
            "gameday",
        ],
    },
}


def _apply_roster_overrides() -> None:
    """Применяет решения HR Rotation Review (workflows/hr_rotation_review.py
    ::apply_rotation) — читает .state/squad_roster_overrides.json,
    формат {"имя": "целевой_департамент"}, и переносит имя в
    member_names целевого департамента, убирая из остальных.

    НЕ редактирует member_names ВЫШЕ в этом файле напрямую (регулярным
    выражением на каждый перенос) — это было бы риском тихо сломать
    синтаксис файла с ~600 именами в списках. Отдельный JSON-оверрайд
    поверх статически объявленного SQUADS безопаснее и даёт чистую
    историю кадровых решений в git-логе самого файла-оверрайда, а не
    диффами посреди полусотни других имён здесь.

    Если файла нет, он пустой или битый — SQUADS остаётся ровно таким,
    как объявлено выше, без изменений. Это норма (пока ни одной
    ротации не применялось), не ошибка."""
    import json
    from pathlib import Path

    overrides_path = Path(".state/squad_roster_overrides.json")
    if not overrides_path.exists():
        return
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[squads] Не удалось прочитать squad_roster_overrides.json ({e}) — оверрайды пропущены.")
        return

    for name, target_key in overrides.items():
        if target_key not in SQUADS:
            continue
        for key, squad in SQUADS.items():
            if key != target_key and name in squad["member_names"]:
                squad["member_names"].remove(name)
        if name not in SQUADS[target_key]["member_names"]:
            SQUADS[target_key]["member_names"].append(name)


_apply_roster_overrides()
