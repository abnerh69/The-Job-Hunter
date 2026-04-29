🚀 *Tier A Match Found\!*

*Role:* {{ job.title | escape_telegram_markdown }}
*Company:* {{ job.company | escape_telegram_markdown }}
*Score:* {{ job.fit_score }}/100

{% if job.score_data and job.score_data.compensation and (job.score_data.compensation.salary_min_usd_month or job.score_data.compensation.salary_max_usd_month) %}
*Salary:* {{ (job.score_data.compensation.salary_min_usd_month or 0) | format_currency('USD') }} \- {{ (job.score_data.compensation.salary_max_usd_month or 0) | format_currency('USD') }}/mo
{% endif %}

*Top Match Points:*
{% if job.score_data and job.score_data.match_analysis and job.score_data.match_analysis.key_match_points %}
{% for point in job.score_data.match_analysis.key_match_points[:3] %}
• {{ point | escape_telegram_markdown }}
{% endfor %}
{% endif %}

[View Job Post]({{ job.url }})
