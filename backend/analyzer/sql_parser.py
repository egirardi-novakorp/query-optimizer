"""
Parser SQL con sqlglot para análisis de AST de queries Impala/Hive.
Extrae estructura completa de queries para detección de anti-patterns.
"""

from dataclasses import dataclass, field
from typing import Optional
import sqlglot
from sqlglot import exp
from collections import defaultdict


@dataclass
class ParsedCTE:
    name: str
    query: str                     # SQL de la CTE
    columns: list[str]             # columnas usadas
    tables_referenced: list[str]   # tablas que referencia
    references_count: int = 0      # cuantas veces se usa en el query principal + otras CTEs


@dataclass
class ParsedJoin:
    join_type: str                 # "LEFT", "INNER", "CROSS", "RIGHT"
    left_table: str
    right_table: str
    condition: str                 # SQL de la condicion ON
    has_cast: bool                 # CAST en la condicion
    has_function: bool             # funcion (CONCAT, SUBSTRING, etc) en condicion
    cast_details: list[str]        # detalle de cada CAST/funcion encontrada
    cast_both_sides: bool = False  # CAST en ambos lados del =


@dataclass
class ParsedSelect:
    columns: list[str]
    has_star: bool
    table_source: str = ""


@dataclass
class ParsedQuery:
    raw_sql: str
    dialect: str = "hive"
    ctes: list[ParsedCTE] = field(default_factory=list)
    joins: list[ParsedJoin] = field(default_factory=list)
    selects: list[ParsedSelect] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    where_conditions: list[str] = field(default_factory=list)
    subqueries_in_select: int = 0  # subqueries correlacionadas en SELECT
    has_max_fecha: bool = False
    max_fecha_count: int = 0       # cuantos MAX(fecha_*) hay
    replace_chain_count: int = 0   # REPLACE anidados (>2 = warning)
    partition_filters: dict = field(default_factory=dict)  # {tabla: [columnas filtradas]}
    errors: list[str] = field(default_factory=list)


def parse_query(sql: str) -> ParsedQuery:
    """
    Parsea una query SQL de Hive/Impala y extrae toda su estructura.
    
    Args:
        sql: Query SQL a parsear
        
    Returns:
        ParsedQuery con toda la estructura extraída
    """
    result = ParsedQuery(raw_sql=sql)
    
    try:
        # Parsear con sqlglot usando dialecto Hive
        parsed = sqlglot.parse_one(sql, dialect="hive")
        
        # Extraer componentes
        result.ctes = _extract_ctes(parsed, sql)
        result.joins = _extract_joins(parsed)
        result.selects = _extract_selects(parsed)
        result.tables = _extract_tables(parsed)
        result.where_conditions = _extract_where(parsed)
        result.subqueries_in_select = _detect_correlated_subqueries(parsed)
        result.max_fecha_count, result.has_max_fecha = _detect_max_fecha(parsed)
        result.replace_chain_count = _detect_replace_chains(parsed)
        result.partition_filters = _detect_partition_filters(parsed)
        
    except Exception as e:
        result.errors.append(f"Parse error: {str(e)}")
    
    return result


def _extract_ctes(parsed: exp.Expression, original_sql: str) -> list[ParsedCTE]:
    """
    Extrae todas las CTEs (WITH clauses) y cuenta sus referencias.
    """
    ctes = []
    cte_names = set()
    
    # Primero, encontrar todas las CTEs
    for cte in parsed.find_all(exp.CTE):
        cte_name = cte.alias
        if not cte_name:
            continue
            
        cte_names.add(cte_name.lower())
        
        # Extraer query de la CTE
        cte_query = cte.this.sql(dialect="hive")
        
        # Extraer columnas
        columns = []
        for col in cte.this.find_all(exp.Column):
            col_name = col.name
            if col_name and col_name != "*":
                columns.append(col_name)
        
        # Extraer tablas referenciadas
        tables_ref = []
        for table in cte.this.find_all(exp.Table):
            table_name = table.name
            if table_name:
                full_name = f"{table.db}.{table_name}" if table.db else table_name
                tables_ref.append(full_name)
        
        parsed_cte = ParsedCTE(
            name=cte_name,
            query=cte_query,
            columns=list(set(columns)),
            tables_referenced=list(set(tables_ref)),
            references_count=0
        )
        ctes.append(parsed_cte)
    
    # Contar referencias a cada CTE en el query principal y en otras CTEs
    for cte in ctes:
        cte.references_count = _count_cte_references(parsed, cte.name, cte_names)
    
    return ctes


