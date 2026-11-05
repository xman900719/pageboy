#!/usr/bin/env bash
# 生产侧一次性准备（需 root）：创建生产专用用户与生产目录、单向发布用裸仓库，
# 复制生产配置/附件/二进制到生产目录。幂等；**不停止、不修改正在运行的旧栈，不删除任何开发侧文件**。
# 用法（由开发用户经 sudo 执行）：  sudo bash infra/provision-prod.sh
# 后续步骤见 docs/operations/prod-separation-runbook.md。
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "需要 root：sudo bash $0" >&2; exit 1; }
DEV_USER="${SUDO_USER:?请经 sudo 由开发用户执行（需要 SUDO_USER 以授予发布推送权限）}"
PROD_USER=shutong-prod
DEPLOY_GROUP=shutong-deploy
ROOT="${SHUTONG_PROD_ROOT:-/media/xc/backup_ext4/prod-env/pageboy}"
DEV_INFRA="$(cd "$(dirname "$0")" && pwd)"

# 0. 权限穿透：若生产根目录位于 /media/xc 下，为生产用户打通 /media/xc 的穿透权限
if [[ "$ROOT" == /media/xc/* ]]; then
  setfacl -m "u:$PROD_USER:--x" /media/xc 2>/dev/null || true
fi

# 1. 用户与组：生产用户可用系统 Docker；开发用户仅加入发布组（只能向裸仓库推送代码，读不到 env/）。
id "$PROD_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$PROD_USER"
passwd -l "$PROD_USER" >/dev/null   # 无口令登录；仅经 sudo -iu 进入
usermod -aG docker "$PROD_USER"
getent group "$DEPLOY_GROUP" >/dev/null || groupadd "$DEPLOY_GROUP"
usermod -aG "$DEPLOY_GROUP" "$DEV_USER"

# 2. 目录：env/data/logs 仅生产用户可读；ROOT 本身 750。
install -d -o "$PROD_USER" -g "$PROD_USER" -m 750 "$ROOT" "$ROOT/env" "$ROOT/data" "$ROOT/logs" "$ROOT/bin"
install -d -o "$PROD_USER" -g "$PROD_USER" -m 700 "$ROOT/data/attachments"

# 3. 单向发布裸仓库：开发 push → 生产 pull（生产用户读不到开发目录，开发用户读不到生产机密）。
if [[ ! -d "$ROOT/release.git" ]]; then
  (cd / && sudo -u "$PROD_USER" git init --bare --shared=group -b release "$ROOT/release.git" >/dev/null)
fi
chgrp -R "$DEPLOY_GROUP" "$ROOT/release.git"
chmod -R g+rwX "$ROOT/release.git"
find "$ROOT/release.git" -type d -exec chmod g+s {} +
# ROOT 为 750 时发布组无法穿越；给组 x 位仅用于到达 release.git（不含 env/data 读权限，它们各自 700/750 且属组为生产用户组）。
chgrp "$DEPLOY_GROUP" "$ROOT"; chmod 710 "$ROOT"
(cd / && sudo -u "$DEV_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$ROOT/release.git") \
  || (cd / && sudo -u "$DEV_USER" git config --global --add safe.directory "$ROOT/release.git")
(cd / && sudo -u "$PROD_USER" git config --global --get-all safe.directory 2>/dev/null | grep -qxF "$ROOT/release.git") \
  || (cd / && sudo -u "$PROD_USER" git config --global --add safe.directory "$ROOT/release.git")

# 4. 生产配置：从现有 infra/.env 派生（沿用既有密钥），仅改路径与运行 uid。已存在则不覆盖。
if [[ ! -f "$ROOT/env/prod.env" ]]; then
  [[ -f "$DEV_INFRA/.env" ]] || { echo "缺少 $DEV_INFRA/.env" >&2; exit 1; }
  uid="$(id -u "$PROD_USER")"; gid="$(id -g "$PROD_USER")"
  grep -v -E '^(RESTIC_PASSWORD_FILE|ATTACHMENTS_DIR|SHUTONG_ATTACHMENTS_DIR|SHUTONG_UID|SHUTONG_GID)=' "$DEV_INFRA/.env" > "$ROOT/env/prod.env"
  {
    echo "RESTIC_PASSWORD_FILE=$ROOT/env/restic-password"
    echo "ATTACHMENTS_DIR=$ROOT/data/attachments"
    echo "SHUTONG_ATTACHMENTS_DIR=$ROOT/data/attachments"
    echo "SHUTONG_UID=$uid"
    echo "SHUTONG_GID=$gid"
  } >> "$ROOT/env/prod.env"
  [[ -f "$DEV_INFRA/.local/restic-password" ]] && install -o "$PROD_USER" -g "$PROD_USER" -m 600 "$DEV_INFRA/.local/restic-password" "$ROOT/env/restic-password"
  chown "$PROD_USER:$PROD_USER" "$ROOT/env/prod.env"; chmod 600 "$ROOT/env/prod.env"
fi

# 5. 附件初次同步（切换时还会在停服后再同步一次以保证一致）与二进制。
rsync -a --chown="$PROD_USER:$PROD_USER" "$DEV_INFRA/private-data/attachments/" "$ROOT/data/attachments/"
for b in caddy restic; do
  [[ -x "$DEV_INFRA/.local/$b" ]] && install -o "$PROD_USER" -g "$PROD_USER" -m 755 "$DEV_INFRA/.local/$b" "$ROOT/bin/$b"
done

# 6. Caddy 服务单元：仅安装，不启用、不启动（切换步骤中启动）。
install -m 644 "$DEV_INFRA/shutong-caddy.service" /etc/systemd/system/shutong-caddy.service
systemctl daemon-reload

echo "完成。注意：组成员变更需要重新登录（或 newgrp $DEPLOY_GROUP）才对 $DEV_USER 生效。"
echo "旧栈未被改动。下一步：docs/operations/prod-separation-runbook.md 第 3 步起。"
