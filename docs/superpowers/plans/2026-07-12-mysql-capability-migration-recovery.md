# MySQL Capability Migration Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair Alembic's MySQL transaction handoff and safely recover the existing `20260710_model_capability_defaults` half-migration so text and vision capability bindings become durable.

**Architecture:** Finish the MySQL compatibility preflight transaction before Alembic creates its `MigrationContext`, then make the existing capability-default revision recognize and validate an already-created table. Preserve existing bindings, backfill only unique candidates, and separate code verification from authorized production mutation.

**Tech Stack:** Python 3.10+, SQLAlchemy 2.x, Alembic, PyMySQL, SQLite/MySQL-compatible migrations, FastAPI, pytest, Railway CLI.

---

## Execution Constraints

- Start implementation in an isolated, intent-named worktree such as `fix/mysql-capability-migration-recovery`; report that it is not root `master`.
- The root workspace is currently dirty. Do not touch or stage the unrelated source-image design and plan files.
- Do not commit unless the user explicitly authorizes commits. Commit commands below are checkpoints to run only after that authorization.
- Do not merge into root `master`, push, redeploy, restart, or mutate production data without separate explicit authorization for each operational stage.
- Do not run a real text/image Provider request during code verification.
- Do not run `alembic downgrade`, delete `model_capability_defaults`, or stamp production past the failed revision.
- Design reference: `docs/superpowers/specs/2026-07-12-mysql-capability-migration-recovery-design.md`.

## File Map

- `backend/app/core/alembic_compat.py`: prepare the MySQL Alembic connection and finish preflight autobegin before Alembic configures migration transactions.
- `backend/alembic/env.py`: call the prepared compatibility entrypoint instead of the low-level version-table helper.
- `backend/alembic/versions/20260710_model_capability_defaults.py`: validate/reuse an existing partial table and backfill bindings idempotently.
- `tests/backend/test_mysql_migration_compatibility.py`: verify MySQL preflight commits and non-MySQL behavior remains unchanged.
- `tests/backend/test_model_capability_migration_recovery.py`: exercise fresh and half-applied upgrades through Alembic against temporary databases.
- `docs/superpowers/specs/2026-07-12-mysql-capability-migration-recovery-design.md`: approved design; update status/evidence only during closeout.

### Task 1: Restore Alembic Transaction Ownership

**Files:**
- Modify: `tests/backend/test_mysql_migration_compatibility.py`
- Modify: `backend/app/core/alembic_compat.py`
- Modify: `backend/alembic/env.py`

- [ ] **Step 1: Extend the fake connection for transaction assertions**

Update `_FakeConnection` in `tests/backend/test_mysql_migration_compatibility.py`:

```python
class _FakeConnection:
    def __init__(self, *, dialect=None, in_transaction: bool = False) -> None:
        self.dialect = dialect or mysql.dialect()
        self.statements: list[str] = []
        self._in_transaction = in_transaction
        self.commit_count = 0

    def execute(self, statement) -> None:
        self.statements.append(str(statement))

    def in_transaction(self) -> bool:
        return self._in_transaction

    def commit(self) -> None:
        self.commit_count += 1
        self._in_transaction = False
```

- [ ] **Step 2: Write failing MySQL and SQLite preflight tests**

Add these tests below the existing version-table compatibility tests:

```python
def test_prepare_mysql_alembic_connection_commits_preflight_autobegin(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection(in_transaction=True)
    monkeypatch.setattr(
        alembic_compat,
        "inspect",
        lambda _connection: _FakeInspector(
            [{"name": "version_num", "type": sa.String(length=128)}]
        ),
    )

    alembic_compat.prepare_mysql_alembic_connection(connection)

    assert connection.statements == []
    assert connection.commit_count == 1
    assert connection.in_transaction() is False


def test_prepare_mysql_alembic_connection_does_not_commit_sqlite(monkeypatch):
    from backend.app.core import alembic_compat

    connection = _FakeConnection(
        dialect=sa.create_engine("sqlite:///:memory:").dialect,
        in_transaction=True,
    )
    monkeypatch.setattr(
        alembic_compat,
        "inspect",
        lambda _connection: _FakeInspector(),
    )

    alembic_compat.prepare_mysql_alembic_connection(connection)

    assert connection.commit_count == 0
```

