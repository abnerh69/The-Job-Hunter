{% if count > 0 %}
📋 *{{ count }} aplicación{% if count > 1 %}es{% endif %} esperan follow-up:*
{% for app in applications %}
• {{ app.job.company | escape_telegram_markdown }}
{% endfor %}
{% endif %}

{% if outreach_count > 0 %}
💌 *{{ outreach_count }} contacto{% if outreach_count > 1 %}s{% endif %} esperan follow-up:*
{% for contact in outreach_contacts %}
• {{ contact.name | escape_telegram_markdown }} at {{ (contact.company or 'Unknown') | escape_telegram_markdown }}
{% endfor %}
{% endif %}

Ver dashboard para más detalles\.
