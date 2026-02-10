# libs/oracle_keywords.py
from robot.api.deco import keyword
from robot.libraries.BuiltIn import BuiltIn
import oracledb, traceback, os, pathlib

_CONN = None  # глобальная ссылка на соединение

@keyword("Open Oracle Connection")
def open_oracle_connection():
    """Толстый режим. Все параметры берутся строго из *** Variables ***."""

    global _CONN
    if _CONN:
        return

    b = BuiltIn()

    ic_dir  = r"C:\svn\Ride\libs\instantclient23.8.0.25.04\instantclient_23_8"          # путь к instantclient_23_8
    user    = "system"         # system
    pwd     = "psystemp"        # pass
    host    = "192.168.84.200"        # 192.168.84.200
    service = "central"          # central
    port    = 1521                                       # фиксированный порт
    print(repr(host), repr(service))
    # проверяем наличие oci.dll
    ic_path = pathlib.Path(ic_dir).expanduser().resolve()
    if not ic_path.joinpath("oci.dll").exists():
        raise RuntimeError(f"В {ic_path} нет oci.dll — проверь ${IC_DIR}")

    # включаем Thick-режим
    oracledb.init_oracle_client(lib_dir=str(ic_path))

    # ─ подключаемся по SERVICE_NAME (без резервов) ─
    dsn = f"//{host}:{port}/{service}"
    _CONN = oracledb.connect(user=user, password=pwd, dsn=dsn)

    print(_CONN)

@keyword("Oracle Query")
def oracle_query(sql, *params):
    if _CONN is None:
        raise RuntimeError("Сначала вызови Open Oracle Connection")
    with _CONN.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()

@keyword("Close Oracle Connection")
def close_oracle_connection():
    global _CONN
    if _CONN:
        _CONN.close()
        _CONN = None
