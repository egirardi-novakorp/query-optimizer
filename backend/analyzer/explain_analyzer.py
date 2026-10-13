"""
Analizador de planes EXPLAIN de Impala/Hive.
Detecta full scans, memoria, JOINs, broadcasts y shuffles.
"""

import re
from typing import Optional


def analyze_explain(explain_text: str) -> str:
    """
    Analiza un plan EXPLAIN de Impala y extrae métricas clave.
    
    Args:
        explain_text: Texto del EXPLAIN plan
    
    Returns:
        Análisis textual con hallazgos del plan
    """
    
    if not explain_text or not explain_text.strip():
        return "No se proporcionó plan EXPLAIN."
    
    findings = []
    
    # 1. Detectar SCAN sin filtro de partición
    scans = _detect_full_scans(explain_text)
    if scans:
        findings.append("[!] **Full Scans Detectados:**")
        for scan in scans:
            findings.append(f"   - {scan}")
    
    # 2. Analizar memoria estimada
    memory_info = _analyze_memory(explain_text)
    if memory_info:
        findings.append(f"\n[MEM] **Memoria Estimada:** {memory_info}")
    
    # 3. Contar HASH JOINs
    hash_joins = _count_pattern(explain_text, r'HASH JOIN')
    if hash_joins > 0:
        findings.append(f"\n[JOIN] **HASH JOINs:** {hash_joins} detectados")
    
    # 4. Contar BROADCAST JOINs
    broadcasts = _count_pattern(explain_text, r'BROADCAST')
    if broadcasts > 0:
        findings.append(f"\n[BROADCAST] **BROADCAST JOINs:** {broadcasts} detectados")
        findings.append("   (Tabla pequena se broadcast a todos los nodos)")
    
    # 5. Contar EXCHANGE (shuffles de red)
    exchanges = _count_pattern(explain_text, r'EXCHANGE')
    if exchanges > 3:
        findings.append(f"\n[SHUFFLE] **Shuffles de Red:** {exchanges} EXCHANGE detectados")
        findings.append("   [!] Mas de 3 shuffles puede indicar problema de performance")
    elif exchanges > 0:
        findings.append(f"\n[SHUFFLE] **Shuffles de Red:** {exchanges} EXCHANGE detectados")
    
    # 6. Analizar estimación de filas
    rows_info = _analyze_row_estimates(explain_text)
    if rows_info:
        findings.append(f"\n[ROWS] **Estimacion de Filas:**")
        for info in rows_info:
            findings.append(f"   - {info}")
    
    # 7. Detectar posibles problemas
    warnings = _detect_warnings(explain_text, hash_joins, broadcasts, exchanges)
    if warnings:
        findings.append("\n[WARNING] **Advertencias:**")
        for warning in warnings:
            findings.append(f"   - {warning}")
    
    if not findings:
        return "Plan EXPLAIN analizado: no se detectaron problemas evidentes."
    
    return "\n".join(findings)


def _detect_full_scans(explain_text: str) -> list[str]:
    """
    Detecta table scans sin filtros de partición.
    """
    scans = []
    
    # Buscar líneas con SCAN
    scan_pattern = r'SCAN\s+(\w+\.\w+)'
    matches = re.finditer(scan_pattern, explain_text, re.IGNORECASE)
    
    for match in matches:
        table = match.group(1)
        
        # Verificar si hay filtros de partición cerca
        # Buscar en las siguientes líneas después del SCAN
        scan_pos = match.start()
        context = explain_text[scan_pos:scan_pos + 500]
        
        # Si no encuentra "partition" en el contexto, es full scan
        if "partition" not in context.lower() and "predicates" not in context.lower():
            scans.append(f"Tabla {table} sin filtro de partición")
    
    return scans


def _analyze_memory(explain_text: str) -> Optional[str]:
    """
    Analiza memoria estimada del plan.
    """
    # Buscar mem-estimate=XXX
    memory_pattern = r'mem-estimate=([0-9.]+\s*[KMGT]B)'
    matches = re.findall(memory_pattern, explain_text, re.IGNORECASE)
    
    if not matches:
        return None
    
    # Sumar memoria total (aproximado)
    total_mb = 0
    for mem_str in matches:
        mb = _parse_memory_to_mb(mem_str)
        total_mb += mb
    
    if total_mb > 1024:
        return f"{total_mb / 1024:.2f} GB total"
    else:
        return f"{total_mb:.2f} MB total"


def _parse_memory_to_mb(mem_str: str) -> float:
    """
    Convierte strings de memoria a MB.
    Ej: "10.5GB" -> 10752.0
    """
    mem_str = mem_str.strip().upper()
    
    # Extraer número
    match = re.match(r'([0-9.]+)\s*([KMGT]?B)', mem_str)
    if not match:
        return 0.0
    
    value = float(match.group(1))
    unit = match.group(2)
    
    # Convertir a MB
    if unit == "KB":
        return value / 1024
    elif unit == "MB":
        return value
    elif unit == "GB":
        return value * 1024
    elif unit == "TB":
        return value * 1024 * 1024
    else:
        return value


def _count_pattern(text: str, pattern: str) -> int:
    """
    Cuenta ocurrencias de un patrón en el texto.
    """
    matches = re.findall(pattern, text, re.IGNORECASE)
    return len(matches)


def _analyze_row_estimates(explain_text: str) -> list[str]:
    """
    Analiza estimaciones de filas en los nodos del plan.
    """
    estimates = []
    
    # Buscar cardinality=XXXX
    card_pattern = r'cardinality=([0-9,]+)'
    matches = re.finditer(card_pattern, explain_text, re.IGNORECASE)
    
    cardinalities = []
    for match in matches:
        card_str = match.group(1).replace(',', '')
        try:
            card = int(card_str)
            cardinalities.append(card)
        except ValueError:
            continue
    
    if cardinalities:
        max_card = max(cardinalities)
        if max_card > 1_000_000_000:
            estimates.append(f"Máximo de filas procesadas: {max_card:,} (>1B)")
        elif max_card > 1_000_000:
            estimates.append(f"Máximo de filas procesadas: {max_card:,} (>1M)")
    
    return estimates


def _detect_warnings(
    explain_text: str,
    hash_joins: int,
    broadcasts: int,
    exchanges: int
) -> list[str]:
    """
    Detecta posibles problemas en el plan.
    """
    warnings = []
    
    # Muchos HASH JOINs pueden ser costosos
    if hash_joins > 5:
        warnings.append(f"{hash_joins} HASH JOINs pueden causar alto uso de memoria")
    
    # BROADCAST de tablas grandes es problema
    if broadcasts > 0:
        if "GB" in explain_text:
            warnings.append("BROADCAST con tablas grandes puede causar OOM")
    
    # Muchos shuffles
    if exchanges > 5:
        warnings.append(f"{exchanges} shuffles de red pueden ser muy lentos")
    
    # Buscar warnings explícitos en el plan
    if "WARNING" in explain_text.upper():
        warnings.append("El plan contiene advertencias explícitas")
    
    return warnings


# Función principal para mantener compatibilidad
def analyze_explain_plan(explain_text: str) -> str:
    """
    Alias para analyze_explain (compatibilidad).
    """
    return analyze_explain(explain_text)
