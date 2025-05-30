import streamlit as st
from utils import BEDROCK_MODEL_ID
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
from utils import invoke_bedrock_model_streaming
import uuid
from styles import apply_custom_styles


def generate_backlog_estimation(messages):
    """Generate project backlog and estimations based on the conversation."""
    
    if "backlog_estimation_generated" not in st.session_state:
        st.session_state.backlog_estimation_generated = False
    
    if "backlog_estimation_content" not in st.session_state:
        st.session_state.backlog_estimation_content = ""

    # Apply custom styles
    apply_custom_styles()

    # Generate button
    if st.button("📋 Generate Project Backlog & Estimations", key="generate_backlog_btn"):
        with st.spinner("Creating project backlog and estimations..."):
            try:
                # Extract conversation context
                conversation_context = ""
                for msg in messages:
                    if msg["role"] == "user":
                        conversation_context += f"Usuario: {msg['content']}\n"
                    elif msg["role"] == "assistant":
                        conversation_context += f"Asistente: {msg['content']}\n"

                # Create backlog generation prompt
                backlog_prompt = f"""
Basándote en la conversación sobre la solución AWS, genera un backlog de proyecto completo con estimaciones detalladas.

Contexto de la conversación:
{conversation_context}

Crea una tabla en formato Markdown con las siguientes columnas exactas:
| Iniciativa | Componente | Épica | User Story - Capacidad | Estimación puntos de usuario | Estimación Horas | Prioridad | Definición de User Story |

Instrucciones específicas:

1. **Iniciativa**: Agrupa las funcionalidades en iniciativas de alto nivel (ej: "Infraestructura Base", "Seguridad", "Monitoreo", etc.)

2. **Componente**: Identifica los componentes técnicos específicos (ej: "API Gateway", "Lambda Functions", "RDS Database", etc.)

3. **Épica**: Define épicas que agrupen user stories relacionadas (ej: "Configuración de Base de Datos", "Implementación de API", etc.)

4. **User Story - Capacidad**: Escribe user stories en formato "Como [usuario], quiero [funcionalidad] para [beneficio]"

5. **Estimación puntos de usuario**: Usa escala Fibonacci (1, 2, 3, 5, 8, 13, 21) basada en complejidad

6. **Estimación Horas**: Convierte puntos a horas (1 punto = 4-6 horas aprox.)

7. **Prioridad**: Usa Alta, Media, Baja basado en dependencias y valor de negocio

8. **Definición de User Story**: Criterios de aceptación detallados y condiciones de "Done"

Incluye al menos 15-20 user stories que cubran:
- Configuración de infraestructura
- Desarrollo de aplicaciones
- Configuración de seguridad
- Implementación de monitoreo
- Testing y QA
- Deployment y DevOps
- Documentación

Después de la tabla, proporciona:

## 📊 Resumen del Proyecto

### Estimación Total
- **Total Story Points**: [suma total]
- **Total Horas Estimadas**: [suma total]
- **Duración Estimada**: [semanas/meses basado en equipo típico]

### Distribución por Prioridad
- **Alta Prioridad**: X story points (X horas)
- **Media Prioridad**: X story points (X horas)  
- **Baja Prioridad**: X story points (X horas)

### Fases Recomendadas

#### Fase 1 - MVP (Semanas 1-X)
- Lista de user stories de alta prioridad
- Entregables clave

#### Fase 2 - Funcionalidades Core (Semanas X-Y)
- User stories de media prioridad
- Mejoras y optimizaciones

#### Fase 3 - Mejoras y Optimización (Semanas Y-Z)
- User stories de baja prioridad
- Funcionalidades adicionales

### Consideraciones y Riesgos
- Dependencias críticas
- Riesgos técnicos identificados
- Recomendaciones para mitigación

### Equipo Recomendado
- Roles necesarios
- Tamaño de equipo sugerido
- Skills requeridos

Asegúrate de que las estimaciones sean realistas y consideren la complejidad de AWS, integraciones, testing y documentación.
"""

                # Prepare messages for the model
                backlog_messages = [
                    {
                        "role": "user",
                        "content": backlog_prompt
                    }
                ]

                # Generate backlog using streaming
                backlog_content = ""
                backlog_placeholder = st.empty()
                
                for chunk in invoke_bedrock_model_streaming(
                    model_id=BEDROCK_MODEL_ID,
                    messages=backlog_messages,
                    max_tokens=4000,
                    temperature=0.2
                ):
                    if chunk:
                        backlog_content += chunk
                        backlog_placeholder.markdown(backlog_content)

                # Store the generated content
                st.session_state.backlog_estimation_content = backlog_content
                st.session_state.backlog_estimation_generated = True

                # Store in S3
                file_name = f"project_backlog_{uuid.uuid4()}.md"
                store_in_s3(backlog_content, file_name)
                
                st.success("✅ Project backlog and estimations generated successfully!")

            except Exception as e:
                st.error(f"Error generating backlog: {str(e)}")

    # Display generated content if available
    if st.session_state.backlog_estimation_generated and st.session_state.backlog_estimation_content:
        st.markdown("### 📋 Project Backlog & Estimations")
        st.markdown(st.session_state.backlog_estimation_content)
        
        # Download button
        st.download_button(
            label="📥 Download Backlog & Estimations",
            data=st.session_state.backlog_estimation_content,
            file_name=f"project_backlog_{uuid.uuid4()}.md",
            mime="text/markdown",
            key="download_backlog_btn"
        )
        
        # Additional tools section
        st.markdown("---")
        st.markdown("### 🛠️ Additional Project Tools")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Export to CSV", key="export_csv_btn"):
                st.info("💡 Tip: Copy the table from the markdown above and paste it into Excel or Google Sheets for further manipulation.")
        
        with col2:
            if st.button("📅 Create Sprint Plan", key="create_sprint_btn"):
                st.info("💡 Tip: Use the priority levels to organize sprints. Start with High priority items for Sprint 1.")
        
        with col3:
            if st.button("🎯 Refine Estimates", key="refine_estimates_btn"):
                st.info("💡 Tip: Review estimates with your team during planning poker sessions for better accuracy.")
        
        # Feedback section
        st.markdown("---")
        st.markdown("### 💬 Feedback")
        feedback_col1, feedback_col2 = st.columns(2)
        
        with feedback_col1:
            if st.button("👍 Helpful", key="backlog_helpful_btn"):
                collect_feedback(
                    st.session_state.get('conversation_id', 'unknown'),
                    "backlog_estimation",
                    "helpful",
                    "Backlog estimation was helpful"
                )
                st.success("Thank you for your feedback!")
        
        with feedback_col2:
            if st.button("👎 Not Helpful", key="backlog_not_helpful_btn"):
                collect_feedback(
                    st.session_state.get('conversation_id', 'unknown'),
                    "backlog_estimation", 
                    "not_helpful",
                    "Backlog estimation was not helpful"
                )
                st.success("Thank you for your feedback!")


