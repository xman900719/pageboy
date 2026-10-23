"""练习约束：exposures.question_id 回填与两条唯一索引（条件式迁移）。

- exposures 增加非规范化列 question_id（FK→questions.id）并从 question_versions 回填；
- 部分唯一索引 uq_exposure_first_unseen ON (learner_id, question_id) WHERE is_unseen_at_exposure，
  保证每学习者每逻辑题至多一次未见首曝；
- 唯一索引 uq_attempt_exposure ON answer_attempts(exposure_id)，保证每曝光至多一条有效作答；
- 0001 用当前 models create_all 建表，新库在 0001 即含新列/新索引，故本迁移全程 inspect 判定后条件执行；
- 遗留库若已存在重复未见认定或同曝光双作答（仅旧并发缺陷可产生），索引创建将诚实失败，
  需人工裁决，不自动改写历史。
- SQLite 无事务性 DDL：孤儿断言触发 RuntimeError 时列已添加而回填未完成（非原子失败点），需人工重跑迁移或清理。
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "question_id" not in [c["name"] for c in insp.get_columns("exposures")]:
        # alembic 原生 add_column 无法附带外键（SQLite 无 ALTER ADD CONSTRAINT，会抛 NotImplementedError）；
        # 经 batch 重建增列并建 FK，与 0001 create_all 产出的表结构一致，alembic check 两路径均干净。
        with op.batch_alter_table("exposures") as batch:
            batch.add_column(sa.Column("question_id", sa.String(36), nullable=True))
            # 命名仅满足 batch API 要求；alembic 外键比对按"未命名签名"（列+引用表）进行，与模型侧未命名外键等价。
            batch.create_foreign_key("fk_exposures_question_id", "questions", ["question_id"], ["id"])
    bind.execute(sa.text("UPDATE exposures SET question_id = (SELECT question_id FROM question_versions WHERE question_versions.id = exposures.question_version_id) WHERE question_id IS NULL"))
    orphans = bind.execute(sa.text("SELECT count(*) FROM exposures WHERE question_id IS NULL")).scalar()
    if orphans:
        raise RuntimeError("exposures contain rows without question_id (orphaned question_version reference)")
    exposure_indexes = {i["name"] for i in insp.get_indexes("exposures")}
    if "uq_exposure_first_unseen" not in exposure_indexes:
        op.create_index("uq_exposure_first_unseen", "exposures", ["learner_id", "question_id"], unique=True, sqlite_where=sa.text("is_unseen_at_exposure"), postgresql_where=sa.text("is_unseen_at_exposure"))
    attempt_indexes = {i["name"] for i in insp.get_indexes("answer_attempts")}
    if "uq_attempt_exposure" not in attempt_indexes:
        op.create_index("uq_attempt_exposure", "answer_attempts", ["exposure_id"], unique=True)


def downgrade():
    # 仅用于隔离开发库；不对真实库执行。
    bind = op.get_bind()
    insp = sa.inspect(bind)
    attempt_indexes = {i["name"] for i in insp.get_indexes("answer_attempts")}
    if "uq_attempt_exposure" in attempt_indexes:
        op.drop_index("uq_attempt_exposure", table_name="answer_attempts")
    exposure_indexes = {i["name"] for i in insp.get_indexes("exposures")}
    if "uq_exposure_first_unseen" in exposure_indexes:
        op.drop_index("uq_exposure_first_unseen", table_name="exposures")
    if "question_id" in [c["name"] for c in insp.get_columns("exposures")]:
        # 本机实测（SQLite 3.46.1 + SQLAlchemy 2.1.5）：0001 create_all 与本迁移 batch 增列均产出表级
        # FOREIGN KEY(question_id) 子句，原生 DROP COLUMN 会因残留外键定义而失败，故列删除统一经 batch 重建。
        with op.batch_alter_table("exposures") as batch:
            batch.drop_column("question_id")
