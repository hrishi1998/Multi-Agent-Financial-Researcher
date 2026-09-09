from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.api.schemas.reports import ResearchReport

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _safe_token(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return cleaned.strip("_") or "report"


class ReportExporter:
    """Render a ResearchReport to Markdown and write it under outputs/."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        directory = Path(template_dir) if template_dir else TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(directory)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate_markdown(self, report: ResearchReport) -> str:
        template = self._env.get_template("report.md.j2")
        return template.render(report=report).strip() + "\n"

    def report_filename(self, report: ResearchReport) -> str:
        ticker = _safe_token(report.ticker)
        period = _safe_token(report.analysis_period)
        run_id = _safe_token(report.run_id)
        return f"{ticker}_{period}_{run_id}.md"

    async def export_to_disk(
        self,
        report: ResearchReport,
        output_dir: str = "outputs/",
    ) -> Path:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / self.report_filename(report)
        path.write_text(self.generate_markdown(report), encoding="utf-8")
        return path
