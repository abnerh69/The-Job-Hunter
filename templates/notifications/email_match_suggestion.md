📩 *Nueva correspondencia detectada*

Se ha recibido un email relacionado con una de tus aplicaciones:

*De:* {{ suggestion.from_email | escape_telegram_markdown }}
*Sugerencia:* {{ suggestion.current_state | escape_telegram_markdown }} → *{{ suggestion.suggested_state | escape_telegram_markdown }}*
*Confianza:* {{ (suggestion.confidence * 100) | round(1) }}%

*Snippet:*
_{{ suggestion.email_snippet | escape_telegram_markdown }}_
