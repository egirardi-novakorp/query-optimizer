"""
Generador de reportes en PDF para análisis de queries.
"""

from fpdf import FPDF
from datetime import datetime
from backend.api.models import AnalyzeResponse, RuleFinding


class QueryAnalysisPDF(FPDF):
    """PDF personalizado para reportes de análisis."""
    
    def header(self):
        """Header del PDF."""
        # Logo/Title
        self.set_font('Arial', 'B', 16)
        self.set_text_color(41, 128, 185)  # Azul
        self.cell(0, 10, 'GP Query Optimizer - Reporte de Analisis', 0, 1, 'C')
        
        # Fecha
        self.set_font('Arial', '', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, f'Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        
        # Línea
        self.set_draw_color(200, 200, 200)
        self.line(10, 30, 200, 30)
        self.ln(5)
    
    def footer(self):
        """Footer del PDF."""
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, 'Generado por GP Query Optimizer - Grupo Petersen Data & Analytics', 0, 0, 'C')


def generate_analysis_pdf(analysis: AnalyzeResponse) -> bytes:
    """
    Genera un PDF con el análisis completo.
    
    Args:
        analysis: Respuesta del análisis a exportar
    
    Returns:
        Bytes del PDF generado
    """
    pdf = QueryAnalysisPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    # 1. Resumen con métricas
    _add_summary(pdf, analysis.summary)
    
    # 2. Query Original
    _add_query_section(pdf, "Query Original", analysis.original_query)
    
    # 3. Hallazgos
    if analysis.findings:
        _add_findings_section(pdf, analysis.findings)
    
    # 4. Análisis LLM
    if analysis.llm_analysis:
        _add_text_section(pdf, "Analisis Detallado (LLM)", analysis.llm_analysis)
    
    # 5. Análisis EXPLAIN
    if analysis.explain_analysis:
        _add_text_section(pdf, "Analisis del EXPLAIN Plan", analysis.explain_analysis)
    
    # 6. Query Optimizada
    if analysis.optimized_query:
        _add_query_section(pdf, "Query Optimizada", analysis.optimized_query)
    
    # Generar y retornar bytes
    return pdf.output()


def _add_summary(pdf: FPDF, summary: dict):
    """Agrega tabla de resumen al PDF."""
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, 'Resumen', 0, 1)
    pdf.ln(2)
    
    # Tabla
    critical = summary.get('critical', 0)
    warning = summary.get('warning', 0)
    info = summary.get('info', 0)
    
    # Headers
    pdf.set_font('Arial', 'B', 11)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(63, 8, 'Criticos', 1, 0, 'C', True)
    pdf.cell(63, 8, 'Warnings', 1, 0, 'C', True)
    pdf.cell(64, 8, 'Info', 1, 1, 'C', True)
    
    # Values
    pdf.set_font('Arial', '', 11)
    
    # Critical (rojo)
    pdf.set_fill_color(255, 224, 224)
    pdf.set_text_color(211, 47, 47)
    pdf.cell(63, 8, str(critical), 1, 0, 'C', True)
    
    # Warning (naranja)
    pdf.set_fill_color(255, 243, 224)
    pdf.set_text_color(245, 124, 0)
    pdf.cell(63, 8, str(warning), 1, 0, 'C', True)
    
    # Info (verde)
    pdf.set_fill_color(232, 245, 233)
    pdf.set_text_color(56, 142, 60)
    pdf.cell(64, 8, str(info), 1, 1, 'C', True)
    
    pdf.ln(5)


def _add_query_section(pdf: FPDF, title: str, query: str):
    """Agrega una sección con una query SQL."""
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, title, 0, 1)
    pdf.ln(2)
    
    # Query en bloque con fondo gris
    pdf.set_fill_color(245, 245, 245)
    pdf.set_font('Courier', '', 8)
    pdf.set_text_color(0, 0, 0)
    
    # Dividir query en líneas para que quepa en el PDF
    lines = query.split('\n')
    for line in lines:
        # Línea vacía
        if not line.strip():
            pdf.cell(0, 4, '', 0, 1, 'L', True)
            continue
        
        # Truncar líneas muy largas
        max_chars = 95  # Ajustado para Courier 8pt
        if len(line) > max_chars:
            # Dividir en chunks
            chunks = [line[i:i+max_chars] for i in range(0, len(line), max_chars)]
            for chunk in chunks:
                pdf.cell(0, 4, chunk, 0, 1, 'L', True)
        else:
            pdf.cell(0, 4, line, 0, 1, 'L', True)
    
    pdf.ln(3)


