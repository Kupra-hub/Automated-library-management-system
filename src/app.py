import streamlit as st
from datetime import datetime, timedelta
from db_manager import DatabaseManager
from patterns import (
    OverdueFineFactory, DamagedBookFineFactory,
    PopularityReportBuilder, LibraryFacade,
    BaseLoanOperation, SmsNotificationDecorator, RareBookInsuranceDecorator,
    StandardFineStrategy, StudentDiscountStrategy, RareBookMultiplierStrategy,
    FineCalculatorContext, ReaderEmailObserver, ReservationSubject
)

st.set_page_config(page_title="АИС Библиотека", layout="wide")
db = DatabaseManager()
facade = LibraryFacade(db)

st.title("Автоматизированная система управления библиотекой")

tabs = st.tabs([
    "1. Каталог книг",
    "2. Выдача и возврат",
    "3. Расчёт штрафов",
    "4. Бронирование",
    "5. Отчёт по популярности",
    "6. Управление читателями"
])

# Каталог книг с фильтрацией
with tabs[0]:
    st.subheader("Каталог библиотечного фонда")
    with db.get_connection() as conn:
        authors = ["Все"] + [r["FullName"] for r in conn.execute("SELECT FullName FROM Author;").fetchall()]
        genres = ["Все"] + [r["Name"] for r in conn.execute("SELECT Name FROM Category;").fetchall()]
        years = ["Все"] + [str(r["Year"]) for r in conn.execute("SELECT DISTINCT Year FROM Book ORDER BY Year DESC;").fetchall()]

    col1, col2, col3 = st.columns(3)
    sel_author = col1.selectbox("Фильтр по автору", authors)
    sel_genre = col2.selectbox("Фильтр по жанру", genres)
    sel_year = col3.selectbox("Фильтр по году издания", years)

    query = """
        SELECT b.ISBN, b.Title AS Название, a.FullName AS Автор,
               c.Name AS Жанр, p.Name AS Издательство, b.Year AS Год, b.Status AS Статус
        FROM Book b
        JOIN Author a ON b.AuthorId = a.Id
        JOIN Category c ON b.CategoryId = c.Id
        JOIN Publisher p ON b.PublisherId = p.Id
        WHERE 1=1
    """
    params = []
    if sel_author != "Все":
        query += " AND a.FullName = ?"
        params.append(sel_author)
    if sel_genre != "Все":
        query += " AND c.Name = ?"
        params.append(sel_genre)
    if sel_year != "Все":
        query += " AND b.Year = ?"
        params.append(int(sel_year))

    with db.get_connection() as conn:
        books_data = [dict(row) for row in conn.execute(query, params).fetchall()]
    st.dataframe(books_data, use_container_width=True)

# Оформление выдачи и возврата
with tabs[1]:
    st.subheader("Оформление выдачи и возврата книг")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Выдача книги читателю**")
        with db.get_connection() as conn:
            avail_books = conn.execute("SELECT Id, Title, IsRare FROM Book WHERE Status = 'Available';").fetchall()
            readers = conn.execute("SELECT Id, FullName, TicketNumber FROM Reader;").fetchall()

        if avail_books and readers:
            book_map = {f"{b['Title']} (ID: {b['Id']})": b for b in avail_books}
            reader_map = {f"{r['FullName']} [{r['TicketNumber']}]": r for r in readers}

            chosen_book_label = st.selectbox("Выберите доступную книгу", list(book_map.keys()))
            chosen_reader_label = st.selectbox("Выберите читателя", list(reader_map.keys()))
            add_sms = st.checkbox("Добавить SMS-уведомление", value=True)
            add_ins = st.checkbox("Добавить акт сохранности редкой книги")

            if st.button("Оформить выдачу"):
                b_obj = book_map[chosen_book_label]
                r_obj = reader_map[chosen_reader_label]
                ok, msg = facade.issue_book(b_obj["Id"], r_obj["Id"])
                if ok:
                    operation = BaseLoanOperation()
                    if add_sms:
                        operation = SmsNotificationDecorator(operation)
                    if add_ins:
                        operation = RareBookInsuranceDecorator(operation)
                    logs = operation.execute(b_obj["Title"], r_obj["FullName"])
                    st.success(msg)
                    for line in logs:
                        st.info(line)
                else:
                    st.error(msg)

    with c2:
        st.markdown("**Активные выдачи и возврат**")
        with db.get_connection() as conn:
            active_loans = conn.execute("""
                SELECT l.Id, b.Title, r.FullName, l.IssueDate, l.DueDate
                FROM Loan l
                JOIN Book b ON l.BookId = b.Id
                JOIN Reader r ON l.ReaderId = r.Id
                WHERE l.ReturnDate IS NULL;
            """).fetchall()
        if active_loans:
            st.dataframe([dict(r) for r in active_loans], use_container_width=True)
            loan_ids = {f"Выдача #{r['Id']}: {r['Title']} ({r['FullName']})": r["Id"] for r in active_loans}
            sel_return = st.selectbox("Выберите выдачу для возврата", list(loan_ids.keys()))
            if st.button("Принять возврат книги"):
                ok, msg = facade.return_book(loan_ids[sel_return])
                st.success(msg) if ok else st.error(msg)
        else:
            st.info("Активных выдач нет.")

