"""ST-024-B isolated regression: all external commands are fake; no real Docker/R2 calls."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from check_release_ci import verify, REQUIRED

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40

def run_record(**kw):
    return dict(id=1, created_at="2026-11-27T00:00:00Z", run_attempt=1,
                head_sha=SHA, head_branch="main", event="push", path=".github/workflows/verify.yml",
                status="completed", conclusion="success") | kw

def jobs():
    return [dict(name=n, status="completed", conclusion="success") for n in sorted(REQUIRED)]

class ReleaseGate(unittest.TestCase):
    def check(self, records, entries):
        return verify(SHA, lambda p: {"workflow_runs": records} if "/actions/runs?" in p else {"jobs": entries})
    def test_success(self):
        self.assertEqual(self.check([run_record()], jobs()), 1)
    def test_fail_closed(self):
        for records, entries in [([], jobs()), ([run_record(head_sha="b"*40)], jobs()),
            ([run_record(event="pull_request")], jobs()), ([run_record(conclusion="failure")], jobs()),
            ([run_record(), run_record(id=2, status="in_progress", conclusion=None)], jobs()),
            ([run_record()], jobs()[:-1]), ([run_record()], jobs()+[jobs()[0]]),
            ([run_record()], [dict(j, conclusion="skipped") for j in jobs()])]:
            with self.subTest(records=records, entries=entries), self.assertRaises(ValueError):
                self.check(records, entries)

class BackupGate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.infra = self.root / "infra"; self.infra.mkdir()
        (self.infra / "backup.sh").write_bytes((ROOT / "infra/backup.sh").read_bytes())
        (self.infra / "compose.yaml").touch()
        scripts=self.root/"scripts"; scripts.mkdir()
        (scripts/"web_artifact_provenance.py").write_bytes((ROOT/"scripts/web_artifact_provenance.py").read_bytes())
        state=self.infra/".local"; state.mkdir(); (state/"deployed-tag").write_text("api-aaaaaaa\n")
        dist=self.root/"apps/web/dist"; (dist/"assets").mkdir(parents=True)
        for n in ("index.html","admin.html","assets/app.js"): (dist/n).write_text("synthetic")
        self.bin = self.root / "bin"; self.bin.mkdir()
        self.attach = self.root / "attachments"; self.attach.mkdir()
        (self.attach / "synthetic.txt").write_text("虚构测试数据")
        self.conf = self.root / "test.env"; self.conf.write_text("")
        self.log = self.root / "calls"
        self.env = dict(PATH=f"{self.bin}:/usr/bin:/bin", HOME=str(self.root), ENV_FILE=str(self.conf),
                        ATTACHMENTS_DIR=str(self.attach), TEST_LOG=str(self.log),
                        RESTIC_REPOSITORY="mock", RESTIC_PASSWORD_FILE="mock", HEALTHCHECKS_PING_URL="mock")
        self.fake("docker", """echo docker >> "$TEST_LOG"
case "$*" in
  *psql*) printf '%s\n' "${TEST_REV-0023}" ;;
  *pg_dump*) printf 'synthetic dump' ;;
  *printenv*) printf 'api-aaaaaaa\n' ;;
  *'ps -q api'*) printf 'aaaaaaaaaaaa\n' ;;
  *'.Mounts'*) printf '[{"Type":"bind","Source":"%s","Destination":"/var/lib/shutong/attachments"}]\n' "${TEST_MOUNT:-$ATTACHMENTS_DIR}" ;;
  *'.Config.Image'*) printf 'shutong-api:api-aaaaaaa\n' ;;
  *'.State.Running'*) printf 'true\n' ;;
  *'.Config.Labels'*) printf '%s\n' "${TEST_LABEL:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}" ;;
  *'.Image'*|*'.Id'*) printf 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n' ;;
  *) exit 99 ;;
esac""")
        self.fake("restic", """echo "restic $1" >> "$TEST_LOG"
case "$1" in
  backup) printf '%s\n' "$TEST_RESTIC_JSON" ;;
  check) exit "${TEST_CHECK_RC:-0}" ;;
  snapshots) printf '%s\n' '[{"id":"abcdef1234567890","tags":["shutong-foundation"]}]' ;;
  *) exit 99 ;;
esac""")
        # Default JSON is explicit, avoiding shell expansion ambiguity.
        self.env["TEST_RESTIC_JSON"] = '{"message_type":"summary","snapshot_id":"abcdef12"}'
        self.fake("curl", 'echo curl >> "$TEST_LOG"')
        self.fake("git", '[[ "$*" == *"cat-file -t"* ]] && echo commit')
    def fake(self, name, body):
        p = self.bin / name; p.write_text("#!/bin/bash\nset -eu\n"+body+"\n"); p.chmod(0o700)
    def run_backup(self, **env):
        return subprocess.run(["bash", str(self.infra / "backup.sh")], env=self.env | env, capture_output=True, text=True)
    def calls(self):
        return self.log.read_text() if self.log.exists() else ""
    def test_missing_attachments(self):
        self.attach.rename(self.root / "missing")
        self.assertNotEqual(self.run_backup().returncode, 0)
        self.assertEqual(self.calls(), "")
    def test_unknown_revision(self):
        self.assertNotEqual(self.run_backup(TEST_REV="").returncode, 0)
        self.assertNotIn("restic", self.calls())
    def test_local_no_overwrite(self):
        out = self.root / "out"; out.mkdir(); (out / "keep").write_text("keep")
        self.assertNotEqual(self.run_backup(BACKUP_OUTPUT_DIR=str(out)).returncode, 0)
        self.assertEqual((out / "keep").read_text(), "keep")
    def test_legacy_local_refused(self):
        out = self.root / "out"
        r = self.run_backup(BACKUP_OUTPUT_DIR=str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSED", r.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(self.calls(), "")
    def test_snapshot_check(self):
        for args in ({"TEST_RESTIC_JSON":"{}"}, {"TEST_CHECK_RC":"1"}):
            r = self.run_backup(**args)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("curl", self.calls())
    def test_api_mismatch_refused(self):
        r = self.run_backup(TEST_LABEL="cccccccccccccccccccccccccccccccccccccccc")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("restic", self.calls())
    def test_mount_mismatch_refused(self):
        r = self.run_backup(TEST_MOUNT=str(self.root / "wrong"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("attachment mount differs", r.stderr)
        self.assertNotIn("restic", self.calls())
    def test_remote_stub_success(self):
        r = self.run_backup()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BACKUP_SNAPSHOT_OK=abcdef12", r.stdout)
        self.assertIn("BUNDLE_CHECK_OK", r.stdout)
        self.assertIn("curl", self.calls())
        self.assertNotIn("forget", self.calls())
        self.assertNotIn("prune", self.calls())

if __name__ == "__main__":
    unittest.main()
