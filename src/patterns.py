from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from db_manager import DatabaseManager


# 1. Factory Method
class FineProduct(ABC):
    @abstractmethod
    def get_description(self) -> str:
        pass

    @abstractmethod
    def get_base_rate(self) -> float:
        pass


class OverdueFine(FineProduct):
    def get_description(self) -> str:
        return "Штраф за просрочку возврата книги"

    def get_base_rate(self) -> float:
        return 50.0


class DamagedBookFine(FineProduct):
    def get_description(self) -> str:
        return "Штраф за повреждение переплёта или страниц"

    def get_base_rate(self) -> float:
        return 500.0


class FineFactory(ABC):
    @abstractmethod
    def create_fine(self) -> FineProduct:
        pass


class OverdueFineFactory(FineFactory):
    def create_fine(self) -> FineProduct:
        return OverdueFine()


class DamagedBookFineFactory(FineFactory):
    def create_fine(self) -> FineProduct:
        return DamagedBookFine()


# 2. Builder
@dataclass
class PopularityReport:
    title: str = ""
    period: str = ""
    generated_at: str = ""
    rows: list[dict] = field(default_factory=list)


class PopularityReportBuilder:
    def __init__(self) -> None:
        self._report = PopularityReport()

    def set_title(self, title: str) -> "PopularityReportBuilder":
        self._report.title = title
        return self

    def set_period(self, date_from: str, date_to: str) -> "PopularityReportBuilder":
        self._report.period = f"с {date_from} по {date_to}"
        return self

    def set_timestamp(self) -> "PopularityReportBuilder":
        self._report.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        return self

    def add_book_stat(self, book_title: str, author: str, loans_count: int) -> "PopularityReportBuilder":
        self._report.rows.append({
            "Название книги": book_title,
            "Автор": author,
            "Количество выдач": loans_count
        })
        return self

    def build(self) -> PopularityReport:
        return self._report


# 3. Decorator
class LoanOperation(ABC):
    @abstractmethod
    def execute(self, book_title: str, reader_name: str) -> list[str]:
        pass


class BaseLoanOperation(LoanOperation):
    def execute(self, book_title: str, reader_name: str) -> list[str]:
        return [f"Оформлена стандартная выдача книги «{book_title}» читателю {reader_name}."]


class LoanOperationDecorator(LoanOperation):
    def __init__(self, wrapped: LoanOperation) -> None:
        self._wrapped = wrapped

    def execute(self, book_title: str, reader_name: str) -> list[str]:
        return self._wrapped.execute(book_title, reader_name)


class SmsNotificationDecorator(LoanOperationDecorator):
    def execute(self, book_title: str, reader_name: str) -> list[str]:
        logs = super().execute(book_title, reader_name)
        logs.append(f"[SMS-сервис]: Отправлено уведомление о дате возврата для {reader_name}.")
        return logs


class RareBookInsuranceDecorator(LoanOperationDecorator):
    def execute(self, book_title: str, reader_name: str) -> list[str]:
        logs = super().execute(book_title, reader_name)
        logs.append(f"[Страхование]: Активирован акт сохранности редкого экземпляра «{book_title}».")
        return logs


# 4. Facade
from datetime import datetime, timedelta
from db_manager import DatabaseManager


