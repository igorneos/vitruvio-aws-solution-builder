import streamlit as st
from utils import BEDROCK_MODEL_ID
from utils import store_in_s3
from utils import save_conversation
from utils import collect_feedback
from utils import invoke_bedrock_model_streaming
import uuid
from styles import apply_custom_styles
import base64
from PIL import Image
import io


def analyze_architecture_improvements(uploaded_image):
    """Generate architecture improvement analysis based on uploaded image."""
    
    if "architecture_analysis_generated" not in st.session_state:
        st.session_state.architecture_analysis_generated = False
    
    if "architecture_analysis_content" not in st.session_state:
        st.session_state.architecture_analysis_content = ""

    # Apply custom styles
    apply_custom_styles()

    # Generate button
    if st.button("🔍 Analyze Architecture for Improvements", key="analyze_architecture_btn"):
        if uploaded_image is not None:
            with st.spinner("Analyzing architecture and identifying improvement opportunities..."):
                try:
                    # Convert image to base64
                    if isinstance(uploaded_image, Image.Image):
                        img_buffer = io.BytesIO()
                        uploaded_image.save(img_buffer, format='PNG')
                        img_data = img_buffer.getvalue()
                    else:
                        img_data = uploaded_image.read()
                    
                    img_base64 = base64.b64encode(img_data).decode('utf-8')
                    
                    # Create analysis prompt
                    analysis_prompt = """
Analiza la arquitectura AWS mostrada en esta imagen y proporciona un análisis detallado de mejoras. 
Estructura tu respuesta en las siguientes secciones:

## 🔍 Análisis de la Arquitectura Actual

### Componentes Identificados
- Lista todos los servicios AWS identificados en el diagrama
- Describe la topología y flujo de datos actual

### Fortalezas de la Arquitectura
- Identifica los aspectos bien diseñados
- Menciona las mejores prácticas ya implementadas

## 🚀 Oportunidades de Mejora

### 1. Seguridad
- Mejoras en configuración de seguridad
- Implementación de principios de menor privilegio
- Cifrado y protección de datos

### 2. Rendimiento y Escalabilidad
- Optimizaciones de rendimiento
- Estrategias de escalado automático
- Mejoras en latencia y throughput

### 3. Disponibilidad y Resiliencia
- Implementación de alta disponibilidad
- Estrategias de recuperación ante desastres
- Redundancia y failover

### 4. Costos
- Optimización de costos
- Uso de instancias reservadas o Spot
- Rightsizing de recursos

### 5. Operaciones y Monitoreo
- Mejoras en observabilidad
- Automatización de operaciones
- Implementación de CI/CD

### 6. Arquitectura y Diseño
- Modernización de servicios
- Implementación de patrones cloud-native
- Microservicios y serverless

## 📋 Plan de Implementación Priorizado

### Prioridad Alta (Implementar primero)
- Lista las mejoras más críticas
- Justifica por qué son prioritarias

### Prioridad Media (Implementar después)
- Mejoras importantes pero no críticas
- Beneficios esperados

### Prioridad Baja (Implementar a largo plazo)
- Optimizaciones adicionales
- Mejoras nice-to-have

## 💰 Estimación de Impacto

### Beneficios Esperados
- Reducción de costos estimada
- Mejoras en rendimiento
- Beneficios operacionales

### Esfuerzo de Implementación
- Tiempo estimado para cada mejora
- Recursos necesarios
- Dependencias entre mejoras

## 🛠️ Recomendaciones Específicas

Para cada mejora identificada, proporciona:
- Configuración específica recomendada
- Servicios AWS adicionales a considerar
- Mejores prácticas de implementación

Sé específico y práctico en tus recomendaciones, considerando tanto aspectos técnicos como de negocio.
"""

                    # Prepare messages for the model
                    analysis_messages = [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": analysis_prompt
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

                    # Generate analysis using streaming
                    analysis_content = ""
                    analysis_placeholder = st.empty()
                    
                    for chunk in invoke_bedrock_model_streaming(
                        model_id=BEDROCK_MODEL_ID,
                        messages=analysis_messages,
                        max_tokens=4000,
                        temperature=0.3
                    ):
                        if chunk:
                            analysis_content += chunk
                            analysis_placeholder.markdown(analysis_content)

                    # Store the generated content
                    st.session_state.architecture_analysis_content = analysis_content
                    st.session_state.architecture_analysis_generated = True

                    # Store in S3
                    file_name = f"architecture_analysis_{uuid.uuid4()}.md"
                    store_in_s3(analysis_content, file_name)
                    
                    st.success("✅ Architecture analysis completed successfully!")

                except Exception as e:
                    st.error(f"Error generating architecture analysis: {str(e)}")
        else:
            st.warning("⚠️ Please upload an architecture image first.")

    # Display generated content if available
    if st.session_state.architecture_analysis_generated and st.session_state.architecture_analysis_content:
        st.markdown("### 📊 Architecture Analysis Results")
        st.markdown(st.session_state.architecture_analysis_content)
        
        # Download button
        st.download_button(
            label="📥 Download Analysis Report",
            data=st.session_state.architecture_analysis_content,
            file_name=f"architecture_analysis_{uuid.uuid4()}.md",
            mime="text/markdown",
            key="download_analysis_btn"
        )
        
        # Feedback section
        st.markdown("---")
        st.markdown("### 💬 Feedback")
        feedback_col1, feedback_col2 = st.columns(2)
        
        with feedback_col1:
            if st.button("👍 Helpful", key="analysis_helpful_btn"):
                collect_feedback(
                    st.session_state.get('conversation_id', 'unknown'),
                    "architecture_analysis",
                    "helpful",
                    "Architecture analysis was helpful"
                )
                st.success("Thank you for your feedback!")
        
        with feedback_col2:
            if st.button("👎 Not Helpful", key="analysis_not_helpful_btn"):
                collect_feedback(
                    st.session_state.get('conversation_id', 'unknown'),
                    "architecture_analysis", 
                    "not_helpful",
                    "Architecture analysis was not helpful"
                )
                st.success("Thank you for your feedback!")