- [ ] **Step 3: Run the new tests and confirm RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_mysql_migration_compatibility.py -k "prepare_mysql_alembic_connection" -q
```

Expected: FAIL with `AttributeError` because `prepare_mysql_alembic_connection` does not exist.

- [ ] **Step 4: Implement the connection preparation helper**

Add to `backend/app/core/alembic_compat.py` after `ensure_mysql_alembic_version_table`:

```python
def prepare_mysql_alembic_connection(connection) -> None:
    """Finish MySQL compatibility preflight before Alembic owns transactions."""
    ensure_mysql_alembic_version_table(connection)
    if (
        connection.dialect.name in {"mysql", "mariadb"}
        and connection.in_transaction()
    ):
        connection.commit()
```

This helper owns only the dedicated Alembic connection. Do not call it from application Session code.

- [ ] **Step 5: Route Alembic env setup through the helper**

In `backend/alembic/env.py`, replace the import:

```python
from backend.app.core.alembic_compat import ensure_mysql_alembic_version_table
```

with:

```python
from backend.app.core.alembic_compat import prepare_mysql_alembic_connection
```

Then replace:

```python
ensure_mysql_alembic_version_table(connection)
```

with:

```python
prepare_mysql_alembic_connection(connection)
```

Keep this call before `context.configure(...)` so `MigrationContext._in_external_transaction` is false.

- [ ] **Step 6: Run the focused compatibility suite and confirm GREEN**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_mysql_migration_compatibility.py -q
```

Expected: all tests PASS, including existing version-column creation and widening cases.

- [ ] **Step 7: Review the scoped diff**

Run:

```powershell
git diff -- backend/app/core/alembic_compat.py backend/alembic/env.py tests/backend/test_mysql_migration_compatibility.py
git diff --check -- backend/app/core/alembic_compat.py backend/alembic/env.py tests/backend/test_mysql_migration_compatibility.py
```

Expected: only the connection-preparation helper, env call-site, and focused tests changed; `git diff --check` prints nothing.

- [ ] **Step 8: Commit only after explicit commit authorization**

```powershell
git add -- backend/app/core/alembic_compat.py backend/alembic/env.py tests/backend/test_mysql_migration_compatibility.py
git commit -m "fix: restore mysql migration transactions"
```

### Task 2: Make the Capability Revision Recoverable and Idempotent

**Files:**
- Create: `tests/backend/test_model_capability_migration_recovery.py`
- Modify: `backend/alembic/versions/20260710_model_capability_defaults.py`

- [ ] **Step 1: Create Alembic integration-test helpers**

Create `tests/backend/test_model_capability_migration_recovery.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from backend.app.models import ModelCapabilityDefault, ModelConfig, User


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "20260708_usage_ledger_followup_unique"
TARGET_REVISION = "20260710_model_capability_defaults"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "backend" / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _seed_candidates(engine) -> tuple[int, int, int]:
    with Session(engine) as session:
        admin = User(
            username="migration-admin",
            password_hash="test",
            role="admin",
            status="active",
        )
        session.add(admin)
        session.flush()

        text_config = ModelConfig(
            user_id=admin.id,
            name="SEED2-MINI Text",
            model_type="text",
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.example.test/api/v3",
            encrypted_api_key="encrypted-text-key",
            is_default=True,
        )
        vision_config = ModelConfig(
            user_id=admin.id,
            name="SEED2-MINI Vision",
            model_type="image",
            provider="volcengine-ark",
            model_name="doubao-seed-2-0-mini-260428",
            base_url="https://ark.example.test/api/v3",
            encrypted_api_key="encrypted-vision-key",
            is_default=True,
        )
        image_a = ModelConfig(
            user_id=admin.id,
            name="Image A",
            model_type="image",
            provider="openai-compatible",
            model_name="image-a",
            base_url="https://images-a.example.test/v1",
            encrypted_api_key="encrypted-image-a",
            is_default=False,
        )
        image_b = ModelConfig(
            user_id=admin.id,
            name="Image B",
            model_type="image",
            provider="runninghub-ai-app",
            model_name="runninghub-image-g",
            base_url="https://images-b.example.test",
            encrypted_api_key="encrypted-image-b",
            is_default=False,
        )
        session.add_all([text_config, vision_config, image_a, image_b])
        session.commit()
        return admin.id, text_config.id, vision_config.id
```

