"""
Módulo para almacenar historial de análisis en SQLite.
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
from backend.config import settings
from typing import Optional


def _get_db_path() -> str:
    """Obtiene la ruta de la base de datos y crea el directorio si no existe."""
    db_path = Path(settings.SQLITE_DB)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


def _init_db():
    """Inicializa la base de datos creando las tablas necesarias."""
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash TEXT NOT NULL,
            original_query TEXT NOT NULL,
            optimized_query TEXT,
            findings_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            llm_analysis TEXT,
            explain_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Índice para búsquedas rápidas
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at ON analyses(created_at DESC)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_hash ON analyses(query_hash)
    """)
    
    conn.commit()
    conn.close()


def _calculate_query_hash(query: str) -> str:
    """Calcula un hash MD5 de la query para identificación rápida."""
    return hashlib.md5(query.encode('utf-8')).hexdigest()


def save_analysis(query: str, response: dict) -> int:
    """
    Guarda un análisis en el historial.
    
    Args:
        query: Query SQL original
        response: Respuesta completa del análisis (AnalyzeResponse como dict)
    
    Returns:
        ID del registro insertado
    """
    _init_db()
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    query_hash = _calculate_query_hash(query)
    
    cursor.execute("""
        INSERT INTO analyses (
            query_hash,
            original_query,
            optimized_query,
            findings_json,
            summary_json,
            llm_analysis,
            explain_analysis
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        query_hash,
        query,
        response.get("optimized_query"),
        json.dumps(response.get("findings", [])),
        json.dumps(response.get("summary", {})),
        response.get("llm_analysis"),
        response.get("explain_analysis")
    ))
    
    analysis_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return analysis_id


def get_history(limit: int = 20, offset: int = 0) -> list[dict]:
    """
    Obtiene el historial de análisis.
    
    Args:
        limit: Número máximo de registros a retornar
        offset: Offset para paginación
    
    Returns:
        Lista de análisis con metadatos
    """
    _init_db()
    
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id,
            query_hash,
            original_query,
            summary_json,
            created_at
        FROM analyses
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        # Extraer primera línea de la query (sin espacios en blanco)
        query_lines = [line.strip() for line in row["original_query"].split('\n') if line.strip()]
        first_line = query_lines[0] if query_lines else "Empty query"
        
        # Truncar si es muy larga
        if len(first_line) > 60:
            first_line = first_line[:60] + "..."
        
        history.append({
            "id": row["id"],
            "query_hash": row["query_hash"],
            "query_preview": first_line,
            "summary": json.loads(row["summary_json"]),
            "created_at": row["created_at"]
        })
    
    return history


def get_analysis_by_id(analysis_id: int) -> Optional[dict]:
    """
    Obtiene un análisis específico por ID.
    
    Args:
        analysis_id: ID del análisis
    
    Returns:
        Análisis completo o None si no existe
    """
    _init_db()
    
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            id,
            query_hash,
            original_query,
            optimized_query,
            findings_json,
            summary_json,
            llm_analysis,
            explain_analysis,
            created_at
        FROM analyses
        WHERE id = ?
    """, (analysis_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "id": row["id"],
        "query_hash": row["query_hash"],
        "original_query": row["original_query"],
        "optimized_query": row["optimized_query"],
        "findings": json.loads(row["findings_json"]),
        "summary": json.loads(row["summary_json"]),
        "llm_analysis": row["llm_analysis"],
        "explain_analysis": row["explain_analysis"],
        "created_at": row["created_at"]
    }


def delete_old_analyses(days: int = 30):
    """
    Elimina análisis más antiguos que N días.
    
    Args:
        days: Días de retención
    """
    _init_db()
    
    conn = sqlite3.connect(_get_db_path())
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM analyses
        WHERE created_at < datetime('now', '-' || ? || ' days')
    """, (days,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted
