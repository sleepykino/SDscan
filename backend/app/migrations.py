"""轻量、幂等的数据库迁移（P5）。

项目不引入 Alembic：本模块是全项目**唯一允许执行裸 DDL** 的地方，业务代码仍只走 ORM。
- 对老库的 ``domain_list`` 用 PRAGMA table_info 检测后 ALTER ADD COLUMN 补列；
- 新表由 ``Base.metadata.create_all`` 创建；
- 历史 T2 行做一次可重复执行的回填。
``migrate()`` 连续执行多次结果必须一致。
"""
from __future__ import annotations

from sqlalchemy import text

from .database import engine

# domain_list 需补的列：列名 -> 列定义（SQLite ALTER 语法）
_DOMAIN_LIST_COLUMNS: dict[str, str] = {
    "layer": "TEXT NOT NULL DEFAULT 'apex'",
    "parent_domain": "TEXT NOT NULL DEFAULT ''",
    "provider": "TEXT NOT NULL DEFAULT ''",
    "confidence": "TEXT NOT NULL DEFAULT 'low'",
    "resolved_ip": "TEXT NOT NULL DEFAULT ''",
    "alive": "BOOLEAN",
    "updated_at": "TIMESTAMP",
}


def _existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _migrate_domain_list(conn) -> None:
    if not _existing_columns(conn, "domain_list"):
        return  # 全新库，create_all 会直接建出含新列的表
    present = _existing_columns(conn, "domain_list")
    for column, ddl in _DOMAIN_LIST_COLUMNS.items():
        if column not in present:
            conn.execute(
                text(f"ALTER TABLE domain_list ADD COLUMN {column} {ddl}")
            )
    # 历史 T2 数据回填（幂等：仅更新仍是默认值的旧行）
    conn.execute(
        text(
            "UPDATE domain_list SET layer = 'apex', provider = 'se_general', "
            "confidence = 'low' WHERE layer = 'apex' AND provider = '' "
            "AND confidence = 'low'"
        )
    )


def migrate() -> None:
    """执行全部轻量迁移；在 init_db 的 create_all 之前调用。"""
    with engine.begin() as conn:
        _migrate_domain_list(conn)
