# GP Query Optimizer

Analizador y optimizador interactivo de queries Impala/Hive para Grupo Petersen — Data & Analytics.

## 🎯 Qué hace

Herramienta conversacional donde pegás una query SQL de Impala/Hive y recibís:

- ✅ Análisis automático con **12 reglas determinísticas** (sin LLM)
- 🤖 Análisis contextual con **LLM (Gemini)**
- ✨ Query optimizada sugerida con **diff visual**
- 📄 Reporte exportable a **PDF y Markdown**
- 💬 **Chat conversacional** para preguntas sobre el análisis
- 📜 **Historial** de análisis en SQLite

## 📋 Reglas Determinísticas

El sistema analiza automáticamente queries con 12 reglas optimizadas para Impala/Hive:

| Regla | Nombre | Severidad |
|-------|--------|-----------|
| **R01** | CTE innecesaria | Warning |
| **R02** | SELECT * detectado | Critical |
| **R03** | LEFT JOIN que es INNER implícito | Critical |
| **R04** | CAST en condición de JOIN | Critical |
| **R05** | Escalar casteado a tipo diferente | Warning |
| **R06** | Función en condición de JOIN | Warning |
| **R07** | REPLACE múltiples anidados | Warning |
| **R08** | MAX(fecha_*) repetido | Warning |
| **R09** | Full scan sin filtro de partición | Critical |
| **R10** | Lógica condicional en JOIN | Warning |
| **R11** | CAST en ambos lados del JOIN | Critical |
| **R12** | Subquery correlacionada en SELECT | Warning |

## 📦 Pre-requisitos

- **Docker Desktop** instalado y corriendo
- **Git**
- **API Key de Google Gemini** (opcional, para análisis LLM)
  - Conseguir en: https://aistudio.google.com/apikey
  - Sin API key, las reglas determinísticas funcionan igual

## 🚀 Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/novakorp/gp-query-optimizer.git
cd gp-query-optimizer

# 2. Crear archivo .env con tu API key
cp .env.example .env
# Editar .env y agregar tu GEMINI_API_KEY

# 3. Levantar con Docker Compose
docker-compose up --build

# 4. Esperar 10-15 segundos y abrir en el browser
```

### URLs de Acceso

- **Frontend (Streamlit):** http://localhost:8502
- **Backend API:** http://localhost:8001
- **API Docs:** http://localhost:8001/docs
- **Health Check:** http://localhost:8001/health

## 💡 Uso

### Análisis Básico

1. Abrir http://localhost:8502
2. Pegar una query SQL de Impala/Hive en el chat
3. Ver el reporte con hallazgos y sugerencias

**Ejemplo:**
```sql
WITH max_fecha AS (
    SELECT MAX(fecha_proceso) AS fp FROM db.tabla_grande
)
SELECT * FROM tabla WHERE fecha = (SELECT fp FROM max_fecha)
```

### Análisis Avanzado

En el **panel lateral (sidebar)** se puede agregar información adicional:

- **DDL de tablas:** Para detectar full scans sin filtro de partición (R09)
  ```sql
  CREATE TABLE db.tabla_grande (
      id BIGINT,
      nombre STRING
  )
  PARTITIONED BY (fecha_proceso STRING)
  ```

- **EXPLAIN plan:** Pegar la salida de `EXPLAIN <query>` de Impala para detectar problemas de memoria, shuffles y broadcasts

- **Contexto:** Información adicional como:
  - "La tabla X tiene 2B rows"
  - "Esta query se ejecuta cada hora"
  - "Tarda 45 minutos en producción"

### Exportar Reportes

- **📥 Exportar Markdown:** Descarga reporte en formato .md
- **📄 Descargar PDF:** Genera y descarga reporte profesional en PDF

### Chat Conversacional

Además de analizar queries, el sistema responde preguntas:

**Ejemplos:**
- "Explicame la regla R04"
- "Qué información adicional necesitas?"
- "Cómo puedo mejorar esta query?"
- "Por qué el LEFT JOIN es problemático?"

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                  Docker Container                    │
│                                                      │
│  ┌────────────────┐         ┌──────────────────┐   │
│  │   Streamlit    │  HTTP   │    FastAPI       │   │
│  │   Frontend     │ ◄─────► │    Backend       │   │
│  │   :8502        │         │    :8001         │   │
│  └────────────────┘         └──────────────────┘   │
│                                      │               │
│                             ┌────────┴────────┐     │
│                             │                 │     │
│                        ┌────▼────┐     ┌─────▼───┐ │
│                        │ sqlglot │     │ Gemini  │ │
│                        │ Parser  │     │   LLM   │ │
│                        └─────────┘     └─────────┘ │
│                             │                       │
│                        ┌────▼────┐                 │
│                        │ SQLite  │                 │
│                        │ History │                 │
│                        └─────────┘                 │
└─────────────────────────────────────────────────────┘
```

**Flujo:**
1. Usuario pega query en Streamlit
2. Frontend detecta si es SQL o conversación
3. POST a `/api/chat` en FastAPI
4. Backend parsea con `sqlglot` (dialecto Hive)
5. Ejecuta 12 reglas determinísticas
6. Envía a Gemini para análisis contextual
7. Guarda en SQLite
8. Retorna reporte completo
9. Frontend renderiza visualmente

## 🛠️ Stack Tecnológico

