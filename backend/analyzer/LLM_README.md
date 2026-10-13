# Analizador LLM - Gemini

Integración con Gemini para análisis contextual y generación de queries optimizadas.

## Configuración

### Variables de Entorno

Configurar `GEMINI_API_KEY` en el archivo `.env`:

```bash
GEMINI_API_KEY=tu_api_key_aqui
```

### Obtener API Key

1. Ir a https://aistudio.google.com/apikey
2. Crear o copiar la API key
3. Agregar al `.env`

## Uso

### Desde el Agente (Automático)

El agente orquesta automáticamente todo el pipeline:

```python
from backend.analyzer.agent import analyze_query
from backend.api.models import AnalyzeRequest

request = AnalyzeRequest(
    query="SELECT * FROM tabla WHERE ...",
    ddl="CREATE TABLE ...",  # Opcional
    explain_plan="EXPLAIN output...",  # Opcional
    context="Contexto adicional..."  # Opcional
)

response = await analyze_query(request)

# Acceder a resultados
print(response.llm_analysis)        # Análisis textual del LLM
print(response.optimized_query)     # Query optimizada (o None)
print(response.findings)            # Hallazgos de reglas determinísticas
print(response.explain_analysis)    # Análisis del EXPLAIN plan
```

### Directamente (Para Testing)

```python
from backend.analyzer.llm_analyzer import llm_analyze
from backend.analyzer.rules_engine import run_all_rules
from backend.analyzer.sql_parser import parse_query

# 1. Parsear y analizar
parsed = parse_query(sql)
findings = run_all_rules(parsed)

# 2. Llamar al LLM
result = await llm_analyze(
    query=sql,
    findings=findings,
    ddl=ddl,
    explain_plan=explain_plan,
    context=context
)

# 3. Acceder a resultados
print(result["analysis"])           # Análisis textual
print(result["optimized_query"])    # Query optimizada
print(result["changes"])            # Lista de cambios sugeridos
print(result["warnings"])           # Advertencias del LLM
print(result["questions"])          # Preguntas para el usuario
```

## System Prompt

El LLM recibe un system prompt especializado que le indica:

- **Rol**: Experto en optimización Impala/Hive para Data Lake
- **Reglas críticas**:
  - Resultados DEBEN ser idénticos a la original
  - Explicar POR QUÉ cada cambio mejora performance
  - Preferir cambios conservadores
  - Para JOINs: castear escalares, no columnas de tablas grandes
  - Siempre filtrar por fecha_proceso cuando exista

## Formato de Respuesta

El LLM retorna JSON estructurado:

```json
{
  "analysis": "Análisis textual completo...",
  "optimized_query": "SELECT ... (o null)",
  "changes": [
    {
      "change": "Descripción del cambio",
      "reason": "Por qué mejora el rendimiento"
    }
  ],
  "warnings": [
    "Cosas que no se pueden validar sin más contexto"
  ],
  "questions": [
    "¿Cuál es el tamaño de la tabla X?",
    "¿Esta query se ejecuta diariamente?"
  ]
}
```

## Manejo de Errores

Si el LLM falla (timeout, API error, etc.):

- El agente retorna los hallazgos de reglas determinísticas de todos modos
- `llm_analysis` contiene el mensaje de error
- `optimized_query` es `null`
- El usuario obtiene análisis parcial pero útil

## Configuración del Modelo

```python
model = genai.GenerativeModel(
    'gemini-3.8-flash',
    generation_config={
        "temperature": 0.2,      # Baja para respuestas determinísticas
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 8192,
    }
)
```

## Prompt Building

El prompt incluye:

1. **Query SQL** (en code block)
2. **Hallazgos de reglas** (agrupados por severidad)
3. **DDL de tablas** (si se provee)
4. **EXPLAIN plan** (si se provee)
5. **Contexto adicional** (si se provee)
6. **Instrucciones finales**

## Ejemplos de Uso

### Ejemplo 1: Análisis Básico

```python
result = await llm_analyze(
    query="SELECT * FROM tabla WHERE fecha = '2024-01-01'",
    findings=findings
)
```

### Ejemplo 2: Con DDL

```python
result = await llm_analyze(
    query=sql,
    findings=findings,
    ddl="""
    CREATE TABLE db.tabla_grande (
        id BIGINT,
        nombre STRING
    )
    PARTITIONED BY (fecha_proceso STRING)
    """
)
```

### Ejemplo 3: Con EXPLAIN y Contexto

```python
result = await llm_analyze(
    query=sql,
    findings=findings,
    explain_plan=explain_output,
    context="Esta query se ejecuta cada hora y tarda 45 minutos"
)
```

## Limitaciones

### Current Issues

⚠️  **Deprecation Warning**: El paquete `google-generativeai` está deprecated. 
Future version debería migrar a `google-genai`.

### Rate Limits

Gemini API tiene límites de:
- **RPM** (Requests Per Minute)
- **TPM** (Tokens Per Minute)

Ver: https://ai.google.dev/gemini-api/docs/models/gemini#rate-limits

### Token Limits

- Input: Depende del modelo
- Output: Configurado en 8192 tokens

## Testing

Para testing sin consumir API calls, usar mocks:

```python
from unittest.mock import patch

with patch('google.generativeai.GenerativeModel') as mock_model:
    mock_model.return_value.generate_content_async.return_value.text = '''
    {
        "analysis": "Test analysis",
        "optimized_query": null,
        "changes": [],
        "warnings": [],
        "questions": []
    }
    '''
    
    result = await llm_analyze(query, findings)
    assert result["analysis"] == "Test analysis"
```

## Debugging

Habilitar logging:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

El agente loggea:
- Inicio de cada paso del pipeline
- Errores de LLM
- Resumen de findings

## Mejoras Futuras

- [ ] Migrar a `google.genai`
- [ ] Cache de respuestas para queries similares
- [ ] Streaming de respuesta para UX mejorada
- [ ] Soporte para múltiples modelos (Claude, GPT-4)
- [ ] Fine-tuning con queries reales de Grupo Petersen
- [ ] Feedback loop para mejorar sugerencias