- [ ] **Step 2: Write the failing half-migration recovery test**

Append:

```python
@pytest.mark.parametrize("existing_text_binding", [False, True])
def test_upgrade_recovers_existing_capability_table(
    tmp_path,
    monkeypatch,
    existing_text_binding,
):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_url = (
        f"sqlite:///{(tmp_path / f'partial-{int(existing_text_binding)}.db').as_posix()}"
    )
    config = _alembic_config(database_url)
    command.upgrade(config, PREVIOUS_REVISION)

    engine = sa.create_engine(database_url)
    admin_id, text_config_id, vision_config_id = _seed_candidates(engine)
    ModelCapabilityDefault.__table__.create(engine)

    if existing_text_binding:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO model_capability_defaults "
                    "(capability, model_config_id, updated_by_user_id, created_at, updated_at) "
                    "VALUES ('text', :model_config_id, :admin_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"model_config_id": text_config_id, "admin_id": admin_id},
            )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        version = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        bindings = dict(
            connection.execute(
                sa.text(
                    "SELECT capability, model_config_id "
                    "FROM model_capability_defaults ORDER BY capability"
                )
            ).all()
        )

    assert version == TARGET_REVISION
    assert bindings == {"text": text_config_id, "vision": vision_config_id}
    engine.dispose()
```

The `False` case reproduces the production empty table. The `True` case proves that a partially written `text` binding is preserved rather than duplicated or overwritten.

- [ ] **Step 3: Write the failing fresh-upgrade test**

Append:

```python
def test_upgrade_creates_capability_table_from_previous_revision(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    config = _alembic_config(database_url)
    command.upgrade(config, PREVIOUS_REVISION)

    engine = sa.create_engine(database_url)
    _, text_config_id, vision_config_id = _seed_candidates(engine)

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    with engine.connect() as connection:
        bindings = dict(
            connection.execute(
                sa.text(
                    "SELECT capability, model_config_id "
                    "FROM model_capability_defaults ORDER BY capability"
                )
            ).all()
        )

    assert "model_capability_defaults" in inspector.get_table_names()
    assert bindings == {"text": text_config_id, "vision": vision_config_id}
    engine.dispose()
```

- [ ] **Step 4: Write the failing incompatible-table test**

Append:

```python
def test_upgrade_rejects_incompatible_existing_capability_table(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_url = f"sqlite:///{(tmp_path / 'invalid.db').as_posix()}"
    config = _alembic_config(database_url)
    command.upgrade(config, PREVIOUS_REVISION)

    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE model_capability_defaults ("
                "id INTEGER PRIMARY KEY, capability VARCHAR(64) NOT NULL)"
            )
        )

    with pytest.raises(RuntimeError, match="incompatible model_capability_defaults"):
        command.upgrade(config, "head")

    engine.dispose()
```

- [ ] **Step 5: Run the new recovery tests and confirm RED**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_model_capability_migration_recovery.py -q
```

Expected: the fresh-upgrade test may pass, while the partial and incompatible-table tests fail because the current migration unconditionally creates the table.

- [ ] **Step 6: Add table constants and validation helpers**

In `backend/alembic/versions/20260710_model_capability_defaults.py`, add after `CAPABILITIES`:

```python
TABLE_NAME = "model_capability_defaults"
CAPABILITY_INDEX = "ix_model_capability_defaults_model_config_id"
REQUIRED_COLUMNS = {
    "id",
    "capability",
    "model_config_id",
    "updated_by_user_id",
    "created_at",
    "updated_at",
}
REQUIRED_FOREIGN_KEYS = {
    (("model_config_id",), "model_configs", ("id",)),
    (("updated_by_user_id",), "users", ("id",)),
}


