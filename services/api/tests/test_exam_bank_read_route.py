"""Historical corpus routing: isolated synthetic data, no persistent DB writes."""
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from shutong import private_files as files
from shutong.home import init_home_identity

FLAG = "SHUTONG_EXAM_BANK_MANIFEST_SHA256"


@pytest.fixture
def bank(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGEBOY_HOME", str(tmp_path))
    monkeypatch.setenv("SHUTONG_ENV", "development")
    monkeypatch.delenv("SHUTONG_PRIVATE_DIR", raising=False)
    dev = tmp_path / "development"
    init_home_identity(dev, "development")
    data = dev / "data"
    root = data / "exam_bank_2018_2025"
    legacy = data / "attachments"
    legacy.mkdir(parents=True)
    content = b"SYNTHETIC TEST DATA - historical corpus"
    key = "a" * 32
    digest = hashlib.sha256(content).hexdigest()
    att = SimpleNamespace(id="synthetic-attachment", source_document_id="synthetic-source",
                          storage_key=key, sha256=digest, byte_size=len(content))
    entry = dict(attachment_id=att.id, source_document_id=att.source_document_id,
                 storage_key=key, sha256=digest, bytes=len(content),
                 raw="2018/math/raw/" + key + ".docx")
    dest = root / entry["raw"]
    dest.parent.mkdir(parents=True)
    dest.write_bytes(content)
    (legacy / key).write_bytes(content)
    def pin(entries):
        payload = json.dumps({"entries": entries}).encode()
        (root / "manifest.json").write_bytes(payload)
        monkeypatch.setenv(FLAG, hashlib.sha256(payload).hexdigest())
    pin([entry])
    return SimpleNamespace(att=att, entry=entry, dest=dest, legacy=legacy,
                           content=content, pin=pin)


def test_mapped_uses_new_path_even_without_old_file(bank):
    (bank.legacy / bank.att.storage_key).unlink()
    assert files._exam_bank_read_path(bank.att) == bank.dest
    assert files.load_blob(bank.att) == bank.content


def test_unmapped_and_disabled_use_legacy(bank, monkeypatch):
    a = SimpleNamespace(**vars(bank.att))
    a.id = "other-attachment"
    a.storage_key = "b" * 32
    (bank.legacy / a.storage_key).write_bytes(bank.content)
    assert files.load_blob(a) == bank.content
    assert files._exam_bank_read_path(SimpleNamespace(storage_key=a.storage_key)) is None
    monkeypatch.delenv(FLAG)
    assert files._exam_bank_read_path(bank.att) is None
    assert files.load_blob(bank.att) == bank.content


@pytest.mark.parametrize("case", ["wrong-pin", "wrong-identity", "missing", "tamper",
                                  "symlink", "duplicate", "traversal", "production"])
def test_mapped_errors_fail_closed(bank, monkeypatch, case):
    if case == "wrong-pin":
        monkeypatch.setenv(FLAG, "0" * 64)
    elif case == "wrong-identity":
        bank.att.source_document_id = "different-source"
    elif case == "missing":
        bank.dest.unlink()
    elif case == "tamper":
        bank.dest.write_bytes(b"corrupt")
    elif case == "symlink":
        bank.dest.unlink()
        bank.dest.symlink_to(bank.legacy / bank.att.storage_key)
    elif case == "duplicate":
        bank.pin([bank.entry, bank.entry])
    elif case == "traversal":
        bank.pin([{**bank.entry, "raw": "../attachments/" + bank.att.storage_key}])
    elif case == "production":
        monkeypatch.setenv("SHUTONG_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        files.load_blob(bank.att)
    assert exc.value.status_code == 409
    assert exc.value.detail == ("ATTACHMENT_HASH_MISMATCH" if case == "tamper" else "EXAM_BANK_STORAGE_INVALID")


@pytest.fixture
def production_bank(bank, tmp_path, monkeypatch):
    import shutil
    prod = tmp_path / "production" / "data"
    prod.mkdir(parents=True)
    root = prod / "exam_bank_2018_2025"
    shutil.copytree(bank.dest.parents[3], root)
    legacy = prod / "attachments"
    shutil.copytree(bank.legacy, legacy)
    monkeypatch.setenv("SHUTONG_ENV", "production")
    monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(legacy))
    monkeypatch.setenv("SHUTONG_EXAM_BANK_DIR", str(root))
    def pin(entries, environment="production"):
        payload = json.dumps({"environment": environment, "entries": entries}).encode()
        (root / "manifest.json").write_bytes(payload)
        monkeypatch.setenv(FLAG, hashlib.sha256(payload).hexdigest())
    pin([bank.entry])
    return SimpleNamespace(att=bank.att, entry=bank.entry, root=root, legacy=legacy,
                           dest=root / bank.entry["raw"], content=bank.content, pin=pin)


def test_production_mapped_without_legacy(production_bank):
    b = production_bank
    (b.legacy / b.att.storage_key).unlink()
    assert files._exam_bank_read_path(b.att) == b.dest
    assert files.load_blob(b.att) == b.content


def test_production_unmapped_and_disabled(production_bank, monkeypatch):
    b = production_bank
    a = SimpleNamespace(**vars(b.att))
    a.id = "unmapped"; a.storage_key = "b" * 32
    (b.legacy / a.storage_key).write_bytes(b.content)
    assert files.load_blob(a) == b.content
    monkeypatch.delenv(FLAG)
    assert files.load_blob(b.att) == b.content


@pytest.mark.parametrize("case", ["wrong-root", "no-root", "dev-manifest", "missing", "tamper", "symlink", "bad-pin", "cross-environment"])
def test_production_fail_closed(production_bank, tmp_path, monkeypatch, case):
    b = production_bank
    if case == "wrong-root":
        monkeypatch.setenv("SHUTONG_EXAM_BANK_DIR", str(tmp_path / "other"))
    elif case == "no-root":
        monkeypatch.delenv("SHUTONG_EXAM_BANK_DIR")
    elif case == "dev-manifest":
        b.pin([b.entry], environment="development")
    elif case == "missing":
        b.dest.unlink()
    elif case == "tamper":
        b.dest.write_bytes(b"SYNTHETIC CORRUPTION")
    elif case == "symlink":
        b.dest.unlink(); b.dest.symlink_to(b.legacy / b.att.storage_key)
    elif case == "bad-pin":
        monkeypatch.setenv(FLAG, "0" * 64)
    elif case == "cross-environment":
        data = tmp_path / "development" / "data"
        monkeypatch.setenv("SHUTONG_PRIVATE_DIR", str(data / "attachments"))
        monkeypatch.setenv("SHUTONG_EXAM_BANK_DIR", str(data / "exam_bank_2018_2025"))
    with pytest.raises(HTTPException) as exc:
        files.load_blob(b.att)
    assert exc.value.status_code == 409
    assert exc.value.detail == ("ATTACHMENT_HASH_MISMATCH" if case == "tamper" else "EXAM_BANK_STORAGE_INVALID")