def _add_findings_section(pdf: FPDF, findings: list[RuleFinding]):
    """Agrega sección de hallazgos."""
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, 'Hallazgos Detectados', 0, 1)
    pdf.ln(2)
    
    # Ordenar por severidad (critical primero)
    severity_order = {'critical': 0, 'warning': 1, 'info': 2}
    sorted_findings = sorted(
        findings,
        key=lambda f: severity_order.get(f.severity, 3)
    )
    
    for i, finding in enumerate(sorted_findings, 1):
        _add_finding(pdf, finding, i)
        pdf.ln(3)


def _add_finding(pdf: FPDF, finding: RuleFinding, number: int):
    """Agrega un hallazgo individual."""
    # Color según severidad
    if finding.severity == 'critical':
        bg_color = (255, 224, 224)
        label = 'CRITICO'
        label_color = (211, 47, 47)
    elif finding.severity == 'warning':
        bg_color = (255, 243, 224)
        label = 'WARNING'
        label_color = (245, 124, 0)
    else:
        bg_color = (232, 245, 233)
        label = 'INFO'
        label_color = (56, 142, 60)
    
    # Verificar que hay espacio suficiente
    if pdf.get_y() > 250:
        pdf.add_page()
    
    # Título del hallazgo
    pdf.set_fill_color(*bg_color)
    pdf.set_font('Arial', 'B', 11)
    pdf.set_text_color(*label_color)
    
    # Etiqueta de severidad
    pdf.cell(25, 7, label, 1, 0, 'C', True)
    
    # Rule ID y nombre (truncar si es muy largo)
    rule_text = f"[{finding.rule_id}] {finding.rule_name}"
    if len(rule_text) > 60:
        rule_text = rule_text[:57] + "..."
    pdf.set_text_color(0, 0, 0)
    pdf.cell(165, 7, rule_text, 1, 1, 'L', True)
    
    # Ubicación
    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(100, 100, 100)
    location_text = f"Ubicacion: {finding.location}"[:80]
    pdf.cell(0, 5, location_text, 0, 1)
    
    # Descripción (dividir en líneas manualmente)
    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(0, 0, 0)
    desc_lines = _wrap_text(finding.description, 90)
    for line in desc_lines[:5]:  # Max 5 líneas
        pdf.cell(0, 5, line, 0, 1)
    pdf.ln(1)
    
    # Sugerencia
    if finding.suggestion:
        pdf.set_font('Arial', 'I', 9)
        pdf.set_text_color(50, 50, 150)
        sugg_lines = _wrap_text(f"Sugerencia: {finding.suggestion}", 90)
        for line in sugg_lines[:3]:  # Max 3 líneas
            pdf.cell(0, 5, line, 0, 1)
        pdf.ln(1)
    
    # Código antes/después (simplificado)
    if finding.code_before or finding.code_after:
        pdf.set_font('Courier', '', 7)
        pdf.set_text_color(0, 0, 0)
        
        if finding.code_before:
            pdf.set_fill_color(255, 240, 240)
            code_lines = finding.code_before[:150].split('\n')
            pdf.cell(0, 4, "Antes:", 0, 1, 'L', True)
            for line in code_lines[:3]:
                pdf.cell(0, 3, line[:90], 0, 1, 'L', True)
            pdf.ln(1)
        
        if finding.code_after:
            pdf.set_fill_color(240, 255, 240)
            code_lines = finding.code_after[:150].split('\n')
            pdf.cell(0, 4, "Despues:", 0, 1, 'L', True)
            for line in code_lines[:3]:
                pdf.cell(0, 3, line[:90], 0, 1, 'L', True)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Divide texto en líneas de máximo max_chars caracteres."""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line += (" " if current_line else "") + word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [text[:max_chars]]


def _add_text_section(pdf: FPDF, title: str, text: str):
    """Agrega una sección de texto."""
    pdf.set_font('Arial', 'B', 14)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, title, 0, 1)
    pdf.ln(2)
    
    # Texto
    pdf.set_font('Arial', '', 9)
    pdf.set_text_color(0, 0, 0)
    
    # Limpiar markdown básico (remover ** y ##)
    clean_text = text.replace('**', '').replace('##', '').replace('###', '')
    
    # Limitar longitud para evitar PDFs muy grandes
    if len(clean_text) > 2000:
        clean_text = clean_text[:2000] + "...\n\n[Texto truncado para el PDF]"
    
    # Dividir en líneas y renderizar
    lines = clean_text.split('\n')
    for line in lines[:50]:  # Max 50 líneas
        if not line.strip():
            pdf.ln(2)
            continue
        
        # Wrap largo texto
        wrapped = _wrap_text(line, 95)
        for wrapped_line in wrapped:
            pdf.cell(0, 5, wrapped_line, 0, 1)
    
    pdf.ln(3)