def _validate_existing_table(bind) -> None:
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    missing_columns = REQUIRED_COLUMNS - columns

    unique_sets = {
        tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(TABLE_NAME)
    }
    foreign_keys = {
        (
            tuple(item.get("constrained_columns") or ()),
            str(item.get("referred_table") or ""),
            tuple(item.get("referred_columns") or ()),
        )
        for item in inspector.get_foreign_keys(TABLE_NAME)
    }

    problems: list[str] = []
    if missing_columns:
        problems.append(f"missing columns: {sorted(missing_columns)}")
    if ("capability",) not in unique_sets:
        problems.append("missing unique capability constraint")
    missing_foreign_keys = REQUIRED_FOREIGN_KEYS - foreign_keys
    if missing_foreign_keys:
        problems.append(f"missing foreign keys: {sorted(missing_foreign_keys)}")
    if problems:
        raise RuntimeError(
            f"incompatible {TABLE_NAME}: " + "; ".join(problems)
        )

    index_names = {
        str(item.get("name") or "")
        for item in inspector.get_indexes(TABLE_NAME)
    }
    if CAPABILITY_INDEX not in index_names:
        op.create_index(
            CAPABILITY_INDEX,
            TABLE_NAME,
            ["model_config_id"],
            unique=False,
        )
```

- [ ] **Step 7: Extract create-or-validate behavior**

Move the current `op.create_table(...)` and `op.create_index(...)` statements into:

```python
def _ensure_capability_table(bind) -> None:
    inspector = sa.inspect(bind)
    if TABLE_NAME in inspector.get_table_names():
        _validate_existing_table(bind)
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("model_config_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["model_configs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "capability",
            name="uq_model_capability_defaults_capability",
        ),
    )
    op.create_index(
        CAPABILITY_INDEX,
        TABLE_NAME,
        ["model_config_id"],
        unique=False,
    )
```

- [ ] **Step 8: Preserve existing bindings during backfill**

Add:

```python
def _has_binding(bind, capability: str) -> bool:
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM model_capability_defaults "
                "WHERE capability = :capability LIMIT 1"
            ),
            {"capability": capability},
        ).first()
        is not None
    )
```

Rewrite `upgrade()` to obtain the bind first, ensure the table, and skip existing bindings:

```python
def upgrade() -> None:
    bind = op.get_bind()
    _ensure_capability_table(bind)

    for capability, (model_type, providers, require_default) in CAPABILITIES.items():
        if _has_binding(bind, capability):
            continue
        candidates = _candidate_rows(
            bind,
            model_type=model_type,
            providers=providers,
            require_default=require_default,
        )
        if len(candidates) != 1:
            continue
        candidate = candidates[0]
        bind.execute(
            sa.text(
                "INSERT INTO model_capability_defaults "
                "(capability, model_config_id, updated_by_user_id, created_at, updated_at) "
                "VALUES (:capability, :model_config_id, :updated_by_user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "capability": capability,
                "model_config_id": candidate["model_config_id"],
                "updated_by_user_id": candidate["updated_by_user_id"],
            },
        )
```

Keep the existing conservative candidate query, including non-empty model name, base URL, and encrypted key checks.

- [ ] **Step 9: Run recovery and migration compatibility tests**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_model_capability_migration_recovery.py tests/backend/test_mysql_migration_compatibility.py tests/backend/test_model_config_service.py -q
```

Expected: all tests PASS. The partial database reaches the head revision, preserves `text`, inserts `vision`, and leaves ambiguous `image_generation` unbound.

- [ ] **Step 10: Verify the single Alembic head**

