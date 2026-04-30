💡 *{{ count }} follow-up{% if count > 1 %}s{% endif %} pendiente{% if count > 1 %}s{% endif %} hoy:*
{% for app in applications %}
• {{ app.job.company | escape_telegram_markdown }}
{% endfor %}

Ver dashboard para más detalles\.
