"""Emite el DDL PostgreSQL completo desde los modelos SQLAlchemy.

Validación sin base de datos: si los modelos tienen errores (tipos, FKs,
constraints), este script explota. Útil también para revisar el esquema.

Uso:  uv run python scripts/generate_ddl.py
"""

from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
import app.db.models  # noqa: F401  (registra todos los modelos)


def main() -> None:
    dialect = PGDialect()
    statements: list[str] = []

    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")

    print("-- DDL generado desde app/db/models (los tipos ENUM los crea Alembic)")
    print()
    print("\n\n".join(statements))
    print()
    print(f"-- {len(Base.metadata.sorted_tables)} tablas")


if __name__ == "__main__":
    main()
