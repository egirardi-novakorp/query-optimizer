# Test de Integración Completa

## Pipeline Completo Implementado

```
Query SQL → Parser → Reglas → EXPLAIN → LLM → Response
```

## Test Manual (POST a la API)

### 1. Iniciar el backend

```bash
# Opción A: Docker
docker-compose up

# Opción B: Local
uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Test con curl

```bash
curl -X POST http://localhost:8001/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "query": "WITH max_fecha AS (SELECT MAX(fecha_proceso) AS fp FROM db.tabla_grande) SELECT * FROM max_fecha",
    "ddl": null,
    "explain_plan": null,
    "context": "Query para obtener la fecha más reciente"
  }'
```

### 3. Test con Python

```python
import httpx

response = httpx.post(
    "http://localhost:8001/api/analyze",
    json={
        "query": """
        WITH max_fecha AS (
            SELECT MAX(fecha_proceso) AS fp FROM db.tabla_grande
        ),
        datos AS (
            SELECT * FROM db.tabla a
            CROSS JOIN max_fecha mf
            WHERE a.fecha_proceso = mf.fp
        )
        SELECT * FROM datos
        """,
        "ddl": None,
        "explain_plan": None,
        "context": "Esta query se ejecuta cada hora"
    },
    timeout=60.0
)

result = response.json()
print(f"Findings: {len(result['findings'])}")
print(f"Summary: {result['summary']}")
print(f"\nLLM Analysis:\n{result['llm_analysis']}")
if result['optimized_query']:
    print(f"\nOptimized Query:\n{result['optimized_query']}")
```

## Respuesta Esperada

```json
{
  "original_query": "WITH max_fecha AS...",
  "optimized_query": "SELECT... (o null)",
  "findings": [
    {
      "rule_id": "R01",
      "rule_name": "CTE innecesaria",
      "severity": "warning",
      "description": "La CTE 'max_fecha' solo se usa 1 vez...",
      "location": "CTE 'max_fecha'",
      "suggestion": "Considerar inlinear esta CTE...",
      "code_before": "WITH max_fecha AS...",
      "code_after": "-- Inlinear en FROM..."
    },
    {
      "rule_id": "R02",
      "rule_name": "SELECT * detectado",
      "severity": "critical",
      "description": "El uso de SELECT * trae todas las columnas...",
      "location": "SELECT #2",
      "suggestion": "Especificar explícitamente...",
      "code_before": "SELECT *",
      "code_after": "SELECT \n  columna1,\n  columna2"
    }
  ],
  "summary": {
    "critical": 1,
    "warning": 1,
    "info": 0
  },
  "llm_analysis": "### Análisis de la Query\n\nLa query...",
  "explain_analysis": null
}
```

## Test con EXPLAIN Plan

```python
response = httpx.post(
    "http://localhost:8001/api/analyze",
    json={
        "query": "SELECT a.id FROM tabla_a a JOIN tabla_b b ON a.id = b.id",
        "explain_plan": """
        PLAN-ROOT SINK
        |
        04:HASH JOIN [INNER JOIN, BROADCAST]
        |  hash predicates: a.id = b.id
        |  mem-estimate=2.00GB
        |  cardinality=10000000
        |
        |--03:EXCHANGE [BROADCAST]
        |  |  mem-estimate=500.00MB
        |  |
        |  02:SCAN HDFS [db.tabla_b b]
        |     HDFS partitions=1/1 files=100 size=10GB
        |     cardinality=1000000
        |
        01:SCAN HDFS [db.tabla_a a]
           HDFS partitions=365/365 files=3650 size=1TB
           predicates: a.fecha_proceso = '2024-01-01'
           cardinality=10000000
        """,
        "context": None
    }
)

result = response.json()
print(result['explain_analysis'])
```

**Output esperado:**

```
[MEM] **Memoria Estimada:** 2.50 GB total

[JOIN] **HASH JOINs:** 1 detectados

[BROADCAST] **BROADCAST JOINs:** 1 detectados
   (Tabla pequeña se broadcast a todos los nodos)

[SHUFFLE] **Shuffles de Red:** 1 EXCHANGE detectados

[ROWS] **Estimacion de Filas:**
   - Máximo de filas procesadas: 10,000,000 (>1M)
```

## Test de Manejo de Errores

### Error de Parsing

```python
response = httpx.post(
    "http://localhost:8001/api/analyze",
    json={"query": "SELEC * FORM tabla"}  # SQL inválido
)

result = response.json()
assert result['findings'][0]['rule_id'] == 'E00'
assert result['findings'][0]['rule_name'] == 'Error de parsing'
```

### Error de LLM (sin API key o timeout)

Si el LLM falla:
- Los findings de reglas se retornan igual
- `llm_analysis` contiene mensaje de error
- `optimized_query` es null
- Status HTTP 200 (no es error de API)

## Verificación de Componentes

### ✅ Parser SQL
```bash
python backend/analyzer/sql_parser.py
```

### ✅ Rules Engine
```bash
python -c "
from backend.analyzer.sql_parser import parse_query
from backend.analyzer.rules_engine import run_all_rules
parsed = parse_query('SELECT * FROM tabla')
findings = run_all_rules(parsed)
print(f'{len(findings)} findings')
"
```

### ✅ EXPLAIN Analyzer
```bash
python -c "
from backend.analyzer.explain_analyzer import analyze_explain
result = analyze_explain('SCAN HDFS [tabla] cardinality=1000000')
print(result)
"
```

### ✅ LLM Analyzer (requiere API key)
```bash
python -c "
import asyncio
from backend.analyzer.llm_analyzer import llm_analyze
result = asyncio.run(llm_analyze('SELECT * FROM tabla', []))
print(result['analysis'][:100])
"
```

## Frontend

Acceder a http://localhost:8502

1. Pegar query SQL
2. Click en "Analizar"
3. Ver JSON con findings, analysis, etc.

## Métricas de Performance

Para queries típicas:
- Parser: < 1s
- Reglas: < 0.5s
- EXPLAIN: < 0.1s
- LLM: 5-15s (depende de Gemini API)
- **Total**: 5-17s

## Troubleshooting

### "No module named 'google.generativeai'"
```bash
pip install google-generativeai
```

### "Error al conectar con el LLM"
- Verificar GEMINI_API_KEY en .env
- Verificar conectividad a internet
- Verificar rate limits de Gemini API

### "Error de parsing"
- Verificar que la query sea Hive/Impala válida
- Verificar sintaxis SQL

## Logs

Para ver logs detallados:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

Los logs incluyen:
- Inicio/fin de cada paso del pipeline
- Errores de parsing, reglas, LLM
- Tiempos de ejecución
