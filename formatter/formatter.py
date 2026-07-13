"""Renders the Jinja2 HTML newspaper template."""

import os
from datetime import datetime
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader


def render_newspaper(state: Dict[str, Any]) -> str:
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(templates_dir), autoescape=True)
    template = env.get_template("newspaper.html")

    now = datetime.now()
    week_number = now.isocalendar()[1]

    return template.render(
        editorial=state.get("editorial", {}),
        issue_date=state.get("issue_date", now.strftime("%B %d, %Y")),
        week_number=state.get("week_number", week_number),
    )
