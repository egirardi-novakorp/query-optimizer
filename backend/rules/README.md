# Motor de Reglas - GP Query Optimizer

Motor de reglas determinísticas para detección de anti-patterns en queries Impala/Hive.

## Reglas Implementadas

### R01 - CTE innecesaria (WARNING)
**Problema**: CTE usada solo 1 vez  
**Detección**: `ParsedCTE.references_count <= 1`  
**Impacto**: Las CTEs en Hive se materializan, causando overhead innecesario  
**Sugerencia**: Inlinear como subquery

### R02 - SELECT * (CRITICAL)
**Problema**: SELECT * trae todas las columnas  
**Detección**: `ParsedSelect.has_star == True`  
**Impacto**: Overhead significativo en tablas con muchas columnas  
**Sugerencia**: Especificar solo columnas necesarias

### R03 - LEFT JOIN que es INNER implícito (CRITICAL)
**Problema**: LEFT JOIN con WHERE que filtra NULLs de tabla right  
**Detección**: LEFT JOIN + WHERE sobre tabla right (sin IS NULL)  
**Ejemplo**: `LEFT JOIN tabla_b ... WHERE b.saldo > 0`  
**Impacto**: Plan de ejecución subóptimo  
**Sugerencia**: Cambiar a INNER JOIN explícito

### R04 - CAST en condición de JOIN (CRITICAL)
**Problema**: CAST de columna en condición ON del JOIN  
**Detección**: `ParsedJoin.has_cast == True`  
**Impacto**: Impide uso de estadísticas, causa shuffle masivo  
**Sugerencia**: Precalcular en CTE o ajustar tipos en DDL

### R05 - Escalar casteado a tipo diferente (WARNING)
**Problema**: CAST de escalar a tipo diferente  
**Estado**: Placeholder - requiere análisis de tipos  
**TODO**: Implementar cuando se disponga de metadatos de tipos

### R06 - Función en condición de JOIN (WARNING)
**Problema**: CONCAT, SUBSTRING, etc. en condición ON  
**Detección**: `ParsedJoin.has_function == True`  
**Impacto**: Se evalúa por cada combinación de filas  
**Sugerencia**: Precalcular en CTE

### R07 - REPLACE múltiples anidados (WARNING)
**Problema**: Más de 2 REPLACE anidados  
**Detección**: `ParsedQuery.replace_chain_count > 2`  
**Impacto**: Difícil de leer y mantener  
**Sugerencia**: Usar REGEXP_REPLACE o CTEs intermedias

### R08 - MAX(fecha_*) repetido (WARNING)
**Problema**: Mismo MAX() sobre fecha en múltiples lugares  
**Detección**: `ParsedQuery.max_fecha_count > 1`  
**Impacto**: N full scans en lugar de 1  
**Sugerencia**: Calcular una vez en CTE y referenciar con CROSS JOIN

### R09 - Full scan sin filtro de partición (CRITICAL)
**Problema**: Tabla sin WHERE en columna de partición  
**Detección**: Comparar con columnas PARTITIONED BY del DDL  
**Impacto**: Lee billones de registros innecesariamente  
**Sugerencia**: Agregar filtro WHERE sobre partición  
**Nota**: Solo se dispara si se provee DDL

### R10 - Lógica condicional en JOIN (WARNING)
**Problema**: CASE, IF, COALESCE en condición ON  
**Detección**: Palabras clave en condición de JOIN  
**Impacto**: Se evalúa por cada combinación  
**Sugerencia**: Precalcular en CTE

### R11 - CAST en ambos lados del JOIN (CRITICAL)
**Problema**: Ambos lados de = tienen CAST  
**Detección**: `ParsedJoin.cast_both_sides == True`  
**Impacto**: Impide cualquier optimización  
**Sugerencia**: Precalcular ambos lados en CTEs

### R12 - Subquery correlacionada en SELECT (WARNING)
**Problema**: Subquery en SELECT que referencia outer query  
**Detección**: `ParsedQuery.subqueries_in_select > 0`  
**Impacto**: Se ejecuta una vez por cada fila  
**Sugerencia**: Mover a LEFT JOIN

## Uso

```python
from backend.analyzer.sql_parser import parse_query
from backend.analyzer.rules_engine import run_all_rules

# Parsear query
parsed = parse_query(sql)

# Ejecutar reglas (DDL opcional para R09)
findings = run_all_rules(parsed, ddl=ddl_text)

# Procesar findings
for finding in findings:
    print(f"[{finding.severity.upper()}] {finding.rule_name}")
    print(f"  {finding.description}")
    print(f"  Sugerencia: {finding.suggestion}")
```

## Severidades

- **CRITICAL**: Impacto directo en performance, puede causar timeouts
  - R02, R03, R04, R09, R11
  
- **WARNING**: Impacto moderado o problemas de mantenibilidad
  - R01, R06, R07, R08, R10, R12
  
- **INFO**: Recomendaciones generales (ninguna por ahora)

## Output

Cada finding incluye:
- `rule_id`: ID único (R01-R12)
- `rule_name`: Nombre descriptivo
- `severity`: critical/warning/info
- `description`: Explicación del problema específico encontrado
- `location`: Dónde en la query está el problema
- `suggestion`: Cómo solucionarlo
- `code_before`: Fragmento original (cuando aplique)
- `code_after`: Fragmento sugerido (cuando aplique)

## Extensibilidad

Para agregar una nueva regla:

1. Crear función `rXX_nombre(parsed: ParsedQuery) -> list[RuleFinding]`
2. Agregar a `run_all_rules()`
3. Documentar en este README

## Testing

Ver `backend/analyzer/sql_parser.py` para query de test completa que dispara la mayoría de las reglas.
