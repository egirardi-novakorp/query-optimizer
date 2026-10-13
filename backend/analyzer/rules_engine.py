"""
Motor de reglas determinísticas para detectar anti-patterns en queries SQL.
Analiza la estructura parseada y genera findings con severidad y sugerencias.
"""

from backend.api.models import RuleFinding
from backend.analyzer.sql_parser import ParsedQuery, ParsedJoin, ParsedCTE
import re


def run_all_rules(parsed: ParsedQuery, ddl: str | None = None) -> list[RuleFinding]:
    """
    Ejecuta todas las reglas y retorna los hallazgos.
    
    Args:
        parsed: Query parseada con sql_parser
        ddl: DDL opcional de las tablas (para R09)
    
    Returns:
        Lista de RuleFinding con todos los hallazgos
    """
    findings = []
    
    # Ejecutar todas las reglas
    findings.extend(r01_cte_innecesaria(parsed))
    findings.extend(r02_select_star(parsed))
    findings.extend(r03_left_is_inner(parsed))
    findings.extend(r04_cast_in_join(parsed))
    findings.extend(r05_scalar_cast(parsed))
    findings.extend(r06_function_in_join(parsed))
    findings.extend(r07_replace_multiple(parsed))
    findings.extend(r08_max_fecha_repeated(parsed))
    
    if ddl:
        findings.extend(r09_full_scan(parsed, ddl))
    
    findings.extend(r10_logic_in_join(parsed))
    findings.extend(r11_cast_both_sides(parsed))
    findings.extend(r12_correlated_subquery(parsed))
    
    return findings


