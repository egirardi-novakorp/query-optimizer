from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from backend.api.models import AnalyzeRequest, AnalyzeResponse, ChatRequest, ChatResponse
from backend.analyzer.agent import analyze_query
from backend.analyzer.llm_chat import chat_with_llm, is_sql_query
from backend.db.history import save_analysis, get_history, get_analysis_by_id
from backend.export.pdf_generator import generate_analysis_pdf
from datetime import datetime
import io
import base64

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_sql(request: AnalyzeRequest):
    """
    Analiza una query SQL y retorna hallazgos, análisis LLM y query optimizada.
    Guarda automáticamente el resultado en el historial.
    """
    try:
        result = await analyze_query(request)
        
        # Guardar en historial
        try:
            analysis_id = save_analysis(request.query, result.model_dump())
            # Agregar ID al resultado (no está en el modelo pero es útil)
            result_dict = result.model_dump()
            result_dict["analysis_id"] = analysis_id
            return result_dict
        except Exception as e:
            # Si falla guardar en historial, no fallar el análisis
            print(f"Warning: Failed to save analysis to history: {e}")
            return result
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_analysis_history(limit: int = 20, offset: int = 0):
    """
    Obtiene el historial de análisis.
    
    Query params:
        - limit: Número de registros (default 20, max 100)
        - offset: Offset para paginación (default 0)
    """
    try:
        if limit > 100:
            limit = 100
        
        history = get_history(limit=limit, offset=offset)
        return {
            "history": history,
            "count": len(history),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{analysis_id}")
async def get_analysis_detail(analysis_id: int):
    """
    Obtiene el detalle completo de un análisis específico.
    """
    try:
        analysis = get_analysis_by_id(analysis_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/pdf")
async def analyze_and_generate_pdf(request: AnalyzeRequest):
    """
    Analiza una query SQL y genera un reporte en PDF.
    
    Ejecuta el mismo análisis que /api/analyze pero retorna un PDF
    en lugar de JSON.
    """
    try:
        # 1. Ejecutar análisis
        result = await analyze_query(request)
        
        # 2. Generar PDF
        pdf_bytes = generate_analysis_pdf(result)
        
        # 3. Retornar como streaming response
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"query-analysis-{timestamp}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Endpoint conversacional que detecta si el mensaje es SQL o chat.
    
    - Si es SQL: ejecuta análisis completo y genera PDF automáticamente
    - Si es conversación: responde con el LLM
    """
    try:
        # Detectar si es query SQL
        if is_sql_query(request.message):
            # Es una query SQL → ejecutar análisis completo
            analyze_request = AnalyzeRequest(
                query=request.message,
                ddl=request.ddl,
                explain_plan=request.explain_plan,
                context=request.context
            )
            
            analysis_result = await analyze_query(analyze_request)
            
            # Guardar en historial
            try:
                save_analysis(request.message, analysis_result.model_dump())
            except Exception as e:
                print(f"Warning: Failed to save analysis: {e}")
            
            # Generar PDF automáticamente
            pdf_base64 = None
            try:
                pdf_bytes = generate_analysis_pdf(analysis_result)
                pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            except Exception as e:
                print(f"Warning: Failed to generate PDF: {e}")
            
            return ChatResponse(
                type="analysis",
                analysis=analysis_result,
                message=None,
                pdf_base64=pdf_base64
            )
        else:
            # Es conversación → chat con LLM
            response_message = await chat_with_llm(
                message=request.message,
                history=request.history,
                last_analysis=request.last_analysis,
                ddl=request.ddl,
                explain_plan=request.explain_plan,
                context=request.context
            )
            
            return ChatResponse(
                type="chat",
                analysis=None,
                message=response_message,
                pdf_base64=None
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
