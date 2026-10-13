# SQL Parser - Analizador de Queries Impala/Hive

Módulo de análisis de queries SQL usando sqlglot con dialecto Hive.

## Características

El parser `sql_parser.py` extrae la estructura completa de queries SQL y detecta:

### 1. CTEs (Common Table Expressions)
- Nombre de la CTE
- Query SQL completa
- Columnas utilizadas
- Tablas referenciadas
- **Conteo de referencias** (cuántas veces se usa en el query principal y en otras CTEs)

### 2. JOINs
- Tipo de JOIN (LEFT, INNER, CROSS, RIGHT)
- Tablas involucradas
- Condición ON completa
- **Detección de CAST** en condiciones
- **Detección de funciones** en condiciones (CONCAT, SUBSTRING, etc.)
- **CAST en ambos lados** de la igualdad (anti-pattern)

### 3. MAX(fecha_*) - Patrón Común
- Detecta todos los `MAX()` sobre columnas que contienen "fecha"
- Útil para identificar queries que recalculan máximas fechas múltiples veces

### 4. Subqueries Correlacionadas
- Detecta subqueries en cláusula SELECT
- Identifica si son correlacionadas (referencian outer query)

### 5. Tablas y Condiciones
- Lista completa de tablas referenciadas
- Condiciones WHERE extraídas
- Filtros sobre columnas de partición

### 6. REPLACE Chains
- Detecta cadenas de REPLACE anidados (>2 = warning)

### 7. SELECT *
- Detecta uso de `SELECT *` en queries

## Uso

```python
from backend.analyzer.sql_parser import parse_query

sql = """
WITH datos AS (
    SELECT * FROM tabla WHERE fecha = '2024-01-01'
)
SELECT d.id, d.nombre
FROM datos d
LEFT JOIN otra_tabla o ON CAST(d.id AS INT) = CAST(o.id AS INT)
"""

result = parse_query(sql)

print(f"CTEs: {len(result.ctes)}")
print(f"JOINs: {len(result.joins)}")
print(f"Tablas: {result.tables}")

# Revisar JOINs con CAST en ambos lados
for join in result.joins:
    if join.cast_both_sides:
        print(f"⚠️  JOIN con CAST en ambos lados: {join.condition}")
```

## Estructura de Datos

### ParsedQuery
Objeto principal que contiene toda la estructura parseada:
- `raw_sql`: Query original
- `ctes`: Lista de ParsedCTE
- `joins`: Lista de ParsedJoin
- `selects`: Lista de ParsedSelect
- `tables`: Lista de nombres de tablas
- `where_conditions`: Lista de condiciones WHERE
- `subqueries_in_select`: Cantidad de subqueries correlacionadas
- `max_fecha_count`: Cantidad de MAX(fecha_*)
- `replace_chain_count`: Profundidad máxima de REPLACE anidados
- `partition_filters`: Dict con filtros de partición
- `errors`: Lista de errores durante el parsing

## Anti-Patterns Detectados

El parser está diseñado para facilitar la detección de:

1. **CTEs no utilizadas**: `references_count == 0`
2. **CAST en JOINs**: Afecta performance, especialmente en ambos lados
3. **MAX(fecha) repetidos**: Recalcula la misma fecha múltiples veces
4. **Subqueries correlacionadas**: Pueden ser lentas en grandes volúmenes
5. **SELECT ***: No optimizado, trae columnas innecesarias
6. **REPLACE chains**: Múltiples REPLACE anidados son difíciles de mantener
7. **WHERE sobre tabla right de LEFT JOIN**: Convierte el JOIN en INNER

## Testing

Ejecutar el test integrado:

```bash
cd backend/analyzer
python sql_parser.py
```

El test verifica todos los casos con una query compleja que incluye CTEs, JOINs, MAX(fecha), y subqueries correlacionadas.

## Requisitos

- `sqlglot >= 26.0.0`: Parser SQL multi-dialecto
- Python 3.12+

## Dialecto

El parser usa el dialecto **"hive"** que es compatible con Impala. sqlglot maneja automáticamente las diferencias sintácticas entre ambos.
