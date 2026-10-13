import streamlit as st
import streamlit.components.v1 as components
import httpx
import json
import difflib
import base64
from datetime import datetime
from typing import Optional

# Configuración de la página
st.set_page_config(
    page_title="Novakorp Query Optimizer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS personalizado con dark theme
st.markdown("""
<style>
    /* Background principal */
    .stApp {
        background-color: #0a0e17;
        color: #e2e8f0;
    }
    
    /* Text areas y inputs */
    .stTextArea textarea, .stTextInput input {
        background-color: #1a202c;
        color: #e2e8f0;
        border: 1px solid #2d3748;
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    
    /* Cards de hallazgos */
    .finding-card {
        border-radius: 0 8px 8px 0;
        padding: 16px;
        margin: 12px 0;
    }
    
    .finding-critical {
        border-left: 4px solid #F44336;
        background-color: rgba(244, 67, 54, 0.1);
    }
    
    .finding-warning {
        border-left: 4px solid #FF9800;
        background-color: rgba(255, 152, 0, 0.1);
    }
    
    .finding-info {
        border-left: 4px solid #4CAF50;
        background-color: rgba(76, 175, 80, 0.1);
    }
    
    /* Métricas */
    .metric-card {
        background-color: #1a202c;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        border: 1px solid #2d3748;
    }
    
    .metric-value {
        font-size: 36px;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .metric-label {
        font-size: 14px;
        color: #a0aec0;
        text-transform: uppercase;
    }
    
    /* Chat messages */
    .chat-message {
        padding: 16px;
        border-radius: 8px;
        margin: 12px 0;
        background-color: #1a202c;
        border: 1px solid #2d3748;
    }
    
    .user-message {
        background-color: #2d3748;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #e2e8f0 !important;
    }
    
    /* Buttons */
    .stButton button {
        background-color: #4299e1;
        color: white;
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #1a202c;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def generate_diff(original, optimized):
    """Genera un diff unificado entre dos queries."""
    original_lines = original.splitlines(keepends=True)
    optimized_lines = optimized.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        optimized_lines,
        fromfile="original.sql",
        tofile="optimized.sql",
        lineterm=""
    )
    
    return "".join(diff)


def copy_to_clipboard(text: str, button_key: str):
    """Copia texto al portapapeles usando JavaScript."""
    html_code = f"""
    <script>
        function copyToClipboard_{button_key}() {{
            const text = `{text.replace('`', '\\`').replace('$', '\\$')}`;
            navigator.clipboard.writeText(text).then(function() {{
                console.log('Copied to clipboard');
            }}, function(err) {{
                console.error('Could not copy text: ', err);
            }});
        }}
    </script>
    <button onclick="copyToClipboard_{button_key}()" 
            style="background-color: #4299e1; color: white; padding: 8px 16px; 
                   border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
        📋 Copiar al portapapeles
    </button>
    """
    components.html(html_code, height=50)


def export_to_markdown(data: dict) -> str:
    """Genera un reporte en formato Markdown."""
    md_parts = []
    
    # Header
    md_parts.append("# Novakorp Query Optimizer - Reporte de Análisis\n")
    md_parts.append(f"**Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    md_parts.append("**Novakorp - Data & Analytics**\n\n")
    md_parts.append("---\n\n")
    
    # Query original
    md_parts.append("## Query Original\n\n")
    md_parts.append("```sql\n")
    md_parts.append(data.get("original_query", ""))
    md_parts.append("\n```\n\n")
    
    # Resumen
    summary = data.get("summary", {})
    md_parts.append("## Resumen\n\n")
    md_parts.append(f"- 🔴 **Críticos:** {summary.get('critical', 0)}\n")
    md_parts.append(f"- 🟡 **Warnings:** {summary.get('warning', 0)}\n")
    md_parts.append(f"- 🟢 **Info:** {summary.get('info', 0)}\n\n")
    
    # Hallazgos
    findings = data.get("findings", [])
    if findings:
        md_parts.append("## Hallazgos Detectados\n\n")
        for i, finding in enumerate(findings, 1):
            severity = finding.get("severity", "info")
            emoji = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "🟢"
            
            md_parts.append(f"### {emoji} [{finding.get('rule_id')}] {finding.get('rule_name')}\n\n")
            md_parts.append(f"**Ubicación:** {finding.get('location')}\n\n")
            md_parts.append(f"{finding.get('description')}\n\n")
            md_parts.append(f"**💡 Sugerencia:** {finding.get('suggestion')}\n\n")
            
            if finding.get('code_before'):
                md_parts.append("**Código actual:**\n\n")
                md_parts.append("```sql\n")
                md_parts.append(finding.get('code_before'))
                md_parts.append("\n```\n\n")
            
            if finding.get('code_after'):
                md_parts.append("**Código sugerido:**\n\n")
                md_parts.append("```sql\n")
                md_parts.append(finding.get('code_after'))
                md_parts.append("\n```\n\n")
    
    # Análisis LLM
    llm_analysis = data.get("llm_analysis")
    if llm_analysis:
        md_parts.append("## Análisis Detallado (LLM)\n\n")
        md_parts.append(llm_analysis)
        md_parts.append("\n\n")
    
    # Análisis EXPLAIN
    explain_analysis = data.get("explain_analysis")
    if explain_analysis:
        md_parts.append("## Análisis del EXPLAIN Plan\n\n")
        md_parts.append(explain_analysis)
        md_parts.append("\n\n")
    
    # Query optimizada
    optimized = data.get("optimized_query")
    if optimized:
        md_parts.append("## Query Optimizada\n\n")
        md_parts.append("```sql\n")
        md_parts.append(optimized)
        md_parts.append("\n```\n\n")
    
    return "".join(md_parts)


def get_history_from_backend(limit: int = 10) -> list:
    """Obtiene el historial del backend."""
    try:
        response = httpx.get(
            f"http://localhost:8001/api/history?limit={limit}",
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json().get("history", [])
    except:
        pass
    return []


def load_analysis_from_history(analysis_id: int) -> Optional[dict]:
    """Carga un análisis del historial."""
    try:
        response = httpx.get(
            f"http://localhost:8001/api/history/{analysis_id}",
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


def generate_pdf_from_backend(request_data: dict) -> Optional[bytes]:
    """Genera PDF desde el backend."""
    try:
        response = httpx.post(
            "http://localhost:8001/api/analyze/pdf",
            json=request_data,
            timeout=90.0
        )
        if response.status_code == 200:
            return response.content
    except Exception as e:
        print(f"Error generating PDF: {e}")
    return None


def render_finding(finding):
    """Renderiza un hallazgo individual."""
    severity = finding.get("severity", "info")
    rule_id = finding.get("rule_id", "")
    rule_name = finding.get("rule_name", "")
    description = finding.get("description", "")
    suggestion = finding.get("suggestion", "")
    location = finding.get("location", "")
    code_before = finding.get("code_before", "")
    code_after = finding.get("code_after", "")
    
    # Emoji según severidad
    emoji = "🔴" if severity == "critical" else "🟡" if severity == "warning" else "🟢"
    css_class = f"finding-{severity}"
    
    st.markdown(
        f"""<div class="finding-card {css_class}">
            <h4>{emoji} [{rule_id}] {rule_name}</h4>
        </div>""",
        unsafe_allow_html=True
    )
    
    st.markdown(f"**📍 Ubicación:** {location}")
    st.markdown(description)
    
    if suggestion:
        st.markdown(f"💡 *{suggestion}*")
    
    # Expander con código antes/después
    if code_before or code_after:
        with st.expander("👁️ Ver código"):
            if code_before and code_after:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Antes:**")
                    st.code(code_before, language="sql")
                with col2:
                    st.markdown("**Después:**")
                    st.code(code_after, language="sql")
            elif code_before:
                st.markdown("**Código actual:**")
                st.code(code_before, language="sql")
            elif code_after:
                st.markdown("**Código sugerido:**")
                st.code(code_after, language="sql")
    
    st.markdown("<br>", unsafe_allow_html=True)


def render_concise_analysis(data, pdf_base64=None):
    """Renderiza el análisis de forma concisa: mensaje conversacional + desglose por regla + PDF."""
    
    findings = data.get("findings", [])
    summary = data.get("summary", {})
    total_findings = summary.get("critical", 0) + summary.get("warning", 0) + summary.get("info", 0)
    
    # Si no hay hallazgos
    if total_findings == 0:
        st.markdown("Analicé tu query y no encontré problemas. ✅ **Se ve bien!**")
        st.markdown("")
        
        # Verificar si hay query optimizada igual (por si el LLM sugirió algo)
        if data.get("optimized_query"):
            st.markdown("Igual generé algunas sugerencias de mejora que podés ver en el PDF.")
            st.markdown("")
    else:
        # Agrupar findings por rule_id y severidad
        rule_groups = {
            "critical": {},
            "warning": {},
            "info": {}
        }
        
        for finding in findings:
            severity = finding.get("severity", "info")
            rule_id = finding.get("rule_id", "")
            rule_name = finding.get("rule_name", "")
            
            if rule_id not in rule_groups[severity]:
                rule_groups[severity][rule_id] = {
                    "name": rule_name,
                    "count": 0
                }
            rule_groups[severity][rule_id]["count"] += 1
        
        # Construir mensaje
        st.markdown(f"Analicé tu query. Encontré **{total_findings} hallazgos**:")
        st.markdown("")
        
        # Críticos
        if rule_groups["critical"]:
            critical_count = sum(r["count"] for r in rule_groups["critical"].values())
            st.markdown(f"🔴 **{critical_count} críticos:**")
            for rule_id, rule_data in sorted(rule_groups["critical"].items()):
                count_text = f"{rule_data['count']} casos" if rule_data['count'] > 1 else "1 caso"
                st.markdown(f"- **{rule_id}** {rule_data['name']}: {count_text}")
            st.markdown("")
        
        # Warnings
        if rule_groups["warning"]:
            warning_count = sum(r["count"] for r in rule_groups["warning"].values())
            st.markdown(f"🟡 **{warning_count} warnings:**")
            for rule_id, rule_data in sorted(rule_groups["warning"].items()):
                count_text = f"{rule_data['count']} casos" if rule_data['count'] > 1 else "1 caso"
                st.markdown(f"- **{rule_id}** {rule_data['name']}: {count_text}")
            st.markdown("")
        
        # Informativos (si hay)
        if rule_groups["info"]:
            info_count = sum(r["count"] for r in rule_groups["info"].values())
            st.markdown(f"🟢 **{info_count} informativos:**")
            for rule_id, rule_data in sorted(rule_groups["info"].items()):
                count_text = f"{rule_data['count']} casos" if rule_data['count'] > 1 else "1 caso"
                st.markdown(f"- **{rule_id}** {rule_data['name']}: {count_text}")
            st.markdown("")
        
        # Invitación a descargar PDF
        st.markdown("**Descargá el PDF** para ver el detalle de cada hallazgo, las sugerencias y la query optimizada.")
        st.markdown("")
    
    # Sugerencias de contexto adicional (si aplica)
    suggestions = []
    
    # Verificar si hay R09 (full scan) y no hay DDL
    has_r09 = any(f.get("rule_id") == "R09" for f in findings)
    has_ddl = st.session_state.get("has_ddl", False)
    
    if has_r09 and not has_ddl:
        suggestions.append("💡 **Tip:** Si me pasás el DDL de las tablas en el panel lateral, puedo verificar mejor los filtros de partición.")
    
    # Verificar si hay muchos hallazgos críticos y no hay EXPLAIN
    has_explain = st.session_state.get("has_explain", False)
    critical_count = summary.get("critical", 0)
    
    if critical_count >= 2 and not has_explain:
        suggestions.append("💡 **Tip:** Si agregás el EXPLAIN plan en el panel lateral, puedo analizar el impacto en memoria y shuffles.")
    
    # Mostrar sugerencias
    if suggestions:
        st.markdown("")
        for suggestion in suggestions:
            st.markdown(suggestion)
        st.markdown("")
    
    # Botón de descarga del PDF
    if pdf_base64:
        try:
            pdf_bytes = base64.b64decode(pdf_base64)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📄 Descargar reporte PDF",
                data=pdf_bytes,
                file_name=f"query-analysis-{timestamp}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
        except Exception as e:
            st.error(f"Error decodificando PDF: {str(e)}")
    else:
        st.info("💡 El PDF no pudo generarse automáticamente, pero el análisis está completo.")


def render_report(data):
    """Renderiza el reporte visual COMPLETO del análisis (LEGACY - para historial)."""
    
    # 1. Resumen con métricas
    summary = data.get("summary", {})
    critical = summary.get("critical", 0)
    warning = summary.get("warning", 0)
    info = summary.get("info", 0)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-label">🔴 Críticos</div>
                <div class="metric-value" style="color: #F44336;">{critical}</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col2:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-label">🟡 Warnings</div>
                <div class="metric-value" style="color: #FF9800;">{warning}</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    with col3:
        st.markdown(
            f"""<div class="metric-card">
                <div class="metric-label">🟢 Info</div>
                <div class="metric-value" style="color: #4CAF50;">{info}</div>
            </div>""",
            unsafe_allow_html=True
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 2. Hallazgos
    findings = data.get("findings", [])
    
    if findings:
        st.markdown("### 📋 Hallazgos Detectados")
        
        for finding in findings:
            render_finding(finding)
    else:
        st.success("✅ No se detectaron problemas en la query")
    
    # 3. Análisis LLM
    llm_analysis = data.get("llm_analysis")
    if llm_analysis:
        st.markdown("---")
        st.markdown("### 🤖 Análisis Detallado")
        st.markdown(llm_analysis)
    
    # 4. Análisis EXPLAIN
    explain_analysis = data.get("explain_analysis")
    if explain_analysis:
        st.markdown("---")
        st.markdown("### 📊 Análisis del EXPLAIN Plan")
        st.markdown(explain_analysis)
    
    # 5. Query optimizada
    optimized = data.get("optimized_query")
    if optimized:
        st.markdown("---")
        st.markdown("### ✨ Query Optimizada")
        
        tab1, tab2 = st.tabs(["📝 Query Optimizada", "🔄 Diff"])
        
        with tab1:
            st.code(optimized, language="sql")
            copy_to_clipboard(optimized, f"opt_{hash(optimized)}")
        
        with tab2:
            original = data.get("original_query", "")
            diff = generate_diff(original, optimized)
            st.code(diff, language="diff")
    
    # Botones de export
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        markdown_content = export_to_markdown(data)
        st.download_button(
            label="📥 Exportar Markdown",
            data=markdown_content,
            file_name=f"query_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True
        )
    
    with col2:
        # Botón para generar y descargar PDF
        # Necesitamos el request original guardado en session_state
        if "last_request" in st.session_state:
            if st.button("📄 Descargar PDF", use_container_width=True, type="secondary"):
                with st.spinner("Generando PDF..."):
                    try:
                        pdf_bytes = generate_pdf_from_backend(st.session_state.last_request)
                        if pdf_bytes:
                            st.download_button(
                                label="💾 Guardar PDF",
                                data=pdf_bytes,
                                file_name=f"query_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                                key=f"pdf_download_{hash(str(data))}"
                            )
                    except Exception as e:
                        st.error(f"Error generando PDF: {str(e)}")


# ============================================================================
# APLICACIÓN PRINCIPAL
# ============================================================================

# Inicializar session state
if "messages" not in st.session_state:
    st.session_state.messages = []
    
    # Mensaje de bienvenida
    welcome_message = """Hola! Soy el asistente del Query Optimizer de Novakorp. 

**Podés:**
- Pegar una query SQL de Impala/Hive
- Arrastrar un archivo `.sql` o `.txt`
- Preguntarme sobre el último análisis

El análisis completo con todos los hallazgos se genera automáticamente en PDF. ¿Arrancamos?"""
    
    st.session_state.messages.append({
        "role": "assistant",
        "content": welcome_message,
        "type": "welcome"
    })

if "last_analysis" not in st.session_state:
    st.session_state.last_analysis = None

# Header
st.markdown("# ⚡ Novakorp Query Optimizer")
st.markdown(
    "<p style='color: #a0aec0; font-size: 16px;'>"
    "Analizador de queries Impala/Hive — Novakorp Data & Analytics"
    "</p>",
    unsafe_allow_html=True
)
st.markdown("---")

# Sidebar con opciones avanzadas
with st.sidebar:
    st.markdown("### ⚙️ Opciones Avanzadas")
    
    ddl = st.text_area(
        "DDL de tablas (opcional)",
        height=150,
        placeholder="CREATE TABLE db.tabla (\n  id BIGINT,\n  nombre STRING\n)\nPARTITIONED BY (fecha_proceso STRING)",
        help="DDL de las tablas referenciadas en la query"
    )
    
    explain_plan = st.text_area(
        "EXPLAIN plan (opcional)",
        height=150,
        placeholder="Pega el resultado de EXPLAIN aquí...",
        help="Plan de ejecución de Impala/Hive"
    )
    
    context = st.text_input(
        "Contexto adicional",
        placeholder="Ej: la tabla X tiene 2B rows, se ejecuta cada hora",
        help="Información adicional para el análisis"
    )
    
    st.markdown("---")
    
    # Historial
    st.markdown("### 📜 Historial")
    history = get_history_from_backend(limit=10)
    
    if history:
        for item in history:
            summary = item.get("summary", {})
            critical = summary.get("critical", 0)
            warning = summary.get("warning", 0)
            
            # Mostrar preview
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(item.get("query_preview", ""))
            with col2:
                if critical > 0:
                    st.markdown(f"🔴 {critical}")
                elif warning > 0:
                    st.markdown(f"🟡 {warning}")
                else:
                    st.markdown("🟢")
            
            # Botón para cargar
            if st.button(f"Cargar", key=f"load_{item['id']}", use_container_width=True):
                analysis = load_analysis_from_history(item['id'])
                if analysis:
                    # Agregar al historial de chat
                    st.session_state.messages.append({
                        "role": "user",
                        "content": analysis["original_query"]
                    })
                    st.session_state.messages.append({
                        "role": "assistant",
                        "data": analysis
                    })
                    st.rerun()
            
            st.markdown("---")
    else:
        st.caption("No hay análisis guardados")
    
    st.markdown("---")
    if st.button("🗑️ Limpiar chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Mostrar historial de chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            # Si parece SQL, mostrarlo como código
            if len(msg["content"]) > 20 and any(kw in msg["content"].upper() for kw in ["SELECT", "WITH", "INSERT"]):
                st.code(msg["content"], language="sql")
            else:
                st.markdown(msg["content"])
    else:
        with st.chat_message("assistant", avatar="⚡"):
            msg_type = msg.get("type", "analysis")
            
            if msg_type == "welcome":
                st.markdown(msg["content"])
            elif msg_type == "chat":
                st.markdown(msg["content"])
            elif msg_type == "analysis" and "data" in msg:
                # Usar render_concise si hay PDF, render_report si es del historial
                if msg.get("pdf_base64"):
                    render_concise_analysis(msg["data"], msg.get("pdf_base64"))
                else:
                    render_report(msg["data"])

# File uploader para archivos .sql
st.markdown("**Arrastra un archivo .sql o pega tu query abajo:**")
uploaded_file = st.file_uploader(
    "Subir archivo SQL",
    type=["sql", "txt"],
    label_visibility="collapsed",
    key="sql_file_uploader"
)

# Si se subió un archivo, procesarlo automáticamente
if uploaded_file is not None and "last_uploaded_file" not in st.session_state:
    st.session_state.last_uploaded_file = uploaded_file.name
    try:
        # Leer contenido del archivo
        file_content = uploaded_file.read().decode("utf-8")
        
        # Agregar al historial de chat como si el usuario lo hubiera pegado
        st.session_state.messages.append({
            "role": "user",
            "content": file_content
        })
        
        # Procesar automáticamente
        with st.chat_message("user", avatar="👤"):
            st.code(file_content, language="sql")
        
        with st.chat_message("assistant", avatar="⚡"):
            with st.spinner("🔍 Analizando query..."):
                try:
                    # Preparar historial
                    history = []
                    for msg in st.session_state.messages[-11:-1]:
                        if msg["role"] == "user":
                            history.append({"role": "user", "content": msg["content"]})
                        elif msg.get("type") == "chat":
                            history.append({"role": "assistant", "content": msg["content"]})
                    
                    # Guardar flags de contexto disponible
                    st.session_state.has_ddl = bool(ddl and ddl.strip())
                    st.session_state.has_explain = bool(explain_plan and explain_plan.strip())
                    
                    # Preparar request
                    payload = {
                        "message": file_content,
                        "ddl": ddl if ddl and ddl.strip() else None,
                        "explain_plan": explain_plan if explain_plan and explain_plan.strip() else None,
                        "context": context if context and context.strip() else None,
                        "history": history,
                        "last_analysis": st.session_state.last_analysis
                    }
                    
                    # POST al endpoint de chat
                    response = httpx.post(
                        "http://localhost:8001/api/chat",
                        json=payload,
                        timeout=90.0
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        response_type = result.get("type")
                        
                        if response_type == "analysis":
                            analysis_data = result.get("analysis")
                            pdf_base64 = result.get("pdf_base64")
                            
                            # Guardar último análisis
                            st.session_state.last_analysis = analysis_data
                            
                            # Guardar en historial con PDF
                            st.session_state.messages.append({
                                "role": "assistant",
                                "type": "analysis",
                                "data": analysis_data,
                                "pdf_base64": pdf_base64
                            })
                            
                            # Renderizar análisis conciso
                            render_concise_analysis(analysis_data, pdf_base64)
                    else:
                        st.error(f"❌ Error {response.status_code}: {response.text}")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
        
        st.rerun()
    except Exception as e:
        st.error(f"❌ Error leyendo archivo: {str(e)}")

# Limpiar flag si se cambió de archivo
if uploaded_file is None and "last_uploaded_file" in st.session_state:
    del st.session_state.last_uploaded_file

# Input de chat
if prompt := st.chat_input("Pega una query SQL o preguntame algo..."):
    if prompt.strip():
        # Agregar mensaje del usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Mostrar mensaje del usuario
        with st.chat_message("user", avatar="👤"):
            # Detectar si es SQL para mostrar como código
            is_sql = len(prompt) > 20 and any(kw in prompt.upper() for kw in ["SELECT", "WITH", "INSERT", "CREATE"])
            if is_sql:
                st.code(prompt, language="sql")
            else:
                st.markdown(prompt)
        
        # Procesar mensaje
        with st.chat_message("assistant", avatar="⚡"):
            # Determinar spinner text
            if is_sql:
                spinner_text = "🔍 Analizando query..."
            else:
                spinner_text = "💭 Pensando..."
            
            with st.spinner(spinner_text):
                try:
                    # Preparar historial (últimos 10 mensajes, excluyendo el actual)
                    history = []
                    for msg in st.session_state.messages[-11:-1]:  # Últimos 10, sin el actual
                        if msg["role"] == "user":
                            history.append({"role": "user", "content": msg["content"]})
                        elif msg.get("type") == "chat":
                            history.append({"role": "assistant", "content": msg["content"]})
                    
                    # Guardar flags de contexto disponible
                    st.session_state.has_ddl = bool(ddl and ddl.strip())
                    st.session_state.has_explain = bool(explain_plan and explain_plan.strip())
                    
                    # Preparar request
                    payload = {
                        "message": prompt,
                        "ddl": ddl if ddl and ddl.strip() else None,
                        "explain_plan": explain_plan if explain_plan and explain_plan.strip() else None,
                        "context": context if context and context.strip() else None,
                        "history": history,
                        "last_analysis": st.session_state.last_analysis
                    }
                    
                    # POST al endpoint de chat
                    response = httpx.post(
                        "http://localhost:8001/api/chat",
                        json=payload,
                        timeout=90.0
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        response_type = result.get("type")
                        
                        if response_type == "analysis":
                            # Es un análisis → guardar y renderizar análisis conciso
                            analysis_data = result.get("analysis")
                            pdf_base64 = result.get("pdf_base64")
                            
                            # Guardar último análisis
                            st.session_state.last_analysis = analysis_data
                            
                            # Guardar en historial con PDF
                            st.session_state.messages.append({
                                "role": "assistant",
                                "type": "analysis",
                                "data": analysis_data,
                                "pdf_base64": pdf_base64
                            })
                            
                            # Renderizar análisis conciso
                            render_concise_analysis(analysis_data, pdf_base64)
                            
                        else:  # type == "chat"
                            # Es conversación → mostrar mensaje
                            message = result.get("message", "")
                            
                            # Guardar en historial
                            st.session_state.messages.append({
                                "role": "assistant",
                                "type": "chat",
                                "content": message
                            })
                            
                            # Mostrar mensaje
                            st.markdown(message)
                    else:
                        st.error(f"❌ Error {response.status_code}: {response.text}")
                        
                except httpx.ConnectError:
                    st.error("❌ No se pudo conectar con el backend. Asegúrate de que esté corriendo en http://localhost:8001")
                except httpx.TimeoutException:
                    st.error("⏱️ Timeout: la respuesta tomó demasiado tiempo")
                except Exception as e:
                    st.error(f"❌ Error inesperado: {str(e)}")


# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 12px;'>"
    "Data & Analytics - Novakorp<br>"
    f"v1.0.0 | {datetime.now().year}"
    "</div>",
    unsafe_allow_html=True
)
