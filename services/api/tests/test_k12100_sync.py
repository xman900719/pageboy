"""k12100.com 拟人化安全同步 CLI 与权限/PII/去重/草稿门禁测试（全离线，不触达外部站点）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import k12100_sync as ks


def test_credentials_permission_guardrails_fail_closed(tmp_path):
    cfg_dir = tmp_path / "shutong-cfg"
    rc = ks.main(
        [
            "init-credentials",
            "--config-dir",
            str(cfg_dir),
            "--username",
            "stu_001",
            "--password",
            "secret_pw",
            "--admin-token",
            "adm_tok",
            "--api-url",
            "http://127.0.0.1:18765",
        ]
    )
    assert rc == 0
    env_file = cfg_dir / "k12100.env"
    assert stat.S_IMODE(cfg_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert ks.main(["status", "--config-dir", str(cfg_dir)]) == 0

    # 反例 1：凭据文件权限放宽为 0644 时必须拒绝加载
    os.chmod(env_file, 0o644)
    with pytest.raises(PermissionError, match="0600"):
        ks.load_env_credentials(env_file)
    assert ks.main(["status", "--config-dir", str(cfg_dir)]) == 1

    # 恢复文件权限，放宽目录权限为 0755 时同样必须拒绝加载
    os.chmod(env_file, 0o600)
    os.chmod(cfg_dir, 0o755)
    with pytest.raises(PermissionError, match="0700"):
        ks.load_env_credentials(env_file)


def test_strip_pii_fields_and_clamp_helpers():
    dirty = {
        "external_id": "ex-1",
        "title": "虚构测试数据：十月数学测",
        "student_name": "张三",
        "xm": "张三",
        "kaohao": "2026001",
        "phone": "13800138000",
        "姓名": "张三",
        "items": [
            {
                "question_label": "第1题",
                "earned_points": 2,
                "max_points": 3,
                "student_id": "S123",
                "stem_text": "实数运算求解",
                "wrong_reason": "符号看错",
                "token": "leak-tok",
            }
        ],
    }
    clean = ks.strip_pii_fields(dirty)
    serialized = json.dumps(clean, ensure_ascii=False)
    for sensitive in ("张三", "2026001", "13800138000", "S123", "leak-tok", "student_name", "kaohao"):
        assert sensitive not in serialized
    assert clean["items"][0]["question_label"] == "第1题"
    assert clean["items"][0]["stem_text"] == "实数运算求解"

    assert ks.clamp_max_exams(0) == 1
    assert ks.clamp_max_exams(2) == 2
    assert ks.clamp_max_exams(10) == 3
    assert ks.map_subject_code("道德与法治") == "ethics"
    assert ks.map_subject_code("物理") == "physics"


def test_sync_sanitized_exams_to_pageboy_draft_gate_and_dedup(client, auth, student_auth, published, tmp_path, monkeypatch):
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    ledger_path = tmp_path / "cfg" / "k12100-synced.json"
    sample_exams = [
        {
            "external_id": f"k12-m-{i}",
            "title": f"虚构测试数据：k12 数学第{i}次测验",
            "subject_hint": "数学",
            "exam_date": f"2026-10-1{i}",
            "earned_points": 80 + i,
            "max_points": 100,
            "student_name": "测试学生PII",
            "items": [
                {
                    "question_label": "第1题",
                    "earned_points": 2.0,
                    "max_points": 3.0,
                    "stem_text": "实数绝对值计算",
                    "wrong_reason": "符号粗心",
                },
                {
                    "question_label": "第2题",
                    "earned_points": 3.0,
                    "max_points": 3.0,
                    "stem_text": "二次函数顶点",
                },
            ],
        }
        for i in range(1, 5)
    ]

    def _testclient_request(api_url, path, token, *, method="GET", body=None):
        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            resp = client.get(path, headers=headers)
        else:
            resp = client.post(path, headers=headers, json=body)
        assert resp.status_code < 400, (path, resp.status_code, resp.text)
        return resp.json()

    # 首次同步严格限制为 max_exams=2
    first = ks.sync_sanitized_exams_to_pageboy(
        sample_exams,
        api_url="http://127.0.0.1:18765",
        admin_token="test-admin-secret",
        ledger_path=ledger_path,
        max_exams=2,
        use_ai=False,
        request_fn=_testclient_request,
    )
    assert first["processed"] == 2
    assert first["drafts_created"] == 4
    assert stat.S_IMODE(ledger_path.stat().st_mode) == 0o600

    # 验证所有导入小题严格处于 ocr_draft + confirmed_by_user=False，学生画像完全为空
    exam1_id = first["exams"][0]["exam_id"]
    detail1 = client.get(f"/api/school-exams/{exam1_id}", headers=auth).json()
    assert len(detail1["items"]) == 2
    assert all(it["scoring_origin"] == "ocr_draft" and it["confirmed_by_user"] is False for it in detail1["items"])
    assert all(it["draft_confidence"] == "external_sync" for it in detail1["items"])
    assert client.get("/api/guidance/profile?subject=math", headers=student_auth).json()["knowledge"] == []
    ana1 = client.get(f"/api/school-exams/{exam1_id}/error-analysis", headers=auth).json()
    assert ana1["status"] == "insufficient_items"
    assert ana1["overview"]["unconfirmed_draft_count"] == 2

    # 二次同步自动去重前 2 场，仅继续增量抓后 2 场
    second = ks.sync_sanitized_exams_to_pageboy(
        sample_exams,
        api_url="http://127.0.0.1:18765",
        admin_token="test-admin-secret",
        ledger_path=ledger_path,
        max_exams=2,
        use_ai=False,
        request_fn=_testclient_request,
    )
    assert second["skipped_dedup"] == 2
    assert second["processed"] == 2
    assert second["drafts_created"] == 4


def test_k12100_browser_mjs_syntax():
    res = subprocess.run(
        ["node", "--check", str(SCRIPTS_DIR / "k12100_browser.mjs")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr


def test_cli_merge_k12100_and_deepseek_zero_echo(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    cfg_dir = tmp_path / "cfg"
    # 1. 非交互写入 k12100 凭据（省略可选项时不阻塞），并准备既有 dev.env 令牌
    assert ks.main(["init-credentials", "--config-dir", str(cfg_dir), "--username", "stu_alpha", "--password", "secret_pw_999"]) == 0
    dev_env_dir = tmp_path / "pb-home" / "development" / "env"
    dev_env_dir.mkdir(parents=True, mode=0o700)
    dev_env_file = dev_env_dir / "dev.env"
    dev_env_file.write_text(
        "# test dev\nSHUTONG_STUDENT_TOKEN=dev-stu-keep\nSHUTONG_ADMIN_TOKEN=dev-adm-keep\n",
        encoding="utf-8",
    )
    os.chmod(dev_env_file, 0o600)

    # 2. 通过 config-deepseek 注入 Key 并同步 dev.env，保留双方既有字段且绝不明文回显
    rc = ks.main(
        [
            "config-deepseek",
            "--config-dir",
            str(cfg_dir),
            "--deepseek-api-key",
            "sk-deepseek-supersecret-1234",
            "--base-url",
            "https://api.deepseek.com/v1",
            "--sync-dev-env",
            "--dev-env-path",
            str(dev_env_file),
        ]
    )
    assert rc == 0
    capsys_io = capsys.readouterr()
    combined_out = capsys_io.out + capsys_io.err
    assert "secret_pw_999" not in combined_out
    assert "sk-deepseek-supersecret-1234" not in combined_out
    assert "sk-d***1234" in combined_out

    creds = ks.load_env_credentials(cfg_dir / "k12100.env")
    assert creds["K12100_USERNAME"] == "stu_alpha"
    assert creds["K12100_PASSWORD"] == "secret_pw_999"
    assert creds["DEEPSEEK_API_KEY"] == "sk-deepseek-supersecret-1234"
    assert creds["SHUTONG_AI_API_KEY"] == "sk-deepseek-supersecret-1234"
    assert creds["SHUTONG_VISION_API_KEY"] == "sk-deepseek-supersecret-1234"
    assert creds["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com/v1"
    assert stat.S_IMODE(dev_env_file.stat().st_mode) == 0o600
    dev_text = dev_env_file.read_text(encoding="utf-8")
    assert "SHUTONG_STUDENT_TOKEN=dev-stu-keep" in dev_text
    assert "SHUTONG_ADMIN_TOKEN=dev-adm-keep" in dev_text
    assert "DEEPSEEK_API_KEY=sk-deepseek-supersecret-1234" in dev_text

    # 3. 再次更新 k12100 凭据不得丢失已配置的 DeepSeek Key
    assert ks.main(["init-credentials", "--config-dir", str(cfg_dir), "--username", "stu_beta", "--password", "new_pw_888"]) == 0
    creds_after = ks.load_env_credentials(cfg_dir / "k12100.env")
    assert creds_after["K12100_USERNAME"] == "stu_beta"
    assert creds_after["DEEPSEEK_API_KEY"] == "sk-deepseek-supersecret-1234"

    # 4. status 校验通过且仅显示脱敏摘要
    assert ks.main(["status", "--config-dir", str(cfg_dir)]) == 0
    status_out = capsys.readouterr().out
    assert "sk-d***1234" in status_out
    assert "sk-deepseek-supersecret-1234" not in status_out


def test_config_deepseek_from_shell_clear_and_fail_closed(tmp_path, monkeypatch, capsys):
    cfg_dir = tmp_path / "cfg"
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # 反例 1：Shell 未配置时 --from-shell 必须 fail-closed
    assert ks.main(["config-deepseek", "--config-dir", str(cfg_dir), "--from-shell"]) == 1

    # 反例 2：非法 Base URL 拒绝写入
    assert ks.main(["config-deepseek", "--config-dir", str(cfg_dir), "--deepseek-api-key", "sk-1234567890", "--base-url", "ftp://bad"]) == 1

    # 正例：从 Shell 导入 --from-shell 且不回显明文
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-shell-abcxyz9876")
    assert ks.main(["config-deepseek", "--config-dir", str(cfg_dir), "--from-shell"]) == 0
    out_io = capsys.readouterr()
    assert "sk-shell-abcxyz9876" not in (out_io.out + out_io.err)
    assert "sk-s***9876" in out_io.out

    # 反例 3：仅配了 DeepSeek Key 但没配 k12100 账号时，probe 直接拒绝（不误起浏览器）
    assert ks.main(["probe", "--config-dir", str(cfg_dir)]) == 1
    assert "尚未配置 k12100.com 账号或密码" in capsys.readouterr().err

    # --clear 清理 DeepSeek AI 字段，同时保留已有 k12100 账号
    assert ks.main(["init-credentials", "--config-dir", str(cfg_dir), "--username", "stu_keep", "--password", "pw_keep"]) == 0
    assert ks.main(["config-deepseek", "--config-dir", str(cfg_dir), "--clear"]) == 0
    creds_cleared = ks.load_env_credentials(cfg_dir / "k12100.env")
    assert creds_cleared["K12100_USERNAME"] == "stu_keep"
    assert "DEEPSEEK_API_KEY" not in creds_cleared
    assert "SHUTONG_AI_API_KEY" not in creds_cleared


def test_run_dev_env_and_manual_env_ai_cli_helpers(tmp_path, monkeypatch, capsys):
    import run_dev_env as rde
    import run_manual_test_env as rmte

    pb_home = tmp_path / "pb-home"
    dev_home = pb_home / "development"
    dev_env_dir = dev_home / "env"
    dev_home.mkdir(parents=True)
    dev_env_file = dev_env_dir / "dev.env"
    web_dev_env_file = tmp_path / ".env.development.local"

    monkeypatch.setattr(rde, "PAGEBOY_HOME", pb_home)
    monkeypatch.setattr(rde, "DEV_HOME", dev_home)
    monkeypatch.setattr(rde, "DEV_ENV_DIR", dev_env_dir)
    monkeypatch.setattr(rde, "DEV_ENV_FILE", dev_env_file)
    monkeypatch.setattr(rde, "WEB_DEV_ENV_FILE", web_dev_env_file)

    assert rde.run_cli(["init-env"]) == 0
    capsys.readouterr()
    initial = rde.parse_env_file(dev_env_file)
    stu_tok = initial["SHUTONG_STUDENT_TOKEN"]
    adm_tok = initial["SHUTONG_ADMIN_TOKEN"]
    assert stat.S_IMODE(dev_env_file.stat().st_mode) == 0o600

    assert rde.run_cli(["config-ai", "--deepseek-api-key", "sk-dev-cli-778899"]) == 0
    out_ai = capsys.readouterr().out
    assert "sk-dev-cli-778899" not in out_ai
    assert "sk-d***8899" in out_ai
    with_ai = rde.parse_env_file(dev_env_file)
    assert with_ai["SHUTONG_STUDENT_TOKEN"] == stu_tok
    assert with_ai["SHUTONG_ADMIN_TOKEN"] == adm_tok
    assert with_ai["DEEPSEEK_API_KEY"] == "sk-dev-cli-778899"
    assert with_ai["SHUTONG_AI_API_KEY"] == "sk-dev-cli-778899"

    assert rde.run_cli(["config-ai", "--clear"]) == 0
    after_clear = rde.parse_env_file(dev_env_file)
    assert after_clear["SHUTONG_STUDENT_TOKEN"] == stu_tok
    assert "DEEPSEEK_API_KEY" not in after_clear

    # 测试人工测试环境注入逻辑：仅接受合规权限文件，并支持 --no-ai-key 隔离
    k12_dir = tmp_path / "k12-home"
    ks.ensure_secure_dir(k12_dir)
    ks.merge_secure_env_file(k12_dir / "k12100.env", {"DEEPSEEK_API_KEY": "sk-k12-src-445566"})
    monkeypatch.setenv("SHUTONG_K12100_CONFIG_DIR", str(k12_dir))
    monkeypatch.setattr(rmte, "_PAGEBOY_DEV_HOME", dev_home)

    env_clean: dict[str, str] = {}
    src_label = rmte._inject_ai_env(env_clean, no_ai_key=False)
    assert "k12100.env" in src_label
    assert "sk-k12-src-445566" not in src_label
    assert env_clean["SHUTONG_AI_API_KEY"] == "sk-k12-src-445566"
    assert env_clean["DEEPSEEK_API_KEY"] == "sk-k12-src-445566"

    # 权限放宽为 0644 后必须拒绝加载
    os.chmod(k12_dir / "k12100.env", 0o644)
    env_loose: dict[str, str] = {}
    assert "未配置" in rmte._inject_ai_env(env_loose, no_ai_key=False)
    assert "SHUTONG_AI_API_KEY" not in env_loose

    # --no-ai-key 清空 Shell 中既有密钥以验证 503 fail-closed
    env_disabled = {"DEEPSEEK_API_KEY": "sk-shell-present", "SHUTONG_AI_API_KEY": "sk-shell-present"}
    disabled_label = rmte._inject_ai_env(env_disabled, no_ai_key=True)
    assert "--no-ai-key" in disabled_label
    assert "DEEPSEEK_API_KEY" not in env_disabled
    assert "SHUTONG_AI_API_KEY" not in env_disabled


def test_cli_collect_writes_0600_sanitized_bundle_and_zero_pii(tmp_path, monkeypatch, capsys):
    """collect 子命令应写出 0600 脱敏采集包 JSON，且磁盘与 stdout 均不得出现凭据或 PII。"""
    import json
    import stat

    cfg_dir = tmp_path / "cfg"
    assert (
        ks.main(
            [
                "init-credentials",
                "--config-dir",
                str(cfg_dir),
                "--username",
                "13900001111",
                "--password",
                "Secret-K12-Pwd",
            ]
        )
        == 0
    )
    capsys.readouterr()

    seen: dict[str, object] = {}

    def _fake_browser(mode, paths, creds, args):
        seen["mode"] = mode
        seen["exam_keyword"] = getattr(args, "exam_keyword", "")
        return {
            "status": "collected",
            "studName": "李四",
            "studentId": "S-PII-001",
            "exams": [
                {
                    "examName": "虚构测试数据 · 期中测试",
                    "examDate": "2026-10-18",
                    "schoolRank": 3,
                    "subjects": [
                        {
                            "subjectName": "数学",
                            "score": 95,
                            "fullScore": 100,
                            "smallQuestions": [{"questionName": "1", "score": 2, "fullScore": 2}],
                            "card_images": [],
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(ks, "_run_browser_node", _fake_browser)
    out_file = tmp_path / "collected_bundle.json"
    rc = ks.main(
        [
            "collect",
            "--config-dir",
            str(cfg_dir),
            "--exam-keyword",
            "虚构测试数据",
            "--output",
            str(out_file),
            "--headless",
        ]
    )
    assert rc == 0
    assert seen == {"mode": "collect", "exam_keyword": "虚构测试数据"}
    assert out_file.exists()
    assert stat.S_IMODE(out_file.stat().st_mode) == 0o600

    disk_text = out_file.read_text(encoding="utf-8")
    for forbidden in ("李四", "S-PII-001", "schoolRank", "studName", "13900001111", "Secret-K12-Pwd"):
        assert forbidden not in disk_text

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    for forbidden in ("李四", "S-PII-001", "13900001111", "Secret-K12-Pwd"):
        assert forbidden not in combined
    summary = json.loads(captured.out)
    assert summary["status"] == "collected"
    assert summary["output_file"] == str(out_file.resolve())


def test_backfill_cli_dry_run_and_real_import_bundle_creates_0600_ledger(tmp_path, client, capsys, monkeypatch):
    """backfill 编排器与 CLI 子命令应支持 dry-run 预演，且真实导入后写入 0600 去重台账。"""
    import base64
    from io import BytesIO
    import json
    import stat
    from PIL import Image

    monkeypatch.delenv("SHUTONG_AI_API_KEY", raising=False)
    monkeypatch.delenv("SHUTONG_VISION_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    buf = BytesIO()
    Image.new("RGB", (48, 48), color=(240, 245, 250)).save(buf, format="JPEG")
    card_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    bundle = {
        "examName": "虚构测试数据 · 离线采集包测试",
        "examDate": "2026-10-16",
        "exams": [
            {
                "examName": "虚构测试数据 · 离线采集包测试",
                "examDate": "2026-10-16",
                "subjects": [
                    {
                        "subjectName": "数学",
                        "score": 92,
                        "fullScore": 100,
                        "smallQuestions": [
                            {"questionName": "1", "score": 2, "fullScore": 2},
                            {"questionName": "2", "score": 0, "fullScore": 2},
                        ],
                        "card_images": [{"filename": "math_card_1.jpg", "data_base64": card_b64}],
                    }
                ],
            }
        ],
    }

    ledger_path = tmp_path / "cfg" / "synced_exams.json"

    def _forbid_request(*args, **kwargs):
        raise AssertionError("dry_run 不应发起 HTTP 请求")

    dry_res = ks.backfill_sanitized_bundle_to_pageboy(
        bundle,
        api_url="http://127.0.0.1:8000",
        admin_token="test-admin-secret",
        ledger_path=ledger_path,
        dry_run=True,
        request_fn=_forbid_request,
    )
    assert dry_res["dry_run"] is True
    assert dry_res["subjects"][0]["smallQuestionsCount"] == 2
    assert not ledger_path.exists()

    def _client_request(api_url, path, token, *, method="GET", body=None, timeout=240):
        resp = client.request(
            method,
            path,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    real_res = ks.backfill_sanitized_bundle_to_pageboy(
        bundle,
        api_url="http://127.0.0.1:8000",
        admin_token="test-admin-secret",
        ledger_path=ledger_path,
        use_ai=False,
        request_fn=_client_request,
    )
    assert len(real_res["subjects"]) == 1
    subj = real_res["subjects"][0]
    assert subj["subject"] == "math"
    assert subj["drafts_created"] == 2
    assert subj["attachments_uploaded"] == 1
    assert real_res["knowledge_evidence_created"] == 0
    assert ledger_path.exists()
    assert stat.S_IMODE(ledger_path.stat().st_mode) == 0o600

    # 再验证 CLI backfill --input-json --dry-run 端到端参数解析
    cfg_dir = tmp_path / "cli_cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    bundle_file = tmp_path / "offline_bundle.json"
    bundle_file.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    rc = ks.main(
        [
            "backfill",
            "--config-dir",
            str(cfg_dir),
            "--input-json",
            str(bundle_file),
            "--dry-run",
        ]
    )
    assert rc == 0
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out["dry_run"] is True
    assert cli_out["exam_count"] == 1
