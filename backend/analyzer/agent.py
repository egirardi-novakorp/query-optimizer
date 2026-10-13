from backend.api.models import AnalyzeRequest, AnalyzeResponse, RuleFinding
from backend.analyzer.sql_parser import parse_query
from backend.analyzer.rules_engine import run_all_rules
from backend.analyzer.explain_analyzer import analyze_explain
from backend.analyzer.llm_analyzer import llm_analyze
import logging

logger = logging.getLogger(__name__)


async def analyze_query(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Orquestador principal del análisis de queries.
    
    Pipeline completo:
    1. Parsear SQL con sqlglot (sql_parser.py)
    2. Ejecutar reglas determinísticas (rules_engine.py)
    3. Analizar EXPLAIN plan si existe (explain_analyzer.py)
    4. Enviar a LLM para análisis contextual (llm_analyzer.py)
    5. Extraer query optimizada del resultado LLM
    
    Maneja errores gracefully: si algún paso falla, retorna lo que se pudo analizar.
    """
    
    # 1. Parsear la query SQL
    logger.info("Paso 1: Parseando query SQL...")
    parsed = parse_query(request.query)
    
    # Si hubo errores de parsing, retornar temprano
    if parsed.errors:
        logger.error(f"Error de parsing: {parsed.errors}")
        return AnalyzeResponse(
            original_query=request.query,
            optimized_query=None,
            findings=[
                RuleFinding(
                    rule_id="E00",
                    rule_name="Error de parsing",
                    severity="critical",
                    description=f"No se pudo parsear la query: {'; '.join(parsed.errors)}",
                    location="Query completa",
                    suggestion="Verificar la sintaxis SQL. Asegurar que sea Hive/Impala válido.",
                    code_before="",
                    code_after=""
                )
            ],
            summary={"critical": 1, "warning": 0, "info": 0},
            llm_analysis=None,
            explain_analysis=None
        )
    
    # 2. Ejecutar reglas determinísticas
    logger.info("Paso 2: Ejecutando reglas determinísticas...")
    findings = run_all_rules(parsed, ddl=request.ddl)
    
    # 3. Calcular summary
    summary = {
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info")
    }
    
    logger.info(f"Findings: {summary['critical']} critical, {summary['warning']} warning")
    
    # 4. Analizar EXPLAIN plan si existe
    explain_analysis = None
    if request.explain_plan:
        try:
            logger.info("Paso 3: Analizando EXPLAIN plan...")
            explain_analysis = analyze_explain(request.explain_plan)
        except Exception as e:
            logger.error(f"Error analizando EXPLAIN plan: {e}")
            explain_analysis = f"Error al analizar EXPLAIN plan: {str(e)}"
    
    # 5. Enviar a LLM para análisis contextual y query optimizada
    llm_analysis = None
    optimized_query = None
    
    try:
        logger.info("Paso 4: Llamando a LLM (Gemini)...")
        
        llm_result = await llm_analyze(
            query=request.query,
            findings=findings,
            ddl=request.ddl,
            explain_plan=request.explain_plan,
            context=request.context
        )
        
        # Extraer análisis y query optimizada
        llm_analysis = llm_result.get("analysis", "")
        optimized_query = llm_result.get("optimized_query")
        
        # Agregar cambios sugeridos al análisis si existen
        if llm_result.get("changes"):
            llm_analysis += "\n\n### Cambios Sugeridos:\n"
            for change in llm_result["changes"]:
                llm_analysis += f"- **{change.get('change')}**\n"
                llm_analysis += f"  Razón: {change.get('reason')}\n"
        
        # Agregar warnings si existen
        if llm_result.get("warnings"):
            llm_analysis += "\n\n### Advertencias:\n"
            for warning in llm_result["warnings"]:
                llm_analysis += f"- {warning}\n"
        
        # Agregar preguntas si existen
        if llm_result.get("questions"):
            llm_analysis += "\n\n### Preguntas para el Usuario:\n"
            for question in llm_result["questions"]:
                llm_analysis += f"- {question}\n"
        
        logger.info("LLM analysis completado exitosamente")
        
    except Exception as e:
        logger.error(f"Error llamando al LLM: {e}")
        llm_analysis = f"⚠️  Error al conectar con el LLM: {str(e)}\n\n"
        llm_analysis += "Los hallazgos de reglas determinísticas están disponibles arriba."
        optimized_query = None
    
    # 6. Retornar respuesta completa
    return AnalyzeResponse(
        original_query=request.query,
        optimized_query=optimized_query,
        findings=findings,
        summary=summary,
        llm_analysis=llm_analysis,
        explain_analysis=explain_analysis
    )
