import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from db_manager import DatabaseManager
from patterns import (
    OverdueFineFactory, DamagedBookFineFactory,
    PopularityReportBuilder, LibraryFacade,
    BaseLoanOperation, SmsNotificationDecorator,
    StandardFineStrategy, StudentDiscountStrategy,
    RareBookMultiplierStrategy, FineCalculatorContext,
    ReaderEmailObserver, ReservationSubject
)


class TestLibraryPatterns(unittest.TestCase):
    def setUp(self) -> None:
        self.test_db_path = "test_library.db"
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
        self.db = DatabaseManager(self.test_db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_factory_method_fines(self) -> None:
        overdue = OverdueFineFactory().create_fine()
        damaged = DamagedBookFineFactory().create_fine()
        self.assertEqual(overdue.get_base_rate(), 50.0)
        self.assertEqual(damaged.get_base_rate(), 500.0)

    def test_builder_report(self) -> None:
        report = (
            PopularityReportBuilder()
            .set_title("Тестовый отчёт")
            .set_period("2026-01-01", "2026-12-31")
            .add_book_stat("Чистый код", "Роберт Мартин", 12)
            .build()
        )
        self.assertEqual(report.title, "Тестовый отчёт")
        self.assertEqual(len(report.rows), 1)
        self.assertEqual(report.rows[0]["Количество выдач"], 12)

    def test_decorator_loan_operation(self) -> None:
        op = SmsNotificationDecorator(BaseLoanOperation())
        logs = op.execute("1984", "Иванов А.С.")
        self.assertEqual(len(logs), 2)
        self.assertIn("SMS-сервис", logs[1])

    def test_facade_issue_and_return(self) -> None:
        facade = LibraryFacade(self.db)
        ok, _ = facade.issue_book(book_id=1, reader_id=2)
        self.assertTrue(ok)
        ok_again, _ = facade.issue_book(book_id=1, reader_id=3)
        self.assertFalse(ok_again)

    def test_strategy_fine_calculation(self) -> None:
        calc = FineCalculatorContext(StandardFineStrategy())
        self.assertEqual(calc.compute_fine(4, 50.0), 200.0)

        calc.set_strategy(StudentDiscountStrategy())
        self.assertEqual(calc.compute_fine(4, 50.0), 100.0)

        calc.set_strategy(RareBookMultiplierStrategy())
        self.assertEqual(calc.compute_fine(4, 50.0), 400.0)

    def test_observer_notifications(self) -> None:
        subject = ReservationSubject()
        obs = ReaderEmailObserver("Иванов", "ivanov@mail.ru")
        subject.attach(obs)
        messages = subject.notify("Книга свободна")
        self.assertEqual(len(messages), 1)
        self.assertIn("ivanov@mail.ru", messages[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)