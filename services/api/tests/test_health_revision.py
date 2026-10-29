"""ST-017 部署身份：/health/live 如实报告构建标识（未设置即 dev，不虚构版本号）。"""


def test_health_live_defaults_to_dev(client):
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"
    assert r.json()["app_revision"] == "dev"  # 缺省不得包装成具体版本


def test_health_live_reports_build_revision(client, monkeypatch):
    monkeypatch.setenv("SHUTONG_APP_REVISION", "drill-b")
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["app_revision"] == "drill-b"