class LibraryFacade:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def issue_book(self, book_id: int, reader_id: int, days: int = 14) -> tuple[bool, str]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT Status FROM Book WHERE Id = ?;", (book_id,))
            book = cur.fetchone()
            if not book or book["Status"] != "Available":
                return False, "Ошибка: книга недоступна для выдачи."

            cur.execute(
                "SELECT COUNT(*) FROM Fine f JOIN Loan l ON f.LoanId = l.Id WHERE l.ReaderId = ? AND f.IsPaid = 0;",
                (reader_id,)
            )
            if cur.fetchone()[0] > 0:
                return False, "Ошибка: у читателя есть неоплаченные штрафы."

            issue_date = datetime.now().strftime("%Y-%m-%d")
            due_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            cur.execute(
                "INSERT INTO Loan (BookId, ReaderId, IssueDate, DueDate) VALUES (?, ?, ?, ?);",
                (book_id, reader_id, issue_date, due_date)
            )
            cur.execute("UPDATE Book SET Status = 'Issued' WHERE Id = ?;", (book_id,))
            conn.commit()
            return True, f"Книга успешно выдана до {due_date}."

    def return_book(self, loan_id: int) -> tuple[bool, str]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT BookId, ReturnDate FROM Loan WHERE Id = ?;", (loan_id,))
            loan = cur.fetchone()
            if not loan or loan["ReturnDate"] is not None:
                return False, "Ошибка: выдача не найдена или уже закрыта."

            ret_date = datetime.now().strftime("%Y-%m-%d")
            cur.execute("UPDATE Loan SET ReturnDate = ? WHERE Id = ?;", (ret_date, loan_id))
            cur.execute("UPDATE Book SET Status = 'Available' WHERE Id = ?;", (loan["BookId"],))
            conn.commit()
            return True, "Книга возвращена в фонд библиотеки."

    def perform_inventory_check(self, librarian_id: int, book_id: int, status: str) -> tuple[bool, str]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()

            cur.execute("SELECT Id, FullName FROM Librarian WHERE Id = ?;", (librarian_id,))
            librarian = cur.fetchone()
            if not librarian:
                return False, "Ошибка: указанный библиотекарь не найден в системе."

            cur.execute("SELECT Id, Title FROM Book WHERE Id = ?;", (book_id,))
            book = cur.fetchone()
            if not book:
                return False, "Ошибка: книга не найдена в каталоге."

            check_date = datetime.now().strftime("%Y-%m-%d")
            cur.execute(
                """
                INSERT INTO Inventory (BookId, LibrarianId, CheckDate, Status) 
                VALUES (?, ?, ?, ?);
                """,
                (book_id, librarian_id, check_date, status)
            )
            conn.commit()
            return True, f"Инвентаризация книги «{book['Title']}» успешно проведена сотрудником {librarian['FullName']}."

# 5. Strategy
class FineCalculationStrategy(ABC):
    @abstractmethod
    def calculate(self, days_overdue: int, base_rate: float) -> float:
        pass


class StandardFineStrategy(FineCalculationStrategy):
    def calculate(self, days_overdue: int, base_rate: float) -> float:
        return round(days_overdue * base_rate, 2)


class StudentDiscountStrategy(FineCalculationStrategy):
    def calculate(self, days_overdue: int, base_rate: float) -> float:
        return round(days_overdue * base_rate * 0.5, 2)


class RareBookMultiplierStrategy(FineCalculationStrategy):
    def calculate(self, days_overdue: int, base_rate: float) -> float:
        return round(days_overdue * base_rate * 2.0, 2)


class FineCalculatorContext:
    def __init__(self, strategy: FineCalculationStrategy) -> None:
        self._strategy = strategy

    def set_strategy(self, strategy: FineCalculationStrategy) -> None:
        self._strategy = strategy

    def compute_fine(self, days_overdue: int, base_rate: float) -> float:
        return self._strategy.calculate(max(0, days_overdue), base_rate)


# 6. Observer
class LibraryObserver(ABC):
    @abstractmethod
    def update(self, event_message: str) -> str:
        pass


class ReaderEmailObserver(LibraryObserver):
    def __init__(self, reader_name: str, email: str) -> None:
        self.reader_name = reader_name
        self.email = email

    def update(self, event_message: str) -> str:
        return f"Уведомление на {self.email} ({self.reader_name}): {event_message}"


class ReservationSubject:
    def __init__(self) -> None:
        self._observers: list[LibraryObserver] = []

    def attach(self, observer: LibraryObserver) -> None:
        self._observers.append(observer)

    def detach(self, observer: LibraryObserver) -> None:
        self._observers.remove(observer)

    def notify(self, event_message: str) -> list[str]:
        return [observer.update(event_message) for observer in self._observers]