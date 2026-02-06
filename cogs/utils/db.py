# -*- coding: utf-8 -*-
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger("ae_scripts_bot")

try:
    import mysql.connector
    from mysql.connector import Error
except ImportError:
    mysql = None
    Error = None

SYSTEM_TABLES = {
    "removebg": "removebg",
    "dedup": "dedup",
    "dedup_results": "dedup_results",
    "removebg_results": "removebg_results",
    "yt_download_mp4": "yt_download_mp4",
    "yt_download_mp4_results": "yt_download_mp4_results",
    "yt_download_mp3": "yt_download_mp3",
    "yt_download_mp3_results": "yt_download_mp3_results",
}

TABLE_SCHEMAS = {
    "removebg": """
        CREATE TABLE IF NOT EXISTS removebg (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "dedup": """
        CREATE TABLE IF NOT EXISTS dedup (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "dedup_results": """
        CREATE TABLE IF NOT EXISTS dedup_results (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "removebg_results": """
        CREATE TABLE IF NOT EXISTS removebg_results (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "yt_download_mp4": """
        CREATE TABLE IF NOT EXISTS yt_download_mp4 (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "yt_download_mp4_results": """
        CREATE TABLE IF NOT EXISTS yt_download_mp4_results (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "yt_download_mp3": """
        CREATE TABLE IF NOT EXISTS yt_download_mp3 (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "yt_download_mp3_results": """
        CREATE TABLE IF NOT EXISTS yt_download_mp3_results (
            server_id VARCHAR(255) PRIMARY KEY,
            channel_id VARCHAR(255) NOT NULL
        )
    """,
    "media_queue": """
        CREATE TABLE IF NOT EXISTS media_queue (
            id INT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            author_id BIGINT NOT NULL,
            message_id BIGINT NULL,
            `system` VARCHAR(32) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            error_message TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_system_status (`system`, status),
            INDEX idx_created (created_at)
        )
    """,
}

def create_db_connection():
    if mysql is None:
        logger.warning("mysql-connector-python not installed. pip install mysql-connector-python")
        return None
    host = os.environ.get("MYSQL_HOST", "").strip()
    user = os.environ.get("MYSQL_USER", "").strip()
    password = os.environ.get("MYSQL_PASSWORD", "").strip()
    database = os.environ.get("MYSQL_DATABASE", "").strip()
    if not host or not user or not database:
        logger.warning(
            "MySQL env vars missing. Set MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE (and MYSQL_PASSWORD) in .env"
        )
        return None
    try:
        connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
        )
        if connection.is_connected():
            return connection
        return None
    except Error as e:
        logger.warning("MySQL connection failed: %s", e)
        return None

def create_table(connection, table_name, schema):
    if connection is None or Error is None:
        return
    try:
        cursor = connection.cursor()
        cursor.execute(schema)
        connection.commit()
        cursor.close()
    except Error as e:
        logger.warning("Create table %s error: %s", table_name, e)

def initialize_database():
    connection = create_db_connection()
    if connection:
        for table_name, schema in TABLE_SCHEMAS.items():
            create_table(connection, table_name, schema)
        return connection
    return None

def enqueue_media(
    connection,
    guild_id: int,
    channel_id: int,
    author_id: int,
    message_id: Optional[int],
    system: str,
    file_path: str,
) -> Optional[int]:
    if connection is None or system not in ("removebg", "dedup", "yt_download_mp4", "yt_download_mp3"):
        return None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO media_queue (guild_id, channel_id, author_id, message_id, `system`, file_path, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'pending')",
            (guild_id, channel_id, author_id, message_id, system, file_path),
        )
        connection.commit()
        job_id = cursor.lastrowid
        cursor.close()
        return job_id
    except Error as e:
        logger.warning("enqueue_media error: %s", e)
        return None

def count_pending(connection, system: str) -> int:
    if connection is None or system not in ("removebg", "dedup", "yt_download_mp4", "yt_download_mp3"):
        return 0
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM media_queue WHERE `system` = %s AND status = 'pending'",
            (system,),
        )
        row = cursor.fetchone()
        cursor.close()
        return int(row[0]) if row else 0
    except Error as e:
        logger.warning("count_pending error: %s", e)
        return 0

def get_next_pending(connection, system: str) -> Optional[Tuple[int, int, int, int, Optional[int], str]]:
    if connection is None or system not in ("removebg", "dedup", "yt_download_mp4", "yt_download_mp3"):
        return None
    try:
        cursor = connection.cursor()
        connection.start_transaction()
        cursor.execute(
            "SELECT id, guild_id, channel_id, author_id, message_id, file_path FROM media_queue "
            "WHERE `system` = %s AND status = 'pending' ORDER BY id ASC LIMIT 1 FOR UPDATE",
            (system,),
        )
        row = cursor.fetchone()
        if not row:
            connection.rollback()
            cursor.close()
            return None
        job_id, guild_id, channel_id, author_id, message_id, file_path = row
        cursor.execute("UPDATE media_queue SET status = 'processing' WHERE id = %s", (job_id,))
        connection.commit()
        cursor.close()
        return (job_id, int(guild_id), int(channel_id), int(author_id), int(message_id) if message_id else None, file_path)
    except Error as e:
        logger.warning("get_next_pending error: %s", e)
        try:
            connection.rollback()
        except Exception:
            pass
        return None

def set_queue_job_completed(connection, job_id: int) -> None:
    if connection is None:
        return
    try:
        cursor = connection.cursor()
        cursor.execute("UPDATE media_queue SET status = 'completed' WHERE id = %s", (job_id,))
        connection.commit()
        cursor.close()
    except Error as e:
        logger.warning("set_queue_job_completed error: %s", e)

def set_queue_job_failed(connection, job_id: int, error_message: Optional[str] = None) -> None:
    if connection is None:
        return
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE media_queue SET status = 'failed', error_message = %s WHERE id = %s",
            (error_message[:2000] if error_message else None, job_id),
        )
        connection.commit()
        cursor.close()
    except Error as e:
        logger.warning("set_queue_job_failed error: %s", e)

def load_channels_from_db(connection):
    if connection is None:
        return {}
    result = {}
    try:
        cursor = connection.cursor()
        for system_key, table in SYSTEM_TABLES.items():
            cursor.execute("SELECT server_id, channel_id FROM `%s`" % table)
            for row in cursor.fetchall():
                server_id = str(row[0])
                channel_id = int(row[1]) if row[1] else None
                if server_id not in result:
                    result[server_id] = {}
                if channel_id:
                    result[server_id][system_key] = channel_id
        cursor.close()
    except Error as e:
        logger.warning("load_channels_from_db error: %s", e)
    return result

def set_system_channel_db(connection, guild_id: int, system: str, channel_id: Optional[int]):
    if connection is None or system not in SYSTEM_TABLES:
        return
    table = SYSTEM_TABLES[system]
    server_id = str(guild_id)
    try:
        cursor = connection.cursor()
        if channel_id is None:
            cursor.execute("DELETE FROM `%s` WHERE server_id = %%s" % table, (server_id,))
        else:
            cursor.execute(
                "INSERT INTO `%s` (server_id, channel_id) VALUES (%%s, %%s) ON DUPLICATE KEY UPDATE channel_id = %%s"
                % table,
                (server_id, str(channel_id), str(channel_id)),
            )
        connection.commit()
        cursor.close()
    except Error as e:
        logger.warning("set_system_channel_db error: %s", e)

def get_system_channel_db(connection, guild_id: int, system: str) -> Optional[int]:
    if connection is None or system not in SYSTEM_TABLES:
        return None
    table = SYSTEM_TABLES[system]
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT channel_id FROM `%s` WHERE server_id = %%s" % table, (str(guild_id),))
        row = cursor.fetchone()
        cursor.close()
        if row and row[0]:
            return int(row[0])
    except Error as e:
        logger.warning("get_system_channel_db error: %s", e)
    return None