# Автоматический расчёт штрафа
with tabs[2]:
    st.subheader("Расчёт и начисление штрафов")
    with db.get_connection() as conn:
        loans = conn.execute("""
            SELECT l.Id, b.Title, b.IsRare, r.FullName, r.IsStudent, l.DueDate
            FROM Loan l
            JOIN Book b ON l.BookId = b.Id
            JOIN Reader r ON l.ReaderId = r.Id;
        """).fetchall()

    loan_options = {f"{r['Id']} — {r['Title']} (Читатель: {r['FullName']}, срок до {r['DueDate']})": r for r in loans}
    selected_loan = loan_options[st.selectbox("Выберите запись выдачи", list(loan_options.keys()))]
    fine_type = st.radio("Тип нарушения", ["Просрочка возврата", "Повреждение книги"])
    days_late = st.number_input("Количество дней просрочки", min_value=1, max_value=365, value=6)

    if st.button("Рассчитать и зафиксировать штраф"):
        factory = OverdueFineFactory() if fine_type == "Просрочка возврата" else DamagedBookFineFactory()
        fine_product = factory.create_fine()

        if selected_loan["IsRare"]:
            strategy = RareBookMultiplierStrategy()
            tariff_name = "Повышенный тариф (редкое издание x2)"
        elif selected_loan["IsStudent"]:
            strategy = StudentDiscountStrategy()
            tariff_name = "Льготный тариф (студент -50%)"
        else:
            strategy = StandardFineStrategy()
            tariff_name = "Стандартный тариф"

        calculator = FineCalculatorContext(strategy)
        total_amount = calculator.compute_fine(days_late, fine_product.get_base_rate())

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO Fine (LoanId, Amount, Reason, IsPaid) VALUES (?, ?, ?, 0);",
                (selected_loan["Id"], total_amount, fine_product.get_description())
            )
            conn.commit()

        st.warning(f"Применена стратегия: {tariff_name}")
        st.success(f"Начислен штраф: {total_amount} руб. ({fine_product.get_description()})")

# Бронирование книги
with tabs[3]:
    st.subheader("Бронирование литературы и оповещение читателей")
    with db.get_connection() as conn:
        all_books = conn.execute("SELECT Id, Title, Status FROM Book;").fetchall()
        all_readers = conn.execute("SELECT Id, FullName, Contacts FROM Reader;").fetchall()

    b_dict = {f"{b['Title']} [{b['Status']}]": b for b in all_books}
    r_dict = {f"{r['FullName']} ({r['Contacts']})": r for r in all_readers}

    b_sel = b_dict[st.selectbox("Книга для бронирования", list(b_dict.keys()))]
    r_sel = r_dict[st.selectbox("Читатель", list(r_dict.keys()))]

    if st.button("Оформить бронь и подписать на уведомление"):
        res_date = datetime.now().strftime("%Y-%m-%d")
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO Reservation (BookId, ReaderId, ReservationDate, Status) VALUES (?, ?, ?, 'Active');",
                (b_sel["Id"], r_sel["Id"], res_date)
            )
            conn.commit()

        subject = ReservationSubject()
        observer = ReaderEmailObserver(r_sel["FullName"], r_sel["Contacts"])
        subject.attach(observer)
        notifications = subject.notify(f"Книга «{b_sel['Title']}» зарезервирована за вами ({res_date}).")
        st.success("Бронирование успешно сохранено в БД")
        for note in notifications:
            st.info(note)

