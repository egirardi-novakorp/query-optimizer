"""
Análisis de queries usando Gemini.
Provee análisis contextual y queries optimizadas sugeridas.
"""

import json
import re
from typing import Optional
import google.generativeai as genai
from backend.config import settings
from backend.api.models import RuleFinding

# System prompt para Gemini
SYSTEM_PROMPT = """
Sos un experto en optimización de queries Impala/Hive para entornos de Data Lake 
con tablas de billones de registros en Grupo Petersen.

Tu rol es analizar queries SQL y sugerir optimizaciones. Recibís:
1. La query SQL original
2. Hallazgos del análisis estático (reglas determinísticas ya ejecutadas)
3. Opcionalmente: DDL de tablas y EXPLAIN plan

REGLAS CRÍTICAS:
- Los resultados de la query optimizada DEBEN ser idénticos a la original.
- Si no podés garantizar equivalencia, marcalo como WARNING.
- Siempre explicá POR QUÉ cada cambio mejora el rendimiento.
- Si necesitás información que no tenés (tamaño de tablas, etc), pedila al usuario.
- Preferí cambios conservadores sobre agresivos.
- Para JOINs: castear escalares al tipo de la columna de la tabla grande, nunca al revés.
- Para filtros de partición: siempre filtrar por fecha_proceso cuando exista.

FORMATO DE RESPUESTA (JSON estricto):
{
  "analysis": "Análisis textual de la query, problemas detectados y recomendaciones generales",
  "optimized_query": "SELECT ... (la query optimizada completa) o null si no hay mejora clara",
  "changes": [
    {"change": "Descripción del cambio", "reason": "Por qué mejora el rendimiento"}
  ],
  "warnings": ["Cosas que no se pueden validar sin más contexto"],
  "questions": ["Preguntas para el usuario si necesitás más info"]
}
"""


async def llm_analyze(
    query: str,
    findings: list[RuleFinding],
    ddl: Optional[str] = None,
    explain_plan: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    """
    Analiza la query con Gemini y retorna análisis + query optimizada.
    
    Args:
        query: Query SQL original
        findings: Lista de hallazgos de reglas determinísticas
        ddl: DDL opcional de las tablas
        explain_plan: Plan EXPLAIN opcional
        context: Contexto adicional del usuario
    
    Returns:
        Dict con analysis, optimized_query, changes, warnings, questions
    """
    
    try:
        # Configurar Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Construir el prompt
        prompt = _build_prompt(query, findings, ddl, explain_plan, context)
        
        # Llamar a Gemini
        model = genai.GenerativeModel(
            'gemini-3.8-flash',
            generation_config={
                "temperature": 0.2,  # Baja temperatura para respuestas más determinísticas
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        
        # Generar respuesta
        response = await model.generate_content_async(
            [SYSTEM_PROMPT, prompt],
            request_options={"timeout": 60}
        )
        
        # Parsear respuesta JSON
        result = _parse_llm_response(response.text)
        
        return result
        
    except Exception as e:
        # Si falla, retornar estructura básica con error
        return {
            "analysis": f"Error al conectar con el LLM: {str(e)}",
            "optimized_query": None,
            "changes": [],
            "warnings": [f"No se pudo obtener análisis del LLM: {str(e)}"],
            "questions": []
        }


def _build_prompt(
    query: str,
    findings: list[RuleFinding],
    ddl: Optional[str],
    explain_plan: Optional[str],
    context: Optional[str]
) -> str:
    """
    Construye el prompt para Gemini con toda la información disponible.
    """
    
    prompt_parts = []
    
    # Query original
    prompt_parts.append("## QUERY SQL A ANALIZAR:\n")
    prompt_parts.append("```sql\n" + query + "\n```\n")
    
    # Findings de reglas determinísticas
    if findings:
        prompt_parts.append("\n## HALLAZGOS DEL ANÁLISIS ESTÁTICO:\n")
        
        # Agrupar por severidad
        critical = [f for f in findings if f.severity == "critical"]
        warning = [f for f in findings if f.severity == "warning"]
        
        if critical:
            prompt_parts.append("\n### CRITICAL:\n")
            for f in critical:
                prompt_parts.append(f"- [{f.rule_id}] {f.rule_name}\n")
                prompt_parts.append(f"  Location: {f.location}\n")
                prompt_parts.append(f"  {f.description}\n")
                prompt_parts.append(f"  Sugerencia: {f.suggestion}\n")
        
        if warning:
            prompt_parts.append("\n### WARNING:\n")
            for f in warning:
                prompt_parts.append(f"- [{f.rule_id}] {f.rule_name}\n")
                prompt_parts.append(f"  Location: {f.location}\n")
                prompt_parts.append(f"  {f.description}\n")
    
    # DDL de tablas
    if ddl:
        prompt_parts.append("\n## DDL DE TABLAS:\n")
        prompt_parts.append("```sql\n" + ddl + "\n```\n")
    
    # EXPLAIN plan
    if explain_plan:
        prompt_parts.append("\n## EXPLAIN PLAN:\n")
        prompt_parts.append("```\n" + explain_plan + "\n```\n")
    
    # Contexto adicional
    if context:
        prompt_parts.append("\n## CONTEXTO ADICIONAL:\n")
        prompt_parts.append(context + "\n")
    
    # Instrucciones finales
    prompt_parts.append("\n## INSTRUCCIONES:\n")
    prompt_parts.append("Analiza la query y los hallazgos. ")
    prompt_parts.append("Propone una query optimizada si hay mejoras claras. ")
    prompt_parts.append("Responde ÚNICAMENTE con JSON válido en el formato especificado.\n")
    
    return "".join(prompt_parts)


def _parse_llm_response(response_text: str) -> dict:
    """
    Parsea la respuesta del LLM, limpiando markdown fences si existen.
    """
    
    # Limpiar markdown fences (```json ... ```)
    cleaned = response_text.strip()
    
    # Remover ```json al inicio
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    
    # Remover ``` al final
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    
    cleaned = cleaned.strip()
    
    try:
        # Intentar parsear JSON
        result = json.loads(cleaned)
        
        # Validar estructura mínima
        if not isinstance(result, dict):
            raise ValueError("Response is not a dict")
        
        # Asegurar campos requeridos
        result.setdefault("analysis", "")
        result.setdefault("optimized_query", None)
        result.setdefault("changes", [])
        result.setdefault("warnings", [])
        result.setdefault("questions", [])
        
        return result
        
    except json.JSONDecodeError as e:
        # Si falla el parseo, retornar texto crudo
        return {
            "analysis": response_text,
            "optimized_query": None,
            "changes": [],
            "warnings": [f"No se pudo parsear respuesta JSON del LLM: {str(e)}"],
            "questions": []
        }


def llm_analyze_sync(
    query: str,
    findings: list[RuleFinding],
    ddl: Optional[str] = None,
    explain_plan: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    """
    Versión sincrónica del analizador LLM (para testing).
    """
    
    try:
        # Configurar Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Construir el prompt
        prompt = _build_prompt(query, findings, ddl, explain_plan, context)
        
        # Llamar a Gemini
        model = genai.GenerativeModel(
            'gemini-3.8-flash',
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        
        # Generar respuesta (sincrónica)
        response = model.generate_content([SYSTEM_PROMPT, prompt])
        
        # Parsear respuesta JSON
        result = _parse_llm_response(response.text)
        
        return result
        
    except Exception as e:
        return {
            "analysis": f"Error al conectar con el LLM: {str(e)}",
            "optimized_query": None,
            "changes": [],
            "warnings": [f"No se pudo obtener análisis del LLM: {str(e)}"],
            "questions": []
        }