Run:

```powershell
py -X utf8 -m alembic -c backend/alembic.ini heads
py -X utf8 -m pytest tests/backend/test_wechat_official_models.py::test_wechat_official_alembic_revision_is_single_head -q
```

Expected: exactly `20260710_model_capability_defaults (head)` and the head test PASS.

- [ ] **Step 11: Review and optionally commit the migration recovery slice**

Run:

```powershell
git diff --check -- backend/alembic/versions/20260710_model_capability_defaults.py tests/backend/test_model_capability_migration_recovery.py
git diff -- backend/alembic/versions/20260710_model_capability_defaults.py tests/backend/test_model_capability_migration_recovery.py
```

After explicit commit authorization only:

```powershell
git add -- backend/alembic/versions/20260710_model_capability_defaults.py tests/backend/test_model_capability_migration_recovery.py
git commit -m "fix: recover partial capability migration"
```

### Task 3: Run Backend Verification and Prepare the Branch Handoff

**Files:**
- Verify: `backend/app/core/alembic_compat.py`
- Verify: `backend/alembic/env.py`
- Verify: `backend/alembic/versions/20260710_model_capability_defaults.py`
- Verify: `tests/backend/test_mysql_migration_compatibility.py`
- Verify: `tests/backend/test_model_capability_migration_recovery.py`
- Verify: `tests/backend/test_model_config_service.py`

- [ ] **Step 1: Compile changed Python modules**

Run:

```powershell
py -X utf8 -m compileall backend/app/core/alembic_compat.py backend/alembic/env.py backend/alembic/versions/20260710_model_capability_defaults.py tests/backend/test_mysql_migration_compatibility.py tests/backend/test_model_capability_migration_recovery.py
```

Expected: exit code 0 with no syntax errors.

- [ ] **Step 2: Run the scoped regression suite**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_mysql_migration_compatibility.py tests/backend/test_model_capability_migration_recovery.py tests/backend/test_model_config_service.py tests/backend/test_runtime_diagnostics.py -q
```

Expected: all tests PASS.

- [ ] **Step 3: Run the full backend suite**

Run:

```powershell
py -X utf8 -m pytest tests/backend -q
```

Expected: all tests PASS; existing deprecation warnings may remain but no new failures are accepted.

- [ ] **Step 4: Verify scope hygiene**

Run:

```powershell
git status --short --branch
git diff --check
git diff --stat
```

Expected: only the backend migration recovery files and this task's approved docs differ in the implementation worktree. Unrelated root-workspace documents remain untouched.

- [ ] **Step 5: Report branch-local completion before integration**

Report:

- worktree path and branch;
- test commands and exact pass counts;
- branch commit SHA if commits were authorized;
- explicit statement that root `master`, Railway production, and production MySQL are unchanged.

Do not merge, push, deploy, or mutate production during this step.

### Task 4: Integrate and Recover Production Only After Explicit Authorization

**Files/Systems:**
- Integrate: root `E:\小红书` `master`
- Deploy: Railway service `Auto-Operations`
- Read/modify after authorization: Railway production MySQL

- [ ] **Step 1: Recheck root integration state**

Run from root `E:\小红书`:

```powershell
git branch --show-current
git status --short --branch
git rev-parse HEAD
git rev-parse origin/master
```

Expected: branch is `master`; report all unrelated changes before any merge.

- [ ] **Step 2: Ask for merge authorization**

Provide the verified feature-branch SHA and ask whether to merge it into root `master` using a merge commit. Do not infer authorization from design approval.

- [ ] **Step 3: Merge only after approval**

```powershell
git merge --no-ff fix/mysql-capability-migration-recovery -m "merge: recover mysql capability migration"
```

Expected: merge succeeds without touching unrelated files. If the implementation branch name differs from the required plan name, stop and reconcile the branch name before merging.

- [ ] **Step 4: Verify merged master before push**

Run:

```powershell
py -X utf8 -m pytest tests/backend/test_mysql_migration_compatibility.py tests/backend/test_model_capability_migration_recovery.py tests/backend/test_model_config_service.py -q
git diff --check origin/master...master
git log -3 --oneline --decorate
```

Expected: tests PASS and the merge commit is visible on local `master`; production remains unchanged.

- [ ] **Step 5: Ask separately for push and deployment authorization**

State that pushing `master` triggers Railway deployment and the startup migration will mutate production MySQL. Obtain explicit authorization before continuing.

- [ ] **Step 6: Create a production database backup**

Before push, create a Railway MySQL backup/snapshot and record its timestamp. Also export these tables as a narrow recovery artifact without printing credentials:

- `alembic_version`
- `model_capability_defaults`
- `model_configs`
- `users`

The artifact must include `SHOW CREATE TABLE` for the first two tables and row data for all four. Verify the backup exists before deployment; if backup creation or verification fails, stop.

- [ ] **Step 7: Capture the pre-deploy state**

Use a read-only Railway MySQL query and record:

```sql
SELECT version_num FROM alembic_version;
SELECT COUNT(*) AS binding_count FROM model_capability_defaults;
SHOW CREATE TABLE model_capability_defaults;
SELECT id, user_id, name, model_type, provider, model_name, is_default
FROM model_configs ORDER BY id;
SELECT id, role, status FROM users WHERE role = 'admin' ORDER BY id;
```

Expected current state: revision `20260708_usage_ledger_followup_unique`, zero bindings, and valid admin configs `#7`/`#8`. If live state differs, stop and re-evaluate instead of applying stale assumptions.

