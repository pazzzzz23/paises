from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import MetaData, Table, URL, create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.engine import Engine

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
TABLE_NAME = "paises"
app = FastAPI(title="CRUD de países", description="Administración de la tabla paises")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Build the MySQL connection from environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return create_engine(database_url, pool_pre_ping=True)

    required = ("DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Configura estas variables en .env: {', '.join(missing)}")

    url = URL.create(
        drivername="mysql+pymysql",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.environ["DB_NAME"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_table() -> Table:
    table = Table(TABLE_NAME, MetaData(), autoload_with=get_engine())
    if len(table.primary_key.columns) != 1:
        raise RuntimeError("La tabla paises debe tener exactamente una clave primaria.")
    return table


def database_error(error: Exception) -> HTTPException:
    if isinstance(error, RuntimeError):
        detail = str(error)
    else:
        detail = "No fue posible acceder a la base de datos. Revisa la conexión y la estructura de la tabla."
    return HTTPException(status_code=503, detail=detail)


def convert_value(column: Any, value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        return value

    try:
        if python_type is bool:
            if isinstance(value, bool):
                return value
            normalized = str(value).strip().lower()
            if normalized in {"true", "1", "sí", "si", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
            raise ValueError("valor booleano no válido")
        if python_type is date and not isinstance(value, date):
            return date.fromisoformat(str(value))
        if python_type is datetime and not isinstance(value, datetime):
            return datetime.fromisoformat(str(value))
        if python_type is Decimal:
            return Decimal(str(value))
        return python_type(value)
    except (ValueError, TypeError, InvalidOperation) as error:
        raise HTTPException(
            status_code=422,
            detail=f"El valor de '{column.name}' no tiene un formato válido.",
        ) from error


def prepare_values(payload: dict[str, Any], table: Table, *, updating: bool = False) -> dict[str, Any]:
    primary_key = next(iter(table.primary_key.columns))
    columns = {column.name: column for column in table.columns}
    values: dict[str, Any] = {}

    for name, value in payload.items():
        column = columns.get(name)
        if column is None:
            raise HTTPException(status_code=422, detail=f"La columna '{name}' no existe en paises.")
        if updating and column is primary_key:
            raise HTTPException(status_code=422, detail="No se puede modificar la clave primaria.")
        if not updating and column is primary_key and (column.autoincrement is True or column.identity is not None):
            continue
        values[name] = convert_value(column, value)

    if updating and not values:
        raise HTTPException(status_code=422, detail="Indica al menos un campo para actualizar.")
    if not updating and not values:
        raise HTTPException(status_code=422, detail="Indica los datos del país que deseas crear.")
    return values


def parse_primary_key(table: Table, item_id: str) -> Any:
    primary_key = next(iter(table.primary_key.columns))
    return convert_value(primary_key, item_id)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/schema")
def schema() -> dict[str, Any]:
    try:
        table = get_table()
        return {
            "table": table.name,
            "columns": [
                {
                    "name": column.name,
                    "type": column.type.__class__.__name__.lower(),
                    "python_type": getattr(column.type, "python_type", str).__name__.lower(),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "autoincrement": column.autoincrement is True or column.identity is not None,
                }
                for column in table.columns
            ],
        }
    except (SQLAlchemyError, RuntimeError) as error:
        raise database_error(error) from error


@app.get("/api/paises")
def list_paises(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    try:
        table = get_table()
        primary_key = next(iter(table.primary_key.columns))
        with get_engine().connect() as connection:
            rows = connection.execute(
                select(table).order_by(primary_key).limit(limit).offset(offset)
            ).mappings().all()
        return jsonable_encoder([dict(row) for row in rows])
    except (SQLAlchemyError, RuntimeError) as error:
        raise database_error(error) from error


@app.post("/api/paises", status_code=201)
def create_pais(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        table = get_table()
        values = prepare_values(payload, table)
        with get_engine().begin() as connection:
            result = connection.execute(table.insert().values(**values))
            primary_key = next(iter(table.primary_key.columns))
            key_value = values.get(primary_key.name, result.inserted_primary_key[0])
            row = connection.execute(
                select(table).where(primary_key == key_value)
            ).mappings().one()
        return jsonable_encoder(dict(row))
    except HTTPException:
        raise
    except IntegrityError as error:
        raise HTTPException(status_code=400, detail="No se pudo crear el registro; revisa campos obligatorios y valores duplicados.") from error
    except (SQLAlchemyError, RuntimeError) as error:
        raise database_error(error) from error


@app.put("/api/paises/{item_id}")
def update_pais(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        table = get_table()
        primary_key = next(iter(table.primary_key.columns))
        key_value = parse_primary_key(table, item_id)
        values = prepare_values(payload, table, updating=True)
        with get_engine().begin() as connection:
            existing = connection.execute(
                select(primary_key).where(primary_key == key_value)
            ).first()
            if existing is None:
                raise HTTPException(status_code=404, detail="No se encontró el país solicitado.")
            connection.execute(table.update().where(primary_key == key_value).values(**values))
            row = connection.execute(
                select(table).where(primary_key == key_value)
            ).mappings().one()
        return jsonable_encoder(dict(row))
    except HTTPException:
        raise
    except IntegrityError as error:
        raise HTTPException(status_code=400, detail="No se pudo actualizar el registro; revisa campos obligatorios y valores duplicados.") from error
    except (SQLAlchemyError, RuntimeError) as error:
        raise database_error(error) from error


@app.delete("/api/paises/{item_id}", status_code=204)
def delete_pais(item_id: str) -> None:
    try:
        table = get_table()
        primary_key = next(iter(table.primary_key.columns))
        key_value = parse_primary_key(table, item_id)
        with get_engine().begin() as connection:
            result = connection.execute(table.delete().where(primary_key == key_value))
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="No se encontró el país solicitado.")
    except HTTPException:
        raise
    except IntegrityError as error:
        raise HTTPException(status_code=400, detail="No se pudo eliminar; el país puede estar relacionado con otros registros.") from error
    except (SQLAlchemyError, RuntimeError) as error:
        raise database_error(error) from error
