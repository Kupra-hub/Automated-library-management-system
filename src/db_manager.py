import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator


class DatabaseManager:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "..", "library.db")
        self.db_path = db_path
        self._init_tables()
        self._seed_data()

    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_tables(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Author (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    FullName TEXT NOT NULL,
                    Biography TEXT,
                    Country TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Publisher (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Name TEXT NOT NULL,
                    Address TEXT,
                    Contacts TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Category (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Name TEXT NOT NULL,
                    Description TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Book (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ISBN TEXT UNIQUE NOT NULL,
                    Title TEXT NOT NULL,
                    Year INTEGER,
                    AuthorId INTEGER,
                    PublisherId INTEGER,
                    CategoryId INTEGER,
                    IsRare INTEGER DEFAULT 0,
                    Status TEXT DEFAULT 'Available',
                    FOREIGN KEY (AuthorId) REFERENCES Author(Id),
                    FOREIGN KEY (PublisherId) REFERENCES Publisher(Id),
                    FOREIGN KEY (CategoryId) REFERENCES Category(Id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Reader (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    FullName TEXT NOT NULL,
                    TicketNumber TEXT UNIQUE NOT NULL,
                    Contacts TEXT,
                    IsStudent INTEGER DEFAULT 0
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Loan (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    BookId INTEGER NOT NULL,
                    ReaderId INTEGER NOT NULL,
                    IssueDate TEXT NOT NULL,
                    DueDate TEXT NOT NULL,
                    ReturnDate TEXT,
                    FOREIGN KEY (BookId) REFERENCES Book(Id),
                    FOREIGN KEY (ReaderId) REFERENCES Reader(Id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Fine (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    LoanId INTEGER NOT NULL,
                    Amount REAL NOT NULL,
                    Reason TEXT,
                    IsPaid INTEGER DEFAULT 0,
                    FOREIGN KEY (LoanId) REFERENCES Loan(Id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Reservation (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    BookId INTEGER NOT NULL,
                    ReaderId INTEGER NOT NULL,
                    ReservationDate TEXT NOT NULL,
                    Status TEXT DEFAULT 'Active',
                    FOREIGN KEY (BookId) REFERENCES Book(Id),
                    FOREIGN KEY (ReaderId) REFERENCES Reader(Id)
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Librarian (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    FullName TEXT NOT NULL,
                    Shift TEXT,
                    Contacts TEXT
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Inventory (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    BookId INTEGER NOT NULL,
                    LibrarianId INTEGER NOT NULL,
                    CheckDate TEXT NOT NULL,
                    Status TEXT NOT NULL,
                    FOREIGN KEY (BookId) REFERENCES Book(Id),
                    FOREIGN KEY (LibrarianId) REFERENCES Librarian(Id)
                );
            """)
            conn.commit()

    def _seed_data(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Book;")
            if cursor.fetchone()[0] > 0:
                return

            cursor.executemany(
                "INSERT INTO Author (FullName, Biography, Country) VALUES (?, ?, ?);",
                [
                    ("Роберт Мартин", "Инженер-программист, автор книг по Agile и архитектуре ПО", "США"),
                    ("Эрих Гамма", "Один из авторов классической книги GoF по паттернам проектирования", "Швейцария"),
                    ("Фёдор Достоевский", "Классик мировой литературы", "Россия"),
                    ("Джордж Оруэлл", "Британский писатель и публицист", "Великобритания"),
                ]
            )
            cursor.executemany(
                "INSERT INTO Publisher (Name, Address, Contacts) VALUES (?, ?, ?);",
                [
                    ("Питер", "Санкт-Петербург", "info@piter.com"),
                    ("АСТ", "Москва", "info@ast.ru"),
                ]
            )
            cursor.executemany(
                "INSERT INTO Category (Name, Description) VALUES (?, ?);",
                [
                    ("Программирование", "Техническая литература по разработке ПО"),
                    ("Классика", "Художественная классическая литература"),
                    ("Антиутопия", "Социально-философская фантастика"),
                ]
            )
            cursor.executemany(
                """INSERT INTO Book (ISBN, Title, Year, AuthorId, PublisherId, CategoryId, IsRare, Status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                [
                    ("978-5-4461-0960-9", "Чистая архитектура", 2021, 1, 1, 1, 0, "Available"),
                    ("978-5-4461-1595-2", "Паттерны объектно-ориентированного проектирования", 2020, 2, 1, 1, 1, "Available"),
                    ("978-5-17-090630-7", "Преступление и наказание", 2019, 3, 2, 2, 0, "Issued"),
                    ("978-5-17-080115-2", "1984", 2022, 4, 2, 3, 0, "Available"),
                    ("978-5-4461-0772-8", "Чистый код", 2023, 1, 1, 1, 0, "Available"),
                ]
            )
            cursor.executemany(
                "INSERT INTO Reader (FullName, TicketNumber, Contacts, IsStudent) VALUES (?, ?, ?, ?);",
                [
                    ("Чаннов Павел Сергеевич", "LIB-1001", "channov@mail.ru", 1),
                    ("Смирнова Елена Викторовна", "LIB-1002", "smirnova@mail.ru", 0),
                    ("Кузнецов Дмитрий Андреевич", "LIB-1003", "kuznetsov@mail.ru", 1),
                ]
            )
            cursor.executemany(
                "INSERT INTO Librarian (FullName, Shift, Contacts) VALUES (?, ?, ?);",
                [("Петрова Ольга Ивановна", "Утренняя", "petrova@lib.ru")]
            )

            today = datetime.now()
            overdue_issue = (today - timedelta(days=20)).strftime("%Y-%m-%d")
            overdue_due = (today - timedelta(days=6)).strftime("%Y-%m-%d")
            past_issue = (today - timedelta(days=40)).strftime("%Y-%m-%d")
            past_due = (today - timedelta(days=26)).strftime("%Y-%m-%d")
            past_ret = (today - timedelta(days=28)).strftime("%Y-%m-%d")

            cursor.executemany(
                "INSERT INTO Loan (BookId, ReaderId, IssueDate, DueDate, ReturnDate) VALUES (?, ?, ?, ?, ?);",
                [
                    (3, 1, overdue_issue, overdue_due, None),
                    (1, 2, past_issue, past_due, past_ret),
                    (1, 3, past_issue, past_due, past_ret),
                    (5, 1, past_issue, past_due, past_ret),
                ]
            )
            cursor.execute(
                "INSERT INTO Inventory (BookId, LibrarianId, CheckDate, Status) VALUES (?, ?, ?, ?);",
                (1, 1, today.strftime("%Y-%m-%d"), "Проверено, в наличии")
            )
            conn.commit()