- [ ] **Step 8: Push the authorized master**

```powershell
git push origin master
```

Expected: push succeeds and Railway starts a deployment for the exact pushed SHA.

- [ ] **Step 9: Monitor startup migration and health**

Run:

```powershell
railway status
railway logs --latest --since 10m --json --lines 500
curl.exe -sS -D - https://aitavix.com/api/health
curl.exe -sS -D - https://aitavix.com/api/version
```

Expected: deployment is online; startup has no migration traceback; health/version return 200 and the deployed commit matches pushed `master`.

- [ ] **Step 10: Verify recovered revision and bindings read-only**

Run read-only SQL:

```sql
SELECT version_num FROM alembic_version;
SELECT capability, model_config_id, updated_by_user_id
FROM model_capability_defaults ORDER BY capability;
```

Expected:

```text
20260710_model_capability_defaults
text   -> 7
vision -> 8
```

`image_generation` remains absent until separately authorized and explicitly selected.

- [ ] **Step 11: Ask for explicit image-generation binding authorization**

Revalidate config `#5` is still owned by an active admin, supports `image_generation`, and has non-empty model/base URL/encrypted key. After authorization, use the existing admin API rather than direct SQL:

```http
PUT /api/model-configs/capability-defaults/image_generation
Content-Type: application/json

{"model_config_id": 5}
```

Expected: response status 200 with `capability=image_generation`, `status=configured`, and model config `id=5`.

- [ ] **Step 12: Verify no unapproved Provider or quota activity**

Before any real model smoke test, query the latest `tasks` and `usage_ledgers` rows. Expected: deployment and binding recovery created no AI tasks, reservations, commits, refunds, or Provider calls.

- [ ] **Step 13: Ask for one real rewrite smoke-test authorization**

Explain that the test calls the configured text Provider and consumes the normal rewrite quota. If approved, perform exactly one rewrite against a designated test draft, then verify:

- HTTP 200;
- one completed `ai_rewrite` task;
- one reservation and one commit ledger operation;
- no refund or duplicate request;
- no real XHS publish action.

- [ ] **Step 14: Close out production truthfully**

Report:

- feature branch and implementation commits;
- root `master` merge SHA;
- pushed/deployed SHA;
- production Alembic revision;
- final `text`, `vision`, and `image_generation` bindings;
- whether a real rewrite was authorized and run;
- backup identifier and whether rollback was needed.
