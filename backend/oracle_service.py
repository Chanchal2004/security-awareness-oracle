import asyncio
import json
import logging
import os
from typing import Any, Dict

import oracledb

logger = logging.getLogger("talbros.oracle")


def _configured() -> bool:
    return all(os.getenv(k) for k in ("ORACLE_USERNAME", "ORACLE_PASSWORD", "ORACLE_HOST"))


def _dsn():
    host = os.getenv("ORACLE_HOST")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE_NAME")
    sid = os.getenv("ORACLE_SID")
    if service:
        return oracledb.makedsn(host, port, service_name=service)
    if sid:
        return oracledb.makedsn(host, port, sid=sid)
    raise RuntimeError("Set ORACLE_SERVICE_NAME or ORACLE_SID")


def _connect():
    if not _configured():
        raise RuntimeError("Oracle is not configured")
    return oracledb.connect(
        user=os.environ["ORACLE_USERNAME"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn=_dsn(),
    )


def _ensure_table_sync() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute("""
                CREATE TABLE AWARENESS_FORM_SUBMISSIONS (
                    ID VARCHAR2(100) PRIMARY KEY,
                    SIMULATION_ID VARCHAR2(100),
                    RECIPIENT_ID VARCHAR2(100),
                    RECIPIENT_EMAIL VARCHAR2(320),
                    DEPARTMENT VARCHAR2(200),
                    FORM_ID VARCHAR2(100),
                    RESPONSES_JSON CLOB,
                    SUBMITTED_AT VARCHAR2(64),
                    CREATED_AT TIMESTAMP DEFAULT SYSTIMESTAMP
                )
            """)
            conn.commit()
            logger.info("Created Oracle table AWARENESS_FORM_SUBMISSIONS")
        except oracledb.DatabaseError as exc:
            # ORA-00955 = name already used by an existing object.
            code = getattr(exc.args[0], "code", None) if exc.args else None
            if code != 955:
                raise
    finally:
        conn.close()


async def init_oracle() -> bool:
    if not _configured():
        logger.info("Oracle integration disabled: ORACLE_* variables are not configured")
        return False
    try:
        await asyncio.to_thread(_ensure_table_sync)
        logger.info("Oracle connection/table check successful")
        return True
    except Exception:
        logger.exception("Oracle initialization failed; MongoDB remains the primary app store")
        return False


def _save_submission_sync(data: Dict[str, Any]) -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE INTO AWARENESS_FORM_SUBMISSIONS t
            USING (
                SELECT :id AS ID FROM dual
            ) s
            ON (t.ID = s.ID)
            WHEN MATCHED THEN UPDATE SET
                SIMULATION_ID=:simulation_id,
                RECIPIENT_ID=:recipient_id,
                RECIPIENT_EMAIL=:recipient_email,
                DEPARTMENT=:department,
                FORM_ID=:form_id,
                RESPONSES_JSON=:responses_json,
                SUBMITTED_AT=:submitted_at
            WHEN NOT MATCHED THEN INSERT
                (ID, SIMULATION_ID, RECIPIENT_ID, RECIPIENT_EMAIL, DEPARTMENT,
                 FORM_ID, RESPONSES_JSON, SUBMITTED_AT)
            VALUES
                (:id, :simulation_id, :recipient_id, :recipient_email, :department,
                 :form_id, :responses_json, :submitted_at)
            """,
            id=data["id"],
            simulation_id=data.get("simulation_id", ""),
            recipient_id=data.get("recipient_id", ""),
            recipient_email=data.get("recipient_email", ""),
            department=data.get("department", ""),
            form_id=data.get("form_id") or "",
            responses_json=json.dumps(data.get("responses", {}), ensure_ascii=False),
            submitted_at=data.get("timestamp", ""),
        )
        conn.commit()
    finally:
        conn.close()


async def save_form_submission(data: Dict[str, Any]) -> bool:
    if not _configured():
        return False
    try:
        await asyncio.to_thread(_save_submission_sync, data)
        return True
    except Exception:
        logger.exception("Could not save form submission to Oracle")
        return False