# Отчёт по популярным книгам
with tabs[4]:
    st.subheader("Отчёт по популярным книгам за период")
    d_from = st.date_input("Дата начала периода", value=datetime.now() - timedelta(days=60))
    d_to = st.date_input("Дата окончания периода", value=datetime.now())

    if st.button("Сформировать отчёт"):
        with db.get_connection() as conn:
            stats = conn.execute("""
                SELECT b.Title, a.FullName AS AuthorName, COUNT(l.Id) AS TotalLoans
                FROM Loan l
                JOIN Book b ON l.BookId = b.Id
                JOIN Author a ON b.AuthorId = a.Id
                WHERE l.IssueDate BETWEEN ? AND ?
                GROUP BY b.Id
                ORDER BY TotalLoans DESC;
            """, (d_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d"))).fetchall()

        builder = (
            PopularityReportBuilder()
            .set_title("Отчёт по наиболее востребованным книгам")
            .set_period(d_from.strftime("%Y-%m-%d"), d_to.strftime("%Y-%m-%d"))
            .set_timestamp()
        )
        for row in stats:
            builder.add_book_stat(row["Title"], row["AuthorName"], row["TotalLoans"])

        report = builder.build()
        st.markdown(f"### {report.title}")
        st.caption(f"Период: {report.period} | Сформировано: {report.generated_at}")
        st.table(report.rows)

# Управление читателями
with tabs[5]:
    st.subheader("Управление списком читателей")

    col_add, col_edit = st.columns(2)

    with col_add:
        st.markdown("### Добавить нового читателя")
        new_name = st.text_input("ФИО читателя", placeholder="Иванов Иван Иванович")
        new_ticket = st.text_input("Номер читательского билета", placeholder="LIB-1004")
        new_contacts = st.text_input("Контакты (Email / телефон)", placeholder="ivanov@mail.ru")
        new_is_student = st.checkbox("Является студентом (льготный тариф)", value=True)

        if st.button("Сохранить нового читателя"):
            if new_name and new_ticket:
                try:
                    with db.get_connection() as conn:
                        conn.execute(
                            "INSERT INTO Reader (FullName, TicketNumber, Contacts, IsStudent) VALUES (?, ?, ?, ?);",
                            (new_name, new_ticket, new_contacts, 1 if new_is_student else 0)
                        )
                        conn.commit()
                    st.success(f"Читатель «{new_name}» успешно добавлен!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка при добавлении (возможно, номер билета уже занят): {e}")
            else:
                st.warning("Заполните ФИО и номер читательского билета.")

    with col_edit:
        st.markdown("### Редактировать читателя")
        with db.get_connection() as conn:
            readers_list = conn.execute(
                "SELECT Id, FullName, TicketNumber, Contacts, IsStudent FROM Reader;").fetchall()

        if readers_list:
            reader_map = {f"{r['FullName']} [{r['TicketNumber']}] (ID: {r['Id']})": r for r in readers_list}
            selected_r_label = st.selectbox("Выберите читателя для изменения", list(reader_map.keys()))
            curr_r = reader_map[selected_r_label]

            edit_name = st.text_input("Изменить ФИО", value=curr_r["FullName"], key="edit_name")
            edit_contacts = st.text_input("Изменить контакты", value=curr_r["Contacts"] or "", key="edit_contacts")
            edit_student = st.checkbox("Является студентом", value=bool(curr_r["IsStudent"]), key="edit_student")

            if st.button("Обновить данные читателя"):
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE Reader SET FullName = ?, Contacts = ?, IsStudent = ? WHERE Id = ?;",
                        (edit_name, edit_contacts, 1 if edit_student else 0, curr_r["Id"])
                    )
                    conn.commit()
                st.success("Данные читателя успешно обновлены!")
                st.rerun()
        else:
            st.info("В базе пока нет читателей.")