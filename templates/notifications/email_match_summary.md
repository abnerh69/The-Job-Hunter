⚠️ *Tormenta de emails detectada*

Se han recibido múltiples emails ({{ suggestions | length }}) en la última hora. Aquí tienes un resumen de las sugerencias pendientes:

{% for s in suggestions %}
• *{{ s.suggested_state | escape_telegram_markdown }}* para match con confianza {{ (s.confidence * 100) | round(0) }}%
{% endfor %}

Por favor, revisa el dashboard para procesar estos cambios manualmente.
