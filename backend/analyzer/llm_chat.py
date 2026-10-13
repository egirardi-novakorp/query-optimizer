"""
Chat conversacional con el LLM para guiar al usuario.
"""

import google.generativeai as genai
from backend.config import settings
from typing import Optional
import json


# System prompt para el chat conversacional
CHAT_SYSTEM_PROMPT = """
Sos el asistente del Novakorp Query Optimizer, una herramienta de análisis de queries 
Impala/Hive para Novakorp Data & Analytics.

IMPORTANTE: Respondé SIEMPRE de forma CONCISA y DIRECTA.
- Máximo 3-4 oraciones por respuesta
- Sin listas ni bullets
- Directo al punto
- Si necesitas dar más detalle, sugerir que descargue el PDF del último análisis

Tu rol:
1. Si el usuario pega SQL, decile que lo estás analizando.
2. Si pregunta sobre un análisis, resumí lo más importante en 2-3 oraciones.
3. Si pregunta por una regla específica (R01, R04, etc), explicala brevemente con un ejemplo corto.
4. Si necesita más detalle, recordale que puede descargar el PDF completo.

REGLAS CLAVE:
- R01: CTE innecesaria (usada 1 vez) → inlinear
- R02: SELECT * → especificar columnas
- R03: LEFT JOIN que es INNER → cambiar a INNER JOIN
- R04: CAST en JOIN → impide estadísticas
- R06: Función en JOIN → muy costoso
- R08: MAX(fecha) repetido → calcular 1 vez
- R09: Full scan sin partición → agregar WHERE fecha_proceso
- R11: CAST en ambos lados JOIN → extremadamente costoso
- R12: Subquery correlacionada → LEFT JOIN

Tono: amigable, profesional, conciso. Español rioplatense.
"""


async def chat_with_llm(
    message: str,
    history: list[dict],
    last_analysis: Optional[dict] = None,
    ddl: Optional[str] = None,
    explain_plan: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """
    Chat conversacional con el LLM.
    
    Args:
        message: Mensaje del usuario
        history: Historial de conversación
        last_analysis: Último análisis para contexto
        ddl: DDL opcional
        explain_plan: EXPLAIN opcional
        context: Contexto opcional
    
    Returns:
        Respuesta del LLM
    """
    try:
        # Configurar Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # Construir prompt con contexto
        prompt = _build_chat_prompt(
            message, 
            history, 
            last_analysis, 
            ddl, 
            explain_plan, 
            context
        )
        
        # Llamar a Gemini
        model = genai.GenerativeModel(
            'gemini-3.8-flash',
            generation_config={
                "temperature": 0.7,  # Más temperatura para conversación natural
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
        )
        
        # Generar respuesta
        response = await model.generate_content_async(
            [CHAT_SYSTEM_PROMPT, prompt],
            request_options={"timeout": 30}
        )
        
        return response.text
        
    except Exception as e:
        return f"Disculpá, tuve un error al procesar tu mensaje: {str(e)}"


def _build_chat_prompt(
    message: str,
    history: list[dict],
    last_analysis: Optional[dict],
    ddl: Optional[str],
    explain_plan: Optional[str],
    context: Optional[str],
) -> str:
    """Construye el prompt con todo el contexto."""
    parts = []
    
    # Historial de conversación (últimos 10 mensajes)
    if history:
        parts.append("## HISTORIAL DE CONVERSACIÓN:\n")
        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Truncar mensajes muy largos
            if len(content) > 200:
                content = content[:200] + "..."
            
            parts.append(f"{role.upper()}: {content}\n")
        parts.append("\n")
    
    # Último análisis
    if last_analysis:
        parts.append("## ÚLTIMO ANÁLISIS REALIZADO:\n")
        
        # Summary
        summary = last_analysis.get("summary", {})
        parts.append(f"Críticos: {summary.get('critical', 0)}, ")
        parts.append(f"Warnings: {summary.get('warning', 0)}, ")
        parts.append(f"Info: {summary.get('info', 0)}\n\n")
        
        # Findings
        findings = last_analysis.get("findings", [])
        if findings:
            parts.append("Hallazgos principales:\n")
            for finding in findings[:5]:  # Top 5
                parts.append(f"- [{finding.get('rule_id')}] {finding.get('rule_name')}: ")
                parts.append(f"{finding.get('description')[:100]}...\n")
        
        parts.append("\n")
    
    # Información disponible
    has_ddl = ddl and ddl.strip()
    has_explain = explain_plan and explain_plan.strip()
    has_context = context and context.strip()
    
    if has_ddl or has_explain or has_context:
        parts.append("## INFORMACIÓN ADICIONAL DISPONIBLE:\n")
        if has_ddl:
            parts.append("- DDL de tablas: Sí\n")
        if has_explain:
            parts.append("- EXPLAIN plan: Sí\n")
        if has_context:
            parts.append(f"- Contexto: {context[:100]}...\n")
        parts.append("\n")
    
    # Mensaje actual
    parts.append("## MENSAJE DEL USUARIO:\n")
    parts.append(message)
    parts.append("\n\n")
    
    # Instrucción
    parts.append("Respondé al usuario de manera útil y concisa.")
    
    return "".join(parts)


def is_sql_query(text: str) -> bool:
    """
    Detecta si el texto es una query SQL.
    
    Criterios:
    - Contiene keywords SQL (SELECT, WITH, INSERT, etc.)
    - Tiene más de 20 caracteres
    - Keywords al inicio o después de whitespace
    """
    if not text or len(text.strip()) < 20:
        return False
    
    text_upper = text.upper().strip()
    
    # Keywords SQL comunes
    sql_keywords = [
        'SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE',
        'CREATE', 'ALTER', 'DROP', 'TRUNCATE'
    ]
    
    # Verificar si empieza con keyword SQL
    for keyword in sql_keywords:
        if text_upper.startswith(keyword):
            return True
        # O si tiene keyword después de whitespace al inicio
        if text_upper.startswith('\n') or text_upper.startswith(' '):
            stripped = text_upper.lstrip()
            if stripped.startswith(keyword):
                return True
    
    return False