def _count_cte_references(parsed: exp.Expression, cte_name: str, all_cte_names: set) -> int:
    """
    Cuenta cuántas veces se referencia una CTE en el query (excluyendo su definición).
    """
    count = 0
    cte_name_lower = cte_name.lower()
    
    # Buscar todas las referencias a tablas
    for table in parsed.find_all(exp.Table):
        table_name = table.name
        if table_name and table_name.lower() == cte_name_lower:
            # Verificar que no sea la definición de la CTE misma
            # La definición está dentro de un nodo CTE
            parent = table.parent
            is_definition = False
            while parent:
                if isinstance(parent, exp.CTE) and parent.alias == cte_name:
                    is_definition = True
                    break
                parent = parent.parent
            
            if not is_definition:
                count += 1
    
    return count


def _extract_joins(parsed: exp.Expression) -> list[ParsedJoin]:
    """
    Extrae todos los JOINs y analiza sus condiciones.
    """
    joins = []
    
    for join in parsed.find_all(exp.Join):
        try:
            # Determinar tipo de JOIN
            join_type = "INNER"
            if join.side:
                join_type = join.side.upper()
            if join.kind:
                join_type = join.kind.upper()
            
            # Extraer tablas involucradas
            right_table = ""
            if isinstance(join.this, exp.Table):
                right_table = join.this.name
                if join.this.db:
                    right_table = f"{join.this.db}.{right_table}"
            elif isinstance(join.this, exp.Subquery):
                right_table = join.this.alias or "subquery"
            elif hasattr(join.this, 'alias'):
                right_table = join.this.alias or str(join.this)
            
            # Extraer condición ON usando args.get('on') porque .on es un método
            on_condition = join.args.get('on')
            condition = ""
            if on_condition:
                condition = on_condition.sql(dialect="hive")
            
            # Detectar CAST y funciones en la condición
            cast_details = []
            has_cast = False
            has_function = False
            cast_both_sides = False
            
            if on_condition:
                # Buscar CAST
                casts = list(on_condition.find_all(exp.Cast))
                if casts:
                    has_cast = True
                    for cast in casts:
                        try:
                            cast_details.append(cast.sql(dialect="hive"))
                        except:
                            cast_details.append(f"CAST expression")
                
                # Buscar funciones comunes
                functions = [
                    exp.Anonymous,  # funciones genericas
                    exp.Concat, exp.Substring, exp.Replace, exp.RegexpReplace,
                    exp.Trim, exp.Upper, exp.Lower, exp.Coalesce, exp.If, exp.Case
                ]
                
                for func_type in functions:
                    funcs = list(on_condition.find_all(func_type))
                    if funcs:
                        has_function = True
                        for func in funcs:
                            try:
                                cast_details.append(func.sql(dialect="hive"))
                            except:
                                cast_details.append(f"{func_type.__name__} expression")
                
                # Detectar CAST en ambos lados de igualdad
                if has_cast and isinstance(on_condition, exp.EQ):
                    left_has_cast = len(list(on_condition.left.find_all(exp.Cast))) > 0
                    right_has_cast = len(list(on_condition.right.find_all(exp.Cast))) > 0
                    cast_both_sides = left_has_cast and right_has_cast
            
            parsed_join = ParsedJoin(
                join_type=join_type,
                left_table="",  # Se completa en contexto
                right_table=right_table,
                condition=condition,
                has_cast=has_cast,
                has_function=has_function,
                cast_details=cast_details,
                cast_both_sides=cast_both_sides
            )
            joins.append(parsed_join)
        except Exception as e:
            # Si hay error en un JOIN individual, continuar con los demás
            continue
    
    return joins


