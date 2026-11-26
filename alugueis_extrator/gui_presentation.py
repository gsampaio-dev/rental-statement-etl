"""Human-readable result text for the GUI, kept outside the batch parser."""

from dataclasses import dataclass

from .models import BatchReport, ProcessingIssue, ProcessingWarning


def result_summary(report: BatchReport) -> str:
    return "\n".join(
        (
            f"PDFs encontrados: {report.total_pdfs}",
            f"Documentos processados com sucesso: {report.processed}",
            f"Registros gerados: {report.records_generated}",
            f"Documentos para revisão: {report.review_count}",
            "Falhas técnicas do lote: 0",
            f"Avisos: {len(report.warnings)}",
        )
    )


def friendly_issue(issue: ProcessingIssue) -> str:
    reason = issue.reason.casefold()
    if issue.stage == "pdf_read":
        return "Não foi possível abrir este PDF. Verifique se o arquivo está íntegro."
    if "rubrica financeira desconhecida" in reason:
        return "Rubrica financeira não reconhecida; o documento requer revisão."
    if "aluguel" in reason or "rubrica principal suportada" in reason:
        return "Valor do aluguel não identificado com segurança."
    if "cpf" in reason or "inq." in reason:
        return "CPF ou nome do inquilino ausente, inválido ou ambíguo."
    if issue.stage == "validation":
        return "Os dados extraídos não passaram pela validação."
    return "Formato ou campos não reconhecidos com segurança; requer revisão."


def friendly_warning(warning: ProcessingWarning) -> str:
    reason = warning.reason.casefold()
    if "binariamente idêntico" in reason:
        return "PDF idêntico a outro arquivo; esta cópia foi ignorada."
    if "possível duplicidade" in reason:
        return "Possível duplicidade. O registro foi mantido no Excel."
    return "Aviso de processamento; consulte os diagnósticos para detalhes."


def result_details(report: BatchReport) -> str:
    lines: list[str] = []
    for issue in report.errors:
        lines.extend((issue.file, friendly_issue(issue), ""))
    for warning in report.warnings:
        lines.extend((warning.file, friendly_warning(warning), ""))
    return "\n".join(lines).strip()


def _counted(count: int, singular: str, plural: str) -> tuple[str, str]:
    return str(count), singular if count == 1 else plural


@dataclass(frozen=True)
class ResultView:
    """Read-only view of a finished batch for the result cards of the GUI."""

    needs_review: bool
    title: str
    metrics: tuple[tuple[str, str], ...]
    review_items: tuple[tuple[str, str], ...]
    warning_items: tuple[tuple[str, str], ...]
    output_name: str


def result_view(report: BatchReport) -> ResultView:
    """Group the report numbers exactly as produced by the batch core.

    "erros" mirrors the former "Falhas técnicas do lote: 0": a technical
    failure of the batch never yields a report (the GUI shows an error state
    instead), while documents that could not be read or validated are listed
    for review, as decided by the core.
    """

    needs_review = report.review_count > 0
    if needs_review:
        title = "Processamento concluído com itens para revisão"
        metrics = (
            _counted(
                report.processed,
                "documento processado com sucesso",
                "documentos processados com sucesso",
            ),
            _counted(report.records_generated, "registro gerado", "registros gerados"),
            _counted(
                report.review_count, "documento requer revisão", "documentos requerem revisão"
            ),
            ("0", "erros"),
        )
    else:
        title = "Processamento concluído"
        metrics = (
            _counted(report.processed, "documento processado", "documentos processados"),
            _counted(report.records_generated, "registro gerado", "registros gerados"),
            _counted(report.review_count, "documento para revisão", "documentos para revisão"),
            ("0", "erros"),
        )
    return ResultView(
        needs_review=needs_review,
        title=title,
        metrics=metrics,
        review_items=tuple((issue.file, friendly_issue(issue)) for issue in report.errors),
        warning_items=tuple(
            (warning.file, friendly_warning(warning)) for warning in report.warnings
        ),
        output_name=report.output_path.name,
    )
