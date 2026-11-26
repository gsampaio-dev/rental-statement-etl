"""Checks for the existing Tk UI, without changing the financial core."""

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from alugueis_extrator.gui import (
    RentalExtractorWindow, STATE_READY, STATE_PROCESSING, STATE_SUCCESS,
    STATE_REVIEW, STATE_ERROR, TITLE, SUBTITLE,
)
from alugueis_extrator.gui_presentation import result_view
from alugueis_extrator.models import BatchReport, RentalRecord, ProcessingIssue, ProcessingWarning
from alugueis_extrator.ui import resources, theme
from test_batch import make_pdf


def report_at(folder, *, review=False, warnings=False, multiple=False):
    record = RentalRecord('synthetic.pdf', '012.345.678-90', 'PESSOA TESTE', Decimal('1234.56'))
    records = [record, record] if multiple else [record]
    return BatchReport(
        folder, folder / 'Relatorio_Alugueis.xlsx', folder / 'Relatorio_Alugueis.diagnostics.json',
        2 if review or warnings else 1, records,
        [ProcessingIssue('falha.pdf', 'pdf_read', 'corrompido')] if review else [],
        [ProcessingWarning('copia.pdf', 'PDF binariamente idêntico')] if warnings else [],
    )


class PresentationTests(unittest.TestCase):
    def test_multiple_events_are_distinct_from_document_count(self):
        view = result_view(report_at(Path('.'), multiple=True))
        self.assertEqual(view.metrics[:2], (('1', 'documento processado'), ('2', 'registros gerados')))
        self.assertFalse(view.needs_review)

    def test_review_and_warning_messages_are_separate(self):
        view = result_view(report_at(Path('.'), review=True, warnings=True))
        self.assertTrue(view.needs_review)
        self.assertEqual(len(view.review_items), 1)
        self.assertIn('íntegro', view.review_items[0][1])
        self.assertIn('ignorada', view.warning_items[0][1])

    def test_binary_duplicate_warning_does_not_mean_review(self):
        view = result_view(report_at(Path('.'), warnings=True))
        self.assertFalse(view.needs_review)
        self.assertEqual(len(view.warning_items), 1)

    def test_logo_is_local_and_has_expected_proportions(self):
        path = resources.product_logo_path()
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, 'product_logo.png')
        with Image.open(path) as logo:
            self.assertEqual(logo.size, (307, 150))
            self.assertEqual(logo.convert('RGBA').getchannel('A').getextrema(), (0, 255))

    def test_frozen_logo_resolves_under_bundle(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', 'bundle', create=True):
            self.assertEqual(resources.product_logo_path(), Path('bundle/alugueis_extrator/ui/assets/product_logo.png'))

    def test_build_keeps_windowed_mode_and_bundles_asset(self):
        spec = (Path(__file__).resolve().parents[1] / 'ExtratorAlugueis.spec').read_text(encoding='utf-8')
        self.assertIn('console=False', spec)
        self.assertIn('alugueis_extrator/ui/assets', spec)
        self.assertNotIn('C:\\Users\\', spec)


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.root = tk.Tk()
        self.root.withdraw()
        self.callback_errors = []
        self.root.report_callback_exception = lambda *args: self.callback_errors.append(args)
        self.window = RentalExtractorWindow(self.root)

    def tearDown(self):
        for timer in self.root.tk.call('after', 'info'):
            # Child widgets own some idle callback commands; leave deletion
            # of those commands to their own destroy(), not root.after_cancel.
            self.root.tk.call('after', 'cancel', timer)
        self.root.destroy()
        self.temp.cleanup()
        self.assertEqual(self.callback_errors, [])

    def pump_until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(0.01)
        self.fail('GUI condition timed out')

    def fake_run(self, **kwargs):
        return SimpleNamespace(report=report_at(self.folder, **kwargs), log_path=None, log_error=None)

    def selected(self):
        self.window.folder_path = self.folder
        self.window.pdf_count = 1
        self.window._set_controls_busy(False)

    def test_ready_state_keeps_title_subtitle_and_logo(self):
        w = self.window
        self.assertEqual(w.state, STATE_READY)
        self.assertEqual(w.title_label.cget('text'), TITLE)
        self.assertEqual(w.subtitle_label.cget('text'), SUBTITLE)
        self.assertIsNotNone(w.logo_image)
        self.assertFalse(w.generate_button.enabled)

    def test_invalid_competence_is_inline_and_never_calls_batch(self):
        self.selected()
        self.window.period_var.set('13/2026')
        with patch('alugueis_extrator.gui.run_application_batch') as batch:
            self.window._start_processing()
        batch.assert_not_called()
        self.assertTrue(self.window.period_error_var.get())
        self.assertFalse(self.window.busy)
        self.window.period_var.set('09/2026')
        self.assertFalse(self.window.period_error_var.get())

    def test_count_is_threaded_and_ignores_stale_results(self):
        make_pdf(self.folder / 'pasta com acentos é' / 'sintético.pdf')
        self.window._count_selected_folder(self.folder)
        self.pump_until(lambda: not self.window.busy)
        self.assertEqual(self.window.pdf_count, 1)
        self.assertTrue(self.window.generate_button.enabled)
        self.window.events.put(('count', self.folder / 'old', 99, None))
        self.window._poll_events()
        self.assertEqual(self.window.pdf_count, 1)

    def test_empty_folder_has_no_enabled_generate_button(self):
        self.window._count_selected_folder(self.folder)
        self.pump_until(lambda: not self.window.busy)
        self.assertEqual(self.window.pdf_count, 0)
        self.assertIn('Nenhum PDF', self.window.pdf_count_var.get())
        self.assertFalse(self.window.generate_button.enabled)

    def test_processing_stays_responsive_and_worker_uses_service(self):
        self.selected()
        release = threading.Event()
        heartbeat = []
        run = self.fake_run()
        def batch(folder, period):
            release.wait(4)
            return run
        try:
            with patch('alugueis_extrator.gui.run_application_batch', side_effect=batch) as service:
                self.window._start_processing()
                self.assertEqual(self.window.state, STATE_PROCESSING)
                self.assertTrue(self.window.busy)
                self.assertFalse(self.window.select_button.enabled)
                self.assertEqual(str(self.window.progress['mode']), 'indeterminate')
                self.root.after(0, lambda: heartbeat.append(True))
                self.pump_until(lambda: bool(heartbeat))
                release.set()
                self.pump_until(lambda: self.window.state == STATE_SUCCESS)
                service.assert_called_once_with(self.folder, '')
        finally:
            release.set()
        self.assertFalse(self.window.busy)
        self.assertIsNone(self.window.progress)

    def test_success_actions_and_reset(self):
        self.selected()
        self.window._show_result(self.fake_run())
        self.assertEqual(self.window.state, STATE_SUCCESS)
        self.assertEqual(self.window.output_label.cget('text'), 'Relatorio_Alugueis.xlsx')
        self.assertIsNotNone(self.window.diagnostics_button)
        self.window.new_report_button.invoke()
        self.assertEqual(self.window.state, STATE_READY)
        self.assertIsNone(self.window.folder_path)
        self.assertEqual(self.window.period_var.get(), '')
        self.assertFalse(self.window.generate_button.enabled)

    def test_review_state_preserves_all_issues(self):
        run = self.fake_run(review=True)
        run.report.errors *= 12
        self.window._show_result(run)
        self.assertEqual(self.window.state, STATE_REVIEW)
        self.assertEqual(len(self.window.review_list.inner.winfo_children()), 12)
        self.assertIn('12 documentos requerem revisão', self.window.metric_labels)

    def test_period_change_returns_result_to_ready(self):
        self.selected()
        self.window._show_result(self.fake_run())
        self.window.period_var.set('09/2026')
        self.assertEqual(self.window.state, STATE_READY)
        self.assertTrue(self.window.generate_button.enabled)

    def test_diagnostics_prefer_readable_log_and_fallback_to_json(self):
        run = self.fake_run()
        run.report.diagnostics_path.touch()
        self.window._show_result(run)
        self.assertEqual(self.window._diagnostics_target(), run.report.diagnostics_path)
        run.log_path = self.folder / 'report.execution.log'
        run.log_path.touch()
        self.assertEqual(self.window._diagnostics_target(), run.log_path)
        with patch('alugueis_extrator.gui.os.startfile', create=True) as opener:
            self.window.diagnostics_button.invoke()
        opener.assert_called_once_with(str(run.log_path))

    def test_open_folder_uses_existing_os_contract(self):
        self.selected()
        self.window._show_result(self.fake_run())
        with patch('alugueis_extrator.gui.os.startfile', create=True) as opener:
            self.window.open_folder_button.invoke()
        opener.assert_called_once_with(str(self.folder))

    def test_batch_error_is_friendly_and_retryable(self):
        self.selected()
        self.window.events.put(('batch', None, RuntimeError('technical private traceback')))
        with patch('alugueis_extrator.gui.messagebox.showerror') as error:
            self.window._poll_events()
        self.assertEqual(self.window.state, STATE_ERROR)
        self.assertTrue(self.window.retry_button.enabled)
        self.assertNotIn('traceback', str(error.call_args))

    def test_actual_gui_batch_generates_workbook_and_review_diagnostics(self):
        make_pdf(self.folder / 'demonstrativo sintético.pdf')
        (self.folder / 'inválido.pdf').write_bytes(b'not a PDF')
        self.window._count_selected_folder(self.folder)
        self.pump_until(lambda: not self.window.busy)
        self.window.generate_button.invoke()
        self.pump_until(lambda: self.window.state == STATE_REVIEW)
        run = self.window.application_run
        self.assertTrue(run.report.output_path.is_file())
        self.assertTrue(run.report.diagnostics_path.is_file())
        self.assertTrue(run.log_path.is_file())
        self.assertEqual(run.report.processed, 1)
        self.assertEqual(run.report.review_count, 1)

    def test_mapped_layout_bootstraps_card_and_handles_narrow_long_review(self):
        self.root.deiconify()
        self.root.geometry('620x500')
        self.pump_until(lambda: self.window.card.body.winfo_width() > 400)
        self.assertTrue(self.window.page.canvas.winfo_ismapped())
        self.assertTrue(self.window.card.body.winfo_ismapped())
        self.assertGreater(self.window.card.winfo_height(), 250)
        run = self.fake_run(review=True)
        run.report.errors = [ProcessingIssue('documento com nome bastante longo ' * 5 + '.pdf', 'parser', 'aluguel ausente') for _ in range(15)]
        self.window._show_result(run)
        self.pump_until(lambda: self.window.review_list.can_scroll())
        self.assertTrue(self.window.page.can_scroll())
        self.window.page.canvas.yview_moveto(1)
        self.root.update()
        buttons = [self.window.open_folder_button, self.window.diagnostics_button, self.window.new_report_button]
        self.assertEqual([int(b.grid_info()['row']) for b in buttons], [0, 1, 2])
        self.assertLessEqual(self.window.title_label.winfo_width(), self.root.winfo_width())
        for button in buttons:
            self.assertGreaterEqual(button.winfo_width(), button._natural_width())

    def test_layout_at_simulated_125_and_150_percent_dpi(self):
        self.root.update_idletasks()
        for factor in (1.25, 1.5):
            with self.subTest(scale=factor):
                for child in self.root.winfo_children():
                    child.destroy()
                self.root.tk.call('tk', 'scaling', 96 / 72 * factor)
                self.window = RentalExtractorWindow(self.root)
                self.root.geometry('1100x680')
                self.root.deiconify()
                self.pump_until(lambda: self.window.card.body.winfo_width() > 500)
                self.assertAlmostEqual(self.window.theme.scale, factor, delta=0.01)
                self.assertTrue(self.window.page.canvas.winfo_ismapped())
                self.assertGreater(int(self.window.title_label.cget('wraplength')), 200)
                image = self.window.logo_image
                self.assertAlmostEqual(image.width() / image.height(), 267 / 150, delta=0.02)
                self.window._show_result(self.fake_run(review=True))
                self.root.update()
                self.window.page.canvas.yview_moveto(1)
                self.root.update()
                self.assertTrue(self.window.new_report_button.winfo_ismapped())
                self.assertGreaterEqual(self.window.new_report_button.winfo_width(), self.window.new_report_button._natural_width())


if __name__ == '__main__':
    unittest.main(verbosity=2)