def r01_cte_innecesaria(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R01 - CTE usada solo 1 vez puede ser inlineada como subquery.
    Severity: warning
    """
    findings = []
    
    for cte in parsed.ctes:
        if cte.references_count <= 1:
            findings.append(RuleFinding(
                rule_id="R01",
                rule_name="CTE innecesaria",
                severity="warning",
                description=f"La CTE '{cte.name}' solo se usa {cte.references_count} vez. "
                           f"Puede ser más eficiente inlinearla como subquery.",
                location=f"CTE '{cte.name}'",
                suggestion="Considerar inlinear esta CTE directamente en el FROM como subquery "
                          "o eliminarla si no se usa. Las CTEs en Hive se materializan, lo que "
                          "puede causar overhead innecesario para expresiones usadas una sola vez.",
                code_before=f"WITH {cte.name} AS (\n  {cte.query[:80]}...\n)",
                code_after=f"-- Inlinear en FROM:\nFROM ({cte.query[:60]}...) AS {cte.name}"
            ))
    
    return findings


def r02_select_star(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R02 - SELECT * trae todas las columnas, muchas innecesarias.
    Severity: critical
    """
    findings = []
    
    for i, select in enumerate(parsed.selects, 1):
        if select.has_star:
            findings.append(RuleFinding(
                rule_id="R02",
                rule_name="SELECT * detectado",
                severity="critical",
                description="El uso de SELECT * trae todas las columnas de la tabla, "
                           "incluyendo muchas que probablemente no se necesitan. "
                           "En tablas con cientos de columnas esto causa overhead significativo.",
                location=f"SELECT #{i}",
                suggestion="Especificar explícitamente solo las columnas necesarias. "
                          "Esto reduce el volumen de datos transferidos y mejora el performance.",
                code_before="SELECT *",
                code_after="SELECT \n  columna1,\n  columna2,\n  columna3\n  -- solo las necesarias"
            ))
    
    return findings


def r03_left_is_inner(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R03 - LEFT JOIN que en realidad es INNER por filtro en WHERE.
    Severity: critical
    """
    findings = []
    
    for join in parsed.joins:
        if join.join_type != "LEFT":
            continue
        
        # Buscar WHERE que filtre la tabla right (convierte LEFT en INNER)
        right_table = join.right_table.lower()
        right_parts = right_table.split('.')
        right_table_name = right_parts[-1]  # Última parte si tiene schema
        
        # Buscar posible alias de la tabla right en la query
        # El alias suele ser una letra después del nombre de tabla
        # Por ejemplo: "LEFT JOIN datos_extra e" -> alias es "e"
        
        for where_cond in parsed.where_conditions:
            where_lower = where_cond.lower()
            
            # Verificar si el WHERE filtra la tabla right
            # Buscar referencias a la tabla o su alias
            # Patrón común: "alias.columna" o "tabla.columna"
            has_reference = False
            
            # Buscar si hay referencia a la tabla
            if right_table_name in where_lower or right_table in where_lower:
                has_reference = True
            else:
                # Buscar por prefijos comunes (e., d., a., b., etc.)
                # Buscar "letra." al inicio de palabras
                import re
                # Buscar patrones como "e.columna"
                alias_pattern = r'\b([a-z])\.'
                aliases = re.findall(alias_pattern, where_lower)
                
                # Si encontramos alias, verificar si podría ser de la tabla right
                # (esto es una heurística simple)
                if aliases:
                    # Asumimos que los primeros caracteres de las tablas son sus alias comunes
                    if right_table_name[0] in aliases:
                        has_reference = True
            
            # Excluir IS NULL / IS NOT NULL que son válidos en LEFT JOIN
            if has_reference:
                if "is null" not in where_lower and "is not null" not in where_lower:
                    findings.append(RuleFinding(
                        rule_id="R03",
                        rule_name="LEFT JOIN que es INNER implícito",
                        severity="critical",
                        description=f"El LEFT JOIN con '{join.right_table}' tiene un filtro "
                                   f"en WHERE que descarta NULLs: '{where_cond}'. "
                                   f"Esto convierte el LEFT JOIN en INNER JOIN implícito.",
                        location=f"LEFT JOIN {join.right_table}",
                        suggestion="Cambiar a INNER JOIN explícito para claridad y mejor plan de ejecución. "
                                  "El optimizador puede no detectar esto y generar un plan subóptimo.",
                        code_before=f"LEFT JOIN {join.right_table}\n  ON {join.condition[:40]}...\nWHERE {where_cond[:40]}...",
                        code_after=f"INNER JOIN {join.right_table}\n  ON {join.condition[:40]}..."
                    ))
                    break  # Ya encontramos un problema, no seguir buscando
    
    return findings


def r04_cast_in_join(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R04 - CAST en condición de JOIN impide uso de índices/stats.
    Severity: critical
    """
    findings = []
    
    for join in parsed.joins:
        if join.has_cast and not join.cast_both_sides:  # R11 maneja ambos lados
            findings.append(RuleFinding(
                rule_id="R04",
                rule_name="CAST en condición de JOIN",
                severity="critical",
                description=f"El JOIN con '{join.right_table}' tiene CAST en la condición. "
                           f"Esto impide el uso eficiente de estadísticas y puede causar "
                           f"shuffle masivo en tablas grandes.",
                location=f"{join.join_type} JOIN {join.right_table}",
                suggestion="Precalcular el CAST en una CTE previa o asegurar que los tipos "
                          "de las columnas coincidan en ambas tablas. Si es un escalar, "
                          "castearlo al tipo de la tabla grande.",
                code_before=f"ON {join.condition}",
                code_after="-- Opción 1: Precalcular en CTE\nWITH tabla_prep AS (\n"
                          "  SELECT CAST(columna AS tipo) AS columna_cast\n"
                          "  FROM tabla\n)\n-- Opción 2: Ajustar tipos en DDL"
            ))
    
    return findings


def r05_scalar_cast(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R05 - Escalar casteado a tipo diferente del origen.
    Severity: warning
    
    Nota: Esta regla es compleja y requiere análisis de tipos.
    Por ahora, implementación básica.
    """
    findings = []
    
    # Esta regla requiere análisis semántico profundo
    # Por ahora, la dejamos como placeholder
    # TODO: Implementar cuando tengamos información de tipos del DDL
    
    return findings


def r06_function_in_join(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R06 - Funciones (CONCAT, SUBSTRING, etc) en condición de JOIN.
    Severity: warning
    """
    findings = []
    
    for join in parsed.joins:
        if join.has_function and not join.has_cast:  # Evitar duplicados con R04
            # Filtrar detalles de funciones (no CAST)
            func_details = [d for d in join.cast_details if not d.startswith("CAST")]
            
            if func_details:
                findings.append(RuleFinding(
                    rule_id="R06",
                    rule_name="Función en condición de JOIN",
                    severity="warning",
                    description=f"El JOIN con '{join.right_table}' usa funciones en la condición: "
                               f"{', '.join(func_details[:2])}. Esto puede ser costoso en tablas grandes.",
                    location=f"{join.join_type} JOIN {join.right_table}",
                    suggestion="Si es posible, precalcular estas transformaciones en CTEs previas "
                              "o crear columnas calculadas en las tablas base.",
                    code_before=f"ON {join.condition}",
                    code_after="-- Precalcular en CTE:\nWITH tabla_prep AS (\n"
                              "  SELECT *, funcion(columna) AS columna_calc\n"
                              "  FROM tabla\n)\n-- JOIN sobre columna_calc"
                ))
    
    return findings


def r07_replace_multiple(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R07 - Múltiples REPLACE anidados (>2) son difíciles de mantener.
    Severity: warning
    """
    findings = []
    
    if parsed.replace_chain_count > 2:
        findings.append(RuleFinding(
            rule_id="R07",
            rule_name="REPLACE múltiples anidados",
            severity="warning",
            description=f"Se detectaron {parsed.replace_chain_count} REPLACE anidados. "
                       f"Esto es difícil de leer y mantener.",
            location="Query principal",
            suggestion="Considerar usar REGEXP_REPLACE con un patrón más complejo, "
                      "o separar las transformaciones en CTEs intermedias con nombres descriptivos.",
            code_before="REPLACE(REPLACE(REPLACE(campo, 'a', ''), 'b', ''), 'c', '')",
            code_after="REGEXP_REPLACE(campo, '[abc]', '')\n-- o usar CTEs intermedias"
        ))
    
    return findings


def r08_max_fecha_repeated(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R08 - MAX(fecha_proceso) repetido en múltiples lugares.
    Severity: warning
    """
    findings = []
    
    if parsed.max_fecha_count > 1:
        findings.append(RuleFinding(
            rule_id="R08",
            rule_name="MAX(fecha_*) repetido",
            severity="warning",
            description=f"Se detectaron {parsed.max_fecha_count} llamadas a MAX() sobre columnas "
                       f"de fecha. Cada una ejecuta un full scan de la tabla.",
            location="Múltiples ubicaciones en la query",
            suggestion="Calcular MAX(fecha) una sola vez en una CTE al inicio y referenciarla "
                      "con CROSS JOIN en las demás consultas. Esto reduce de N full scans a 1.",
            code_before="-- En cada subquery:\nSELECT MAX(fecha_proceso) FROM tabla",
            code_after="-- Una vez al inicio:\nWITH max_fecha AS (\n"
                      "  SELECT MAX(fecha_proceso) AS fp FROM tabla\n)\n"
                      "-- Referenciar con CROSS JOIN:\nCROSS JOIN max_fecha"
        ))
    
    return findings


def r09_full_scan(parsed: ParsedQuery, ddl: str) -> list[RuleFinding]:
    """
    R09 - Full scan sin filtro de partición.
    Severity: critical
    
    Requiere DDL para saber qué columnas son particiones.
    """
    findings = []
    
    # Extraer columnas de partición del DDL
    partition_cols = _extract_partition_columns(ddl)
    
    if not partition_cols:
        return findings  # No hay info de particiones
    
    # Verificar si las tablas tienen filtros de partición
    for table in parsed.tables:
        table_lower = table.lower()
        
        # Verificar si esta tabla tiene filtro de partición
        has_partition_filter = False
        for filter_table, filter_cols in parsed.partition_filters.items():
            if filter_table in table_lower or table_lower.endswith(filter_table):
                # Verificar si alguna de las columnas filtradas es partición
                if any(col.lower() in partition_cols for col in filter_cols):
                    has_partition_filter = True
                    break
        
        if not has_partition_filter:
            findings.append(RuleFinding(
                rule_id="R09",
                rule_name="Full scan sin filtro de partición",
                severity="critical",
                description=f"La tabla '{table}' no tiene filtro sobre columnas de partición "
                           f"({', '.join(partition_cols)}). Esto causa un full scan que puede "
                           f"leer billones de registros.",
                location=f"FROM {table}",
                suggestion=f"Agregar filtro WHERE sobre columna de partición. "
                          f"Ejemplos: WHERE fecha_proceso = '2024-01-01' o "
                          f"WHERE fecha_proceso BETWEEN '2024-01-01' AND '2024-01-31'",
                code_before=f"FROM {table}",
                code_after=f"FROM {table}\nWHERE fecha_proceso = '<fecha_especifica>'"
            ))
    
    return findings


def r10_logic_in_join(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R10 - Lógica condicional (CASE, IF, COALESCE) en condición de JOIN.
    Severity: warning
    """
    findings = []
    
    for join in parsed.joins:
        if join.condition:
            condition_upper = join.condition.upper()
            
            # Detectar palabras clave de lógica condicional
            has_logic = any(keyword in condition_upper 
                          for keyword in ["CASE", "IF(", "COALESCE("])
            
            if has_logic:
                findings.append(RuleFinding(
                    rule_id="R10",
                    rule_name="Lógica condicional en JOIN",
                    severity="warning",
                    description=f"El JOIN con '{join.right_table}' tiene lógica condicional "
                               f"(CASE/IF/COALESCE) en la condición ON. Esto se evalúa por cada "
                               f"combinación de filas y puede ser muy costoso.",
                    location=f"{join.join_type} JOIN {join.right_table}",
                    suggestion="Precalcular el resultado de la lógica condicional en una CTE previa. "
                              "Esto se ejecuta una vez por fila en lugar de una vez por combinación.",
                    code_before=f"ON {join.condition[:80]}...",
                    code_after="-- Precalcular en CTE:\nWITH tabla_prep AS (\n"
                              "  SELECT *, CASE ... END AS condicion_calc\n"
                              "  FROM tabla\n)\n-- JOIN sobre condicion_calc"
                ))
    
    return findings


def r11_cast_both_sides(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R11 - CAST en ambos lados de la condición de JOIN.
    Severity: critical
    """
    findings = []
    
    for join in parsed.joins:
        if join.cast_both_sides:
            findings.append(RuleFinding(
                rule_id="R11",
                rule_name="CAST en ambos lados del JOIN",
                severity="critical",
                description=f"El JOIN con '{join.right_table}' tiene CAST en ambos lados de la "
                           f"condición: {join.condition}. Esto es especialmente costoso porque "
                           f"impide cualquier optimización del optimizador.",
                location=f"{join.join_type} JOIN {join.right_table}",
                suggestion="Precalcular los CAST en CTEs previas para ambas tablas. Idealmente, "
                          "ajustar los tipos de datos en las tablas base para evitar conversiones.",
                code_before=f"ON {join.condition}",
                code_after="-- Precalcular en CTEs:\nWITH tabla_a_prep AS (\n"
                          "  SELECT CAST(col AS tipo) AS col_cast FROM tabla_a\n),\n"
                          "tabla_b_prep AS (\n"
                          "  SELECT CAST(col AS tipo) AS col_cast FROM tabla_b\n)\n"
                          "-- JOIN sin CAST:\nON a.col_cast = b.col_cast"
            ))
    
    return findings


def r12_correlated_subquery(parsed: ParsedQuery) -> list[RuleFinding]:
    """
    R12 - Subquery correlacionada en SELECT.
    Severity: warning
    """
    findings = []
    
    if parsed.subqueries_in_select > 0:
        findings.append(RuleFinding(
            rule_id="R12",
            rule_name="Subquery correlacionada en SELECT",
            severity="warning",
            description=f"Se detectaron {parsed.subqueries_in_select} subquery(s) correlacionada(s) "
                       f"en la cláusula SELECT. Cada subquery se ejecuta una vez por cada fila "
                       f"del resultado, lo que puede ser muy lento.",
            location="SELECT con subqueries",
            suggestion="Mover la subquery a un LEFT JOIN. Esto ejecuta la subquery una sola vez "
                      "y hace un JOIN, que suele ser mucho más eficiente en Impala.",
            code_before="SELECT \n  columna,\n  (SELECT MAX(x) FROM tabla WHERE id = outer.id) AS max_x",
            code_after="-- Mover a LEFT JOIN:\nLEFT JOIN (\n"
                      "  SELECT id, MAX(x) AS max_x FROM tabla GROUP BY id\n) subq\n"
                      "ON main.id = subq.id"
        ))
    
    return findings


def _extract_partition_columns(ddl: str) -> list[str]:
    """
    Extrae columnas de partición del DDL.
    Busca: PARTITIONED BY (col1 type, col2 type)
    """
    partition_cols = []
    
    # Buscar patrón PARTITIONED BY
    pattern = r'PARTITIONED\s+BY\s*\((.*?)\)'
    match = re.search(pattern, ddl.upper())
    
    if match:
        # Extraer nombres de columnas (ignorar tipos)
        cols_str = match.group(1)
        for col_def in cols_str.split(','):
            col_name = col_def.strip().split()[0]  # Primera palabra es el nombre
            partition_cols.append(col_name.lower())
    
    return partition_cols