| Componente | Tecnología | Versión |
|-----------|------------|---------|
| **Frontend** | Streamlit | 1.40+ |
| **Backend** | FastAPI | 0.115+ |
| **SQL Parser** | sqlglot | 26.0+ |
| **LLM** | Gemini (google-generativeai) | 3.8-flash |
| **PDF Export** | fpdf2 | 2.7+ |
| **Database** | SQLite | Built-in |
| **Deploy** | Docker Compose | 3.8 |
| **Python** | Python | 3.12 |

## 🐛 Troubleshooting

### Docker no levanta

**Problema:** `docker-compose up` falla

**Soluciones:**
```bash
# Verificar que Docker Desktop esté corriendo
docker ps

# Limpiar y rebuildar
docker-compose down
docker-compose up --build

# Ver logs detallados
docker-compose logs -f
```

### Error de Gemini API

**Problema:** Error al llamar al LLM

**Soluciones:**
1. Verificar que `GEMINI_API_KEY` esté en el `.env`
   ```bash
   cat .env | grep GEMINI_API_KEY
   ```

2. Verificar que la key sea válida en https://aistudio.google.com/apikey

3. **Nota:** Las reglas determinísticas funcionan sin Gemini, solo el análisis contextual requiere la API

### El frontend no carga

**Problema:** http://localhost:8502 no responde

**Soluciones:**
1. Esperar 10-15 segundos después del `docker-compose up`
2. Verificar que el puerto 8502 no esté ocupado:
   ```bash
   netstat -an | findstr 8502
   ```
3. Ver logs del contenedor:
   ```bash
   docker-compose logs -f
   ```

### El backend retorna error 500

**Problema:** Análisis falla con error interno

**Soluciones:**
1. Ver logs del backend:
   ```bash
   docker-compose logs backend
   ```
2. Verificar la sintaxis SQL (debe ser Hive/Impala válido)
3. Probar el health check: http://localhost:8001/health

### Cambios no se reflejan

**Problema:** Edité código pero no veo cambios

**Soluciones:**
1. Si editaste Python: el hot-reload debería funcionar automáticamente
2. Si editaste `requirements.txt`:
   ```bash
   docker-compose down
   docker-compose up --build
   ```
3. Si editaste `Dockerfile` o `docker-compose.yml`: rebuildar

## 👨‍💻 Desarrollo

### Hot-Reload Habilitado

El proyecto está configurado con hot-reload para desarrollo rápido:

- **Backend:** `uvicorn` con `--reload` detecta cambios en archivos `.py`
- **Frontend:** `streamlit` detecta cambios automáticamente
- **Volúmenes:** Los directorios `backend/` y `frontend/` están montados

### Estructura del Proyecto

```
gp-query-optimizer/
├── backend/
│   ├── analyzer/         # Lógica de análisis
│   │   ├── agent.py      # Orquestador principal
│   │   ├── sql_parser.py # Parser sqlglot
│   │   ├── rules_engine.py # 12 reglas
│   │   ├── llm_analyzer.py # Integración Gemini
│   │   └── llm_chat.py   # Chat conversacional
│   ├── api/
│   │   ├── models.py     # Pydantic models
│   │   └── routes.py     # Endpoints FastAPI
│   ├── db/
│   │   └── history.py    # SQLite historial
│   └── export/
│       └── pdf_generator.py # Generador PDF
├── frontend/
│   └── app.py            # Streamlit app
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

### Agregar una Nueva Regla

1. Editar `backend/analyzer/rules_engine.py`
2. Crear función `rXX_nombre(parsed: ParsedQuery) -> list[RuleFinding]`
3. Agregar a `run_all_rules()`
4. Documentar en `backend/rules/README.md`

### Tests

```bash
# Test del parser SQL
python backend/analyzer/sql_parser.py

# Test de reglas
python -c "from backend.analyzer.rules_engine import *; print('OK')"

# Test de historial
python -c "from backend.db.history import *; print('OK')"
```

## 📊 Endpoints de la API

### `POST /api/chat`
Endpoint principal conversacional (detecta SQL vs chat)

**Request:**
```json
{
  "message": "SELECT * FROM tabla",
  "ddl": "CREATE TABLE...",
  "explain_plan": "EXPLAIN output...",
  "context": "Tabla tiene 2B rows",
  "history": [...],
  "last_analysis": {...}
}
```

**Response:**
```json
{
  "type": "analysis" | "chat",
  "analysis": {...} | null,
  "message": "..." | null
}
```

### `POST /api/analyze`
Análisis directo (legacy, aún funciona)

### `POST /api/analyze/pdf`
Genera y descarga PDF

### `GET /api/history`
Lista últimos análisis

### `GET /api/history/{id}`
Detalle de un análisis

### `GET /health`
Health check

## 📝 Variables de Entorno

Archivo `.env` requerido:

```bash
# API Key de Google Gemini
GEMINI_API_KEY=your_api_key_here

# Base de datos (opcional, default: /app/data/history.db)
SQLITE_DB=/app/data/history.db
```

## 🤝 Contribuir

1. Fork del repo
2. Crear branch: `git checkout -b feature/mi-feature`
3. Commit: `git commit -m 'Agregar mi feature'`
4. Push: `git push origin feature/mi-feature`
5. Abrir Pull Request

## 📄 Licencia

Propietario: Grupo Petersen — Data & Analytics

## 📞 Contacto

**Edgardo Girardi**  
egirardi@novakorp.io

---

Desarrollado con ⚡ por el equipo de Data & Analytics de Grupo Petersen