def _extract_selects(parsed: exp.Expression) -> list[ParsedSelect]:
    """
    Extrae todas las cláusulas SELECT.
    """
    selects = []
    
    for select in parsed.find_all(exp.Select):
        try:
            columns = []
            has_star = False
            
            for projection in select.expressions:
                if isinstance(projection, exp.Star):
                    has_star = True
                    columns.append("*")
                else:
                    try:
                        col_sql = projection.sql(dialect="hive")
                        columns.append(col_sql)
                    except:
                        columns.append(str(projection))
            
            parsed_select = ParsedSelect(
                columns=columns,
                has_star=has_star
            )
            selects.append(parsed_select)
        except:
            continue
    
    return selects


def _extract_tables(parsed: exp.Expression) -> list[str]:
    """
    Extrae todas las tablas referenciadas.
    """
    tables = []
    
    for table in parsed.find_all(exp.Table):
        try:
            table_name = table.name
            if table_name:
                full_name = f"{table.db}.{table_name}" if table.db else table_name
                tables.append(full_name)
        except:
            continue
    
    return list(set(tables))


def _extract_where(parsed: exp.Expression) -> list[str]:
    """
    Extrae todas las condiciones WHERE.
    """
    conditions = []
    
    for where in parsed.find_all(exp.Where):
        try:
            condition_sql = where.this.sql(dialect="hive")
            conditions.append(condition_sql)
        except:
            continue
    
    return conditions


def _detect_correlated_subqueries(parsed: exp.Expression) -> int:
    """
    Detecta subqueries correlacionadas en cláusulas SELECT.
    """
    count = 0
    
    # Buscar SELECT principales
    for select in parsed.find_all(exp.Select):
        # Buscar subqueries en las proyecciones
        for projection in select.expressions:
            subqueries = list(projection.find_all(exp.Subquery))
            for subquery in subqueries:
                # Verificar si es correlacionada (referencia columnas del outer query)
                # Por simplicidad, consideramos correlacionada si hay columnas en WHERE del subquery
                where_clauses = list(subquery.find_all(exp.Where))
                if where_clauses:
                    count += 1
    
    return count


def _detect_max_fecha(parsed: exp.Expression) -> tuple[int, bool]:
    """
    Detecta usos de MAX() sobre columnas que contienen 'fecha' en el nombre.
    """
    count = 0
    
    for func in parsed.find_all(exp.Max):
        # Verificar si el argumento contiene 'fecha' en el nombre
        arg_sql = func.this.sql(dialect="hive").lower()
        if "fecha" in arg_sql:
            count += 1
    
    return count, count > 0


def _detect_replace_chains(parsed: exp.Expression) -> int:
    """
    Detecta cadenas de REPLACE anidados (más de 2 niveles).
    """
    max_depth = 0
    
    for replace in parsed.find_all(exp.Replace):
        depth = _count_replace_depth(replace)
        max_depth = max(max_depth, depth)
    
    return max_depth


def _count_replace_depth(node: exp.Expression) -> int:
    """
    Cuenta la profundidad de REPLACEs anidados.
    """
    if not isinstance(node, exp.Replace):
        return 0
    
    # Buscar REPLACE anidados en el primer argumento
    nested = list(node.this.find_all(exp.Replace))
    if not nested:
        return 1
    
    return 1 + max(_count_replace_depth(n) for n in nested)