def generate_backlog_from_architecture(uploaded_image):
    """Generate project backlog based on uploaded architecture image."""
    
    if "arch_backlog_generated" not in st.session_state:
        st.session_state.arch_backlog_generated = False
    
    if "arch_backlog_content" not in st.session_state:
        st.session_state.arch_backlog_content = ""

    # Apply custom styles
    apply_custom_styles()

    # Generate button
    if st.button("📋 Generate Backlog from Architecture", key="generate_arch_backlog_btn"):
        if uploaded_image is not None:
            with st.spinner("Analyzing architecture and creating project backlog..."):
                try:
                    # Convert image to base64
                    import base64
                    from PIL import Image
                    import io
                    
                    if isinstance(uploaded_image, Image.Image):
                        img_buffer = io.BytesIO()
                        uploaded_image.save(img_buffer, format='PNG')
                        img_data = img_buffer.getvalue()
                    else:
                        img_data = uploaded_image.read()
                    
                    img_base64 = base64.b64encode(img_data).decode('utf-8')
                    
                    # Create backlog generation prompt for architecture
                    arch_backlog_prompt = """
Analiza la arquitectura AWS mostrada en esta imagen y genera un backlog de proyecto completo para implementar esta solución.

Crea una tabla en formato Markdown con las siguientes columnas exactas:
| Iniciativa | Componente | Épica | User Story - Capacidad | Estimación puntos de usuario | Estimación Horas | Prioridad | Definición de User Story |

Basándote en los componentes visibles en la arquitectura, incluye user stories para:

1. **Configuración de Infraestructura**: Para cada servicio AWS identificado
2. **Configuración de Red**: VPC, subnets, security groups, etc.
3. **Configuración de Seguridad**: IAM, encryption, compliance
4. **Desarrollo de Aplicaciones**: Código para lambdas, APIs, etc.
5. **Configuración de Datos**: Bases de datos, storage, backup
6. **Monitoreo y Logging**: CloudWatch, alertas, dashboards
7. **CI/CD Pipeline**: Deployment automation
8. **Testing**: Unit tests, integration tests, load testing
9. **Documentación**: Technical docs, runbooks, architecture docs

Usa estimaciones realistas considerando la complejidad de cada componente AWS identificado.

Después de la tabla, incluye el resumen del proyecto con estimaciones totales, fases recomendadas y consideraciones técnicas específicas para esta arquitectura.
"""

                    # Prepare messages for the model
                    arch_backlog_messages = [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": arch_backlog_prompt
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": img_base64
                                    }
                                }
                            ]
                        }
                    ]

                    # Generate backlog using streaming
                    arch_backlog_content = ""
                    arch_backlog_placeholder = st.empty()
                    
                    for chunk in invoke_bedrock_model_streaming(
                        model_id=BEDROCK_MODEL_ID,
                        messages=arch_backlog_messages,
                        max_tokens=4000,
                        temperature=0.2
                    ):
                        if chunk:
                            arch_backlog_content += chunk
                            arch_backlog_placeholder.markdown(arch_backlog_content)

                    # Store the generated content
                    st.session_state.arch_backlog_content = arch_backlog_content
                    st.session_state.arch_backlog_generated = True

                    # Store in S3
                    file_name = f"architecture_backlog_{uuid.uuid4()}.md"
                    store_in_s3(arch_backlog_content, file_name)
                    
                    st.success("✅ Architecture-based backlog generated successfully!")

                except Exception as e:
                    st.error(f"Error generating architecture backlog: {str(e)}")
        else:
            st.warning("⚠️ Please upload an architecture image first.")

    # Display generated content if available
    if st.session_state.arch_backlog_generated and st.session_state.arch_backlog_content:
        st.markdown("### 📋 Architecture-Based Project Backlog")
        st.markdown(st.session_state.arch_backlog_content)
        
        # Download button
        st.download_button(
            label="📥 Download Architecture Backlog",
            data=st.session_state.arch_backlog_content,
            file_name=f"architecture_backlog_{uuid.uuid4()}.md",
            mime="text/markdown",
            key="download_arch_backlog_btn"
        )