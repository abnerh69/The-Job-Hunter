# ⚠️ {{ type }} Detectada: {{ metric.name }}

**Magnitud del Cambio:**
- **Valor Actual:** {{ "%.2f"|format(metric.current_value) }}%
- **Línea de Base:** {{ "%.2f"|format(metric.baseline_value) }}%
- **Cambio:** {{ "%.2f"|format(metric.change_pct) }}% ({{ "%+.2f"|format(metric.change_absolute) }} pp)

{% if context.prompt_versions %}
**Contexto de Prompts:**
{% for v in context.prompt_versions %}
- Version: `{{ v }}`
{% endfor %}
{% endif %}

{% if context.models %}
**Modelos Utilizados:**
{% for m in context.models %}
- `{{ m }}`
{% endfor %}
{% endif %}

🔍 *Sugerencia: Considera correr `jobhunter analytics report` para un análisis completo.*

[Ver Dashboard](https://jobhunter-eu.streamlit.app)