def _detect_partition_filters(parsed: exp.Expression) -> dict:
    """
    Detecta filtros sobre columnas de partición.
    Asume que columnas con 'fecha', 'partition', 'part' son particiones.
    """
    filters = defaultdict(list)
    
    # Buscar condiciones WHERE
    for where in parsed.find_all(exp.Where):
        # Buscar columnas en condiciones
        for col in where.find_all(exp.Column):
            col_name = col.name.lower()
            if any(keyword in col_name for keyword in ["fecha", "partition", "part"]):
                table = col.table or "unknown"
                filters[table].append(col.name)
    
    return dict(filters)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    test_query = """
    WITH max_fecha AS (
        SELECT MAX(fecha_proceso) AS fp FROM db.tabla_grande
    ),
    datos_base AS (
        SELECT 
            CAST(a.id_cliente AS STRING) AS id_cliente,
            a.nombre,
            a.fecha_proceso
        FROM db.tabla_grande a
        CROSS JOIN max_fecha mf
        WHERE a.fecha_proceso = mf.fp
    ),
    datos_extra AS (
        SELECT b.id_cliente, b.saldo
        FROM db.otra_tabla b
        WHERE b.fecha_proceso = (SELECT MAX(fecha_proceso) FROM db.otra_tabla)
    )
    SELECT 
        d.id_cliente,
        d.nombre,
        e.saldo,
        (SELECT MAX(monto) FROM db.montos m WHERE m.id_cliente = d.id_cliente) AS max_monto
    FROM datos_base d
    LEFT JOIN datos_extra e 
        ON CAST(d.id_cliente AS INT) = CAST(e.id_cliente AS INT)
    WHERE e.saldo > 0
    """
    
    print("=" * 80)
    print("TESTING SQL PARSER")
    print("=" * 80)
    
    result = parse_query(test_query)
    
    print(f"\n[OK] Query parseada exitosamente")
    print(f"\nRESULTADOS:")
    print(f"\n1. CTEs detectadas: {len(result.ctes)}")
    for cte in result.ctes:
        print(f"   - {cte.name}: referenciada {cte.references_count} veces")
        print(f"     Tablas: {cte.tables_referenced}")
    
    print(f"\n2. JOINs detectados: {len(result.joins)}")
    for i, join in enumerate(result.joins, 1):
        print(f"   JOIN {i}:")
        print(f"     Tipo: {join.join_type}")
        print(f"     Tabla: {join.right_table}")
        print(f"     CAST en condicion: {join.has_cast}")
        print(f"     CAST en ambos lados: {join.cast_both_sides}")
        if join.cast_details:
            print(f"     Detalles: {join.cast_details[:2]}")  # Primeros 2
    
    print(f"\n3. MAX(fecha_*) detectados: {result.max_fecha_count}")
    
    print(f"\n4. Subqueries correlacionadas en SELECT: {result.subqueries_in_select}")
    
    print(f"\n5. Tablas unicas: {len(result.tables)}")
    for table in sorted(set(result.tables)):
        print(f"   - {table}")
    
    print(f"\n6. Condiciones WHERE: {len(result.where_conditions)}")
    for cond in result.where_conditions[:3]:  # Primeras 3
        print(f"   - {cond[:60]}...")
    
    print(f"\n7. Filtros de particion detectados:")
    for table, cols in result.partition_filters.items():
        print(f"   {table}: {cols}")
    
    if result.errors:
        print(f"\n[ERROR] ERRORES:")
        for error in result.errors:
            print(f"   - {error}")
    
    print("\n" + "=" * 80)
    print("VERIFICACION DE CASOS ESPERADOS:")
    print("=" * 80)
    
    checks = [
        (len(result.ctes) == 3, f"[OK] 3 CTEs detectadas" if len(result.ctes) == 3 else f"[FAIL] Esperadas 3 CTEs, encontradas {len(result.ctes)}"),
        (len(result.joins) >= 1, f"[OK] LEFT JOIN detectado" if len(result.joins) >= 1 else "[FAIL] No se detecto el LEFT JOIN"),
        (any(j.cast_both_sides for j in result.joins), "[OK] CAST en ambos lados detectado" if any(j.cast_both_sides for j in result.joins) else "[FAIL] No se detecto CAST en ambos lados"),
        (result.max_fecha_count >= 2, f"[OK] {result.max_fecha_count} MAX(fecha_proceso) detectados" if result.max_fecha_count >= 2 else f"[FAIL] Esperados 2 MAX(fecha_*), encontrados {result.max_fecha_count}"),
        (result.subqueries_in_select >= 1, f"[OK] Subquery correlacionada detectada" if result.subqueries_in_select >= 1 else "[FAIL] No se detecto subquery correlacionada"),
    ]
    
    for passed, message in checks:
        print(f"  {message}")
    
    all_passed = all(c[0] for c in checks)
    print(f"\n{'[SUCCESS] TODOS LOS TESTS PASARON' if all_passed else '[WARNING] ALGUNOS TESTS FALLARON'}")
    print("=" * 80)
