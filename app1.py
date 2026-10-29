
import sqlite3
import hashlib
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# =========================================================
# STAYFLOW HOTEL MANAGEMENT SYSTEM
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "hotel.db"

st.set_page_config(
    page_title="StayFlow Hotel Management",
    page_icon="🏨",
    layout="wide"
)


# =========================================================
# DATABASE HELPERS
# =========================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def columns(conn, table):
    return [
        row["name"]
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def ensure_column(conn, table, column, definition):
    if column not in columns(conn, table):
        conn.execute(
            f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}'
        )


def initialize_database():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'Staff',
            active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS owner (
            id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            hotel_name TEXT
        );

        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE,
            room_type TEXT,
            price REAL DEFAULT 0,
            status TEXT DEFAULT 'Available',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_name TEXT,
            phone TEXT,
            room_id INTEGER,
            check_in TEXT,
            check_out TEXT,
            guests INTEGER DEFAULT 1,
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'Confirmed',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            booking_id INTEGER,
            amount REAL DEFAULT 0,
            method TEXT,
            payment_date TEXT,
            received_by TEXT,
            note TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            role TEXT,
            phone TEXT,
            salary REAL DEFAULT 0,
            shift TEXT DEFAULT 'General',
            status TEXT DEFAULT 'Active'
        );
        """)

        # Compatibility with old databases:
        # Existing records are retained. Missing ID columns are added.
        definitions = {
            "users": {
                "id": "INTEGER",
                "username": "TEXT",
                "password_hash": "TEXT",
                "full_name": "TEXT",
                "role": "TEXT DEFAULT 'Staff'",
                "active": "INTEGER DEFAULT 1",
            },
            "rooms": {
                "id": "INTEGER",
                "room_number": "TEXT",
                "room_type": "TEXT",
                "price": "REAL DEFAULT 0",
                "status": "TEXT DEFAULT 'Available'",
                "notes": "TEXT DEFAULT ''",
            },
            "bookings": {
                "id": "INTEGER",
                "guest_name": "TEXT",
                "phone": "TEXT",
                "room_id": "INTEGER",
                "check_in": "TEXT",
                "check_out": "TEXT",
                "guests": "INTEGER DEFAULT 1",
                "total_amount": "REAL DEFAULT 0",
                "status": "TEXT DEFAULT 'Confirmed'",
                "notes": "TEXT DEFAULT ''",
            },
            "payments": {
                "id": "INTEGER",
                "customer_name": "TEXT",
                "booking_id": "INTEGER",
                "amount": "REAL DEFAULT 0",
                "method": "TEXT",
                "payment_date": "TEXT",
                "received_by": "TEXT",
                "note": "TEXT DEFAULT ''",
            },
            "employees": {
                "id": "INTEGER",
                "name": "TEXT",
                "role": "TEXT",
                "phone": "TEXT",
                "salary": "REAL DEFAULT 0",
                "shift": "TEXT DEFAULT 'General'",
                "status": "TEXT DEFAULT 'Active'",
            },
        }

        for table, fields in definitions.items():
            for field, definition in fields.items():
                ensure_column(conn, table, field, definition)

            conn.execute(
                f'UPDATE "{table}" SET id = rowid WHERE id IS NULL'
            )

            conn.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS '
                f'idx_{table}_id ON "{table}"(id)'
            )

            conn.executescript(f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_id
            AFTER INSERT ON "{table}"
            WHEN NEW.id IS NULL
            BEGIN
                UPDATE "{table}"
                SET id = NEW.rowid
                WHERE rowid = NEW.rowid;
            END;
            """)

        # Create default admin only if no account exists.
        user_count = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

        if user_count == 0:
            conn.execute("""
                INSERT INTO users
                (username, password_hash, full_name, role, active)
                VALUES (?, ?, ?, ?, 1)
            """, (
                "admin",
                password_hash("admin123"),
                "Hotel Admin",
                "Admin"
            ))


initialize_database()


def read_df(sql, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql, params=()):
    with get_conn() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid


def money(amount):
    return f"₹{float(amount or 0):,.2f}"


def room_statuses():
    return ["Available", "Occupied", "Reserved", "Maintenance"]


def booking_statuses():
    return ["Confirmed", "Checked-in", "Checked-out", "Cancelled"]


# =========================================================
# LOGIN
# =========================================================

if "logged_user" not in st.session_state:
    st.session_state.logged_user = None

if st.session_state.logged_user is None:
    st.markdown(
        "<h1 style='text-align:center;color:#0f766e'>🏨 StayFlow</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='text-align:center'>Hotel Management System</p>",
        unsafe_allow_html=True
    )

    _, middle, _ = st.columns([1, 1.2, 1])

    with middle:
        with st.form("login_form"):
            st.subheader("Welcome Back")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login = st.form_submit_button(
                "Login", use_container_width=True
            )

        if login:
            df = read_df("""
                SELECT id, username, full_name, role
                FROM users
                WHERE username = ?
                  AND password_hash = ?
                  AND active = 1
            """, (username.strip(), password_hash(password)))

            if not df.empty:
                st.session_state.logged_user = df.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("Username ya password galat hai.")

        st.info("Default login: admin / admin123")
    st.stop()

user = st.session_state.logged_user


# =========================================================
# PROFESSIONAL DESIGN
# =========================================================

st.markdown("""
<style>
.stApp {
    background: linear-gradient(180deg, #f4f8fb, #edf5f6);
}
.block-container {
    max-width: 1500px;
    padding-top: 1.4rem;
}
[data-testid="stMetric"] {
    background: white;
    border: 1px solid #d9e7eb;
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 5px 18px rgba(18,55,75,.06);
}
[data-testid="stMetricValue"] {
    color: #0f766e;
    font-weight: 750;
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #102a43, #164e63);
}
section[data-testid="stSidebar"] * {
    color: white;
}
.stButton > button,
.stFormSubmitButton > button {
    background: #0f766e;
    color: white;
    border: none;
    border-radius: 10px;
    font-weight: 600;
}
div[data-testid="stForm"] {
    background: white;
    border: 1px solid #dce8ed;
    border-radius: 14px;
    padding: 18px;
}
h1, h2, h3 {
    color: #163b50;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# NAVIGATION
# =========================================================

st.sidebar.title("🏨 StayFlow")
st.sidebar.caption(
    f"{user['full_name']} · {user['role']}"
)

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Dashboard",
        "Owner Management",
        "Room Management",
        "Booking Management",
        "Payments",
        "Revenue Management",
        "Employee Management",
        "Settings",
    ]
)

if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.logged_user = None
    st.rerun()


# =========================================================
# DASHBOARD
# =========================================================

if page == "Dashboard":
    st.title("Hotel Dashboard")
    st.caption("Your hotel performance at a glance.")

    rooms = read_df("SELECT * FROM rooms")
    bookings = read_df("SELECT * FROM bookings")
    payments = read_df("SELECT * FROM payments")
    employees = read_df("SELECT * FROM employees")

    available = (
        int((rooms["status"] == "Available").sum())
        if not rooms.empty else 0
    )
    revenue_total = (
        float(payments["amount"].sum())
        if not payments.empty else 0
    )
    active_bookings = (
        int(bookings["status"].isin(
            ["Confirmed", "Checked-in"]
        ).sum())
        if not bookings.empty else 0
    )

    a, b, c, d = st.columns(4)
    a.metric("Total Rooms", len(rooms))
    b.metric("Available Rooms", available)
    c.metric("Total Collection", money(revenue_total))
    d.metric("Active Bookings", active_bookings)

    st.subheader("Revenue Trend")

    if payments.empty:
        st.info("Revenue chart ke liye pehle payment add karein.")
    else:
        chart_data = payments.copy()
        chart_data["payment_date"] = pd.to_datetime(
            chart_data["payment_date"], errors="coerce"
        )
        chart_data = chart_data.dropna(subset=["payment_date"])

        if not chart_data.empty:
            daily = chart_data.groupby(
                chart_data["payment_date"].dt.date
            )["amount"].sum().reset_index()
            daily.columns = ["Date", "Collection"]
            daily["Date"] = pd.to_datetime(daily["Date"])

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=daily["Date"],
                y=daily["Collection"],
                mode="lines+markers",
                line=dict(color="#0f9d91", width=3, shape="spline"),
                fill="tozeroy",
                name="Collection"
            ))
            fig.update_layout(
                template="plotly_white",
                height=340,
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns(2)

    with left:
        st.subheader("Room Status")
        if rooms.empty:
            st.info("Room Management se rooms add karein.")
        else:
            status_data = rooms["status"].value_counts().reset_index()
            status_data.columns = ["Status", "Count"]
            fig = px.pie(
                status_data,
                names="Status",
                values="Count",
                hole=0.55,
                color_discrete_sequence=[
                    "#0f9d91", "#f59e0b", "#64748b", "#dc6b6b"
                ]
            )
            fig.update_layout(template="plotly_white", height=320)
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Employee Overview")
        if employees.empty:
            st.info("Abhi employee records nahi hain.")
        else:
            st.metric("Total Employees", len(employees))
            st.dataframe(
                employees[["name", "role", "shift", "status"]],
                use_container_width=True,
                hide_index=True
            )

    st.subheader("Recent Bookings")
    if bookings.empty:
        st.info("Abhi booking history empty hai.")
    else:
        recent = read_df("""
            SELECT
                b.id AS 'Booking ID',
                b.guest_name AS 'Guest',
                r.room_number AS 'Room',
                r.room_type AS 'Room Type',
                b.check_in AS 'Check-in',
                b.check_out AS 'Check-out',
                b.total_amount AS 'Total (₹)',
                b.status AS 'Status'
            FROM bookings b
            LEFT JOIN rooms r ON r.id = b.room_id
            ORDER BY b.id DESC
            LIMIT 10
        """)
        st.dataframe(recent, use_container_width=True, hide_index=True)


# =========================================================
# OWNER MANAGEMENT
# =========================================================

elif page == "Owner Management":
    st.title("Owner Management")

    df = read_df("SELECT * FROM owner WHERE id = 1")
    owner = df.iloc[0].to_dict() if not df.empty else {}

    with st.form("owner_form"):
        name = st.text_input("Owner Name", owner.get("name") or "")
        hotel = st.text_input(
            "Hotel Name", owner.get("hotel_name") or ""
        )
        phone = st.text_input("Phone", owner.get("phone") or "")
        email = st.text_input("Email", owner.get("email") or "")
        address = st.text_area("Address", owner.get("address") or "")
        save = st.form_submit_button(
            "Save / Update Owner", use_container_width=True
        )

    if save:
        execute("""
            INSERT INTO owner(id, name, phone, email, address, hotel_name)
            VALUES(1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                phone=excluded.phone,
                email=excluded.email,
                address=excluded.address,
                hotel_name=excluded.hotel_name
        """, (
            name.strip(), phone.strip(), email.strip(),
            address.strip(), hotel.strip()
        ))
        st.success("Owner details save ho gaye.")
        st.rerun()

    if owner:
        st.subheader("Saved Owner Details")
        st.write("**Owner:**", owner.get("name") or "-")
        st.write("**Hotel:**", owner.get("hotel_name") or "-")
        st.write("**Phone:**", owner.get("phone") or "-")
        st.write("**Email:**", owner.get("email") or "-")
        st.write("**Address:**", owner.get("address") or "-")


# =========================================================
# ROOM MANAGEMENT
# =========================================================

elif page == "Room Management":
    st.title("Room Management")

    with st.form("add_room_form", clear_on_submit=True):
        st.subheader("Add New Room")
        c1, c2 = st.columns(2)
        room_number = c1.text_input("Room Number")
        room_type = c2.selectbox(
            "Room Type",
            ["Standard", "Deluxe", "Suite", "Single", "Double", "Family"]
        )
        c3, c4 = st.columns(2)
        price = c3.number_input(
            "Price per Night (₹)", min_value=0.0, value=1500.0
        )
        status = c4.selectbox("Status", room_statuses())
        notes = st.text_input("Notes")
        add = st.form_submit_button("Add Room", use_container_width=True)

    if add:
        if not room_number.strip():
            st.error("Room number bharein.")
        else:
            try:
                execute("""
                    INSERT INTO rooms
                    (room_number, room_type, price, status, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    room_number.strip(), room_type,
                    price, status, notes.strip()
                ))
                st.success("Room add ho gaya.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Ye room number pehle se maujood hai.")

    st.divider()
    st.subheader("Update Existing Room")
    rooms = read_df("SELECT * FROM rooms ORDER BY room_number")

    if rooms.empty:
        st.info("Pehle ek room add karein.")
    else:
        room_labels = {
            f"{row['room_number']} — {row['room_type']}": int(row["id"])
            for _, row in rooms.iterrows()
        }
        label = st.selectbox("Select Room", list(room_labels.keys()))
        room_id = room_labels[label]
        room = rooms[rooms["id"] == room_id].iloc[0]

        room_types = [
            "Standard", "Deluxe", "Suite", "Single", "Double", "Family"
        ]
        current_type = (
            room["room_type"]
            if room["room_type"] in room_types else "Standard"
        )
        current_status = (
            room["status"]
            if room["status"] in room_statuses() else "Available"
        )

        with st.form("update_room_form"):
            new_number = st.text_input(
                "Room Number", str(room["room_number"])
            )
            new_type = st.selectbox(
                "Room Type", room_types,
                index=room_types.index(current_type)
            )
            new_price = st.number_input(
                "Price per Night (₹)",
                min_value=0.0,
                value=float(room["price"] or 0)
            )
            new_status = st.selectbox(
                "Status", room_statuses(),
                index=room_statuses().index(current_status)
            )
            new_notes = st.text_input(
                "Notes", str(room["notes"] or "")
            )
            update = st.form_submit_button("Update Room")

        if update:
            try:
                execute("""
                    UPDATE rooms
                    SET room_number=?, room_type=?, price=?, status=?, notes=?
                    WHERE id=?
                """, (
                    new_number.strip(), new_type, new_price,
                    new_status, new_notes.strip(), room_id
                ))
                st.success("Room update ho gaya.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Ye room number kisi aur room ko diya gaya hai.")

    st.subheader("All Rooms")
    rooms = read_df("""
        SELECT room_number AS 'Room Number',
               room_type AS 'Room Type',
               price AS 'Price (₹)',
               status AS 'Status',
               notes AS 'Notes'
        FROM rooms ORDER BY room_number
    """)
    st.dataframe(rooms, use_container_width=True, hide_index=True)


# =========================================================
# BOOKING MANAGEMENT
# =========================================================

elif page == "Booking Management":
    st.title("Booking Management")
    rooms = read_df("SELECT * FROM rooms ORDER BY room_number")

    if rooms.empty:
        st.warning("Booking se pehle Room Management mein room add karein.")
    else:
        available = rooms[rooms["status"] == "Available"]

        st.subheader("Create Booking")
        if available.empty:
            st.warning("Koi available room nahi hai.")
        else:
            room_labels = {
                f"{r['room_number']} · {r['room_type']} · {money(r['price'])}/night":
                int(r["id"])
                for _, r in available.iterrows()
            }

            with st.form("booking_form", clear_on_submit=True):
                guest = st.text_input("Guest Name")
                phone = st.text_input("Phone")
                room_label = st.selectbox(
                    "Available Room", list(room_labels.keys())
                )
                c1, c2 = st.columns(2)
                check_in = c1.date_input("Check-in", date.today())
                check_out = c2.date_input(
                    "Check-out", date.today() + timedelta(days=1)
                )
                guests = st.number_input(
                    "Number of Guests", 1, 20, 1
                )
                status = st.selectbox(
                    "Booking Status", booking_statuses()
                )
                notes = st.text_area("Notes")
                create = st.form_submit_button(
                    "Create Booking", use_container_width=True
                )

            if create:
                room_id = room_labels[room_label]
                room_price = float(
                    rooms.loc[rooms["id"] == room_id, "price"].iloc[0]
                )

                if not guest.strip():
                    st.error("Guest name bharein.")
                elif check_out <= check_in:
                    st.error("Check-out date check-in ke baad honi chahiye.")
                else:
                    overlap = read_df("""
                        SELECT COUNT(*) AS total
                        FROM bookings
                        WHERE room_id = ?
                          AND status IN ('Confirmed', 'Checked-in')
                          AND check_in < ?
                          AND check_out > ?
                    """, (
                        room_id, check_out.isoformat(),
                        check_in.isoformat()
                    )).iloc[0]["total"]

                    if overlap:
                        st.error("Is date range mein room pehle se booked hai.")
                    else:
                        nights = (check_out - check_in).days
                        execute("""
                            INSERT INTO bookings
                            (guest_name, phone, room_id, check_in, check_out,
                             guests, total_amount, status, notes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            guest.strip(), phone.strip(), room_id,
                            check_in.isoformat(), check_out.isoformat(),
                            int(guests), room_price * nights,
                            status, notes.strip()
                        ))
                        st.success("Booking create ho gayi.")
                        st.rerun()

    st.divider()
    st.subheader("Update Booking")

    booking_df = read_df("""
        SELECT b.*, r.room_number
        FROM bookings b
        LEFT JOIN rooms r ON r.id = b.room_id
        ORDER BY b.id DESC
    """)

    if booking_df.empty:
        st.info("Booking history empty hai.")
    else:
        booking_labels = {
            f"#{r['id']} · {r['guest_name']} · Room {r['room_number']} · {r['status']}":
            int(r["id"])
            for _, r in booking_df.iterrows()
        }
        selected_label = st.selectbox(
            "Select Booking", list(booking_labels.keys())
        )
        booking_id = booking_labels[selected_label]
        booking = booking_df[booking_df["id"] == booking_id].iloc[0]

        with st.form("update_booking_form"):
            guest = st.text_input(
                "Guest Name", str(booking["guest_name"] or "")
            )
            phone = st.text_input(
                "Phone", str(booking["phone"] or "")
            )
            check_in = st.date_input(
                "Check-in",
                value=pd.to_datetime(booking["check_in"]).date()
            )
            check_out = st.date_input(
                "Check-out",
                value=pd.to_datetime(booking["check_out"]).date()
            )
            status_options = booking_statuses()
            old_status = booking["status"]
            status_index = (
                status_options.index(old_status)
                if old_status in status_options else 0
            )
            status = st.selectbox(
                "Status", status_options, index=status_index
            )
            notes = st.text_area(
                "Notes", str(booking["notes"] or "")
            )
            update_booking = st.form_submit_button("Update Booking")

        if update_booking:
            if not guest.strip():
                st.error("Guest name required hai.")
            elif check_out <= check_in:
                st.error("Check-out date valid honi chahiye.")
            else:
                execute("""
                    UPDATE bookings
                    SET guest_name=?, phone=?, check_in=?, check_out=?,
                        status=?, notes=?
                    WHERE id=?
                """, (
                    guest.strip(), phone.strip(),
                    check_in.isoformat(), check_out.isoformat(),
                    status, notes.strip(), booking_id
                ))
                st.success("Booking update ho gayi.")
                st.rerun()

        st.subheader("Booking History")
        st.dataframe(
            booking_df[[
                "id", "guest_name", "phone", "room_number",
                "check_in", "check_out", "total_amount", "status"
            ]],
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# PAYMENTS
# =========================================================

elif page == "Payments":
    st.title("Payments")

    bookings = read_df("""
        SELECT id, guest_name
        FROM bookings
        ORDER BY id DESC
    """)

    with st.form("payment_form", clear_on_submit=True):
        customer = st.text_input("Customer Name")

        booking_labels = {"No linked booking": None}
        for _, row in bookings.iterrows():
            booking_labels[
                f"Booking #{row['id']} — {row['guest_name']}"
            ] = int(row["id"])

        selected = st.selectbox(
            "Link Booking (optional)", list(booking_labels.keys())
        )
        amount = st.number_input(
            "Payment Amount (₹)", min_value=0.0, value=0.0
        )
        method = st.selectbox(
            "Payment Method",
            ["Cash", "UPI", "Credit Card", "Debit Card", "Bank Transfer"]
        )
        payment_date = st.date_input("Payment Date", date.today())
        note = st.text_input("Notes")
        save_payment = st.form_submit_button(
            "Save Payment", use_container_width=True
        )

    if save_payment:
        if not customer.strip():
            st.error("Customer name bharein.")
        elif amount <= 0:
            st.error("Payment amount zero se zyada hona chahiye.")
        else:
            execute("""
                INSERT INTO payments
                (customer_name, booking_id, amount, method,
                 payment_date, received_by, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                customer.strip(), booking_labels[selected], amount,
                method, payment_date.isoformat(),
                user["full_name"], note.strip()
            ))
            st.success("Payment save ho gaya.")
            st.rerun()

    st.subheader("Payment Records")
    payments = read_df("""
        SELECT
            p.id AS 'Payment ID',
            p.customer_name AS 'Customer',
            p.amount AS 'Amount (₹)',
            p.method AS 'Method',
            p.payment_date AS 'Date',
            p.booking_id AS 'Booking ID',
            p.received_by AS 'Received By',
            p.note AS 'Notes'
        FROM payments p
        ORDER BY p.payment_date DESC, p.id DESC
    """)

    if payments.empty:
        st.info("Abhi payment records nahi hain.")
    else:
        st.dataframe(payments, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Payments CSV",
            payments.to_csv(index=False).encode("utf-8"),
            "stayflow_payments.csv",
            "text/csv"
        )


# =========================================================
# REVENUE MANAGEMENT
# =========================================================

elif page == "Revenue Management":
    st.title("Revenue Management")

    payments = read_df("SELECT * FROM payments ORDER BY payment_date DESC, id DESC")
    total = float(payments["amount"].sum()) if not payments.empty else 0.0
    today_total = 0.0
    month_total = 0.0

    if not payments.empty:
        dates = pd.to_datetime(payments["payment_date"], errors="coerce")
        today_total = float(
            payments.loc[dates.dt.date == date.today(), "amount"].sum()
        )
        month_total = float(
            payments.loc[
                (dates.dt.year == date.today().year) &
                (dates.dt.month == date.today().month),
                "amount"
            ].sum()
        )

    a, b, c = st.columns(3)
    a.metric("Total Collection", money(total))
    b.metric("Today's Collection", money(today_total))
    c.metric("This Month", money(month_total))

    st.subheader("Revenue Details")

    revenue = read_df("""
        SELECT
            p.id AS 'Payment ID',
            p.customer_name AS 'Customer',
            p.amount AS 'Amount (₹)',
            p.method AS 'Payment Method',
            p.payment_date AS 'Date',
            p.booking_id AS 'Booking ID',
            p.received_by AS 'Received By',
            p.note AS 'Notes'
        FROM payments p
        ORDER BY p.payment_date DESC, p.id DESC
    """)

    if revenue.empty:
        st.info("Revenue report ke liye pehle Payments mein record add karein.")
    else:
        st.dataframe(revenue, use_container_width=True, hide_index=True)

        daily = read_df("""
            SELECT payment_date, SUM(amount) AS collection
            FROM payments
            GROUP BY payment_date
            ORDER BY payment_date
        """)

        fig = px.bar(
            daily,
            x="payment_date",
            y="collection",
            labels={
                "payment_date": "Date",
                "collection": "Collection (₹)"
            },
            title="Daily Revenue"
        )
        fig.update_layout(template="plotly_white", height=350)
        st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "Download Revenue CSV",
            revenue.to_csv(index=False).encode("utf-8"),
            "stayflow_revenue.csv",
            "text/csv"
        )


# =========================================================
# EMPLOYEE MANAGEMENT
# =========================================================

elif page == "Employee Management":
    st.title("Employee Management")

    roles = [
        "Receptionist", "Housekeeping", "Manager", "Security",
        "Cook", "Maintenance", "Accountant", "Other"
    ]
    shifts = ["Morning", "Evening", "Night", "General", "Rotational"]
    employee_statuses = ["Active", "On Leave", "Inactive"]

    with st.form("employee_form", clear_on_submit=True):
        st.subheader("Add Employee")
        name = st.text_input("Employee Name")
        role = st.selectbox("Job Role", roles)
        phone = st.text_input("Phone")
        salary = st.number_input("Monthly Salary (₹)", min_value=0.0)
        shift = st.selectbox("Shift", shifts)
        status = st.selectbox("Status", employee_statuses)
        add_employee = st.form_submit_button("Add Employee")

    if add_employee:
        if not name.strip():
            st.error("Employee name bharein.")
        else:
            execute("""
                INSERT INTO employees
                (name, role, phone, salary, shift, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name.strip(), role, phone.strip(), salary, shift, status
            ))
            st.success("Employee add ho gaya.")
            st.rerun()

    st.subheader("Employee List / Update")
    employees = read_df("SELECT * FROM employees ORDER BY name")

    if employees.empty:
        st.info("Abhi employee records nahi hain.")
    else:
        employee_labels = {
            f"#{r['id']} — {r['name']} ({r['role']})": int(r["id"])
            for _, r in employees.iterrows()
        }
        selected_label = st.selectbox(
            "Select Employee", list(employee_labels.keys())
        )
        employee_id = employee_labels[selected_label]
        employee = employees[employees["id"] == employee_id].iloc[0]

        role_index = roles.index(employee["role"]) if employee["role"] in roles else 0
        shift_index = shifts.index(employee["shift"]) if employee["shift"] in shifts else 0
        status_index = employee_statuses.index(employee["status"]) if employee["status"] in employee_statuses else 0

        with st.form("update_employee_form"):
            new_name = st.text_input("Name", str(employee["name"] or ""))
            new_role = st.selectbox("Role", roles, index=role_index)
            new_phone = st.text_input("Phone", str(employee["phone"] or ""))
            new_salary = st.number_input(
                "Salary", min_value=0.0,
                value=float(employee["salary"] or 0)
            )
            new_shift = st.selectbox("Shift", shifts, index=shift_index)
            new_status = st.selectbox(
                "Status", employee_statuses, index=status_index
            )
            update_employee = st.form_submit_button("Update Employee")

        if update_employee:
            execute("""
                UPDATE employees
                SET name=?, role=?, phone=?, salary=?, shift=?, status=?
                WHERE id=?
            """, (
                new_name.strip(), new_role, new_phone.strip(),
                new_salary, new_shift, new_status, employee_id
            ))
            st.success("Employee update ho gaya.")
            st.rerun()

        st.dataframe(
            employees[["name", "role", "phone", "salary", "shift", "status"]],
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# SETTINGS AND STAFF LOGIN
# =========================================================

elif page == "Settings":
    st.title("Settings")
    st.subheader("Change Password")

    with st.form("password_form"):
        old_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input(
            "Confirm New Password", type="password"
        )
        change_password = st.form_submit_button("Update Password")

    if change_password:
        valid = read_df("""
            SELECT id FROM users
            WHERE id=? AND password_hash=?
        """, (int(user["id"]), password_hash(old_password)))

        if valid.empty:
            st.error("Current password galat hai.")
        elif len(new_password) < 8:
            st.error("Password minimum 8 characters ka hona chahiye.")
        elif new_password != confirm_password:
            st.error("New passwords match nahi karte.")
        else:
            execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (password_hash(new_password), int(user["id"]))
            )
            st.success("Password update ho gaya.")

    if user["role"] == "Admin":
        st.divider()
        st.subheader("Create Staff Account")

        with st.form("staff_form", clear_on_submit=True):
            staff_name = st.text_input("Staff Full Name")
            staff_username = st.text_input("Username")
            staff_password = st.text_input(
                "Temporary Password", type="password"
            )
            staff_role = st.selectbox(
                "Role", ["Staff", "Manager", "Receptionist", "Accountant"]
            )
            create_staff = st.form_submit_button("Create Account")

        if create_staff:
            if not staff_name.strip() or not staff_username.strip():
                st.error("Name aur username bharein.")
            elif len(staff_password) < 8:
                st.error("Password minimum 8 characters ka rakhein.")
            else:
                try:
                    execute("""
                        INSERT INTO users
                        (username, password_hash, full_name, role, active)
                        VALUES (?, ?, ?, ?, 1)
                    """, (
                        staff_username.strip(),
                        password_hash(staff_password),
                        staff_name.strip(),
                        staff_role
                    ))
                    st.success("Staff account create ho gaya.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Ye username pehle se exist karta hai.")

        st.subheader("Manage Staff Accounts")
        staff = read_df("""
            SELECT id, username, full_name, role, active
            FROM users ORDER BY id
        """)

        st.dataframe(staff, use_container_width=True, hide_index=True)

        if not staff.empty:
            staff_labels = {
                f"{r['username']} — {r['full_name']}": int(r["id"])
                for _, r in staff.iterrows()
            }
            selected_staff_label = st.selectbox(
                "Select Staff Account", list(staff_labels.keys())
            )
            staff_id = staff_labels[selected_staff_label]
            staff_row = staff[staff["id"] == staff_id].iloc[0]

            if staff_row["username"] != user["username"]:
                active_options = ["Active", "Inactive"]
                active_index = 0 if int(staff_row["active"]) else 1
                account_status = st.selectbox(
                    "Account Status", active_options, index=active_index
                )

                if st.button("Save Staff Status"):
                    execute(
                        "UPDATE users SET active=? WHERE id=?",
                        (
                            1 if account_status == "Active" else 0,
                            staff_id
                        )
                    )
                    st.success("Staff status update ho gaya.")
                    st.rerun()

    st.caption(
        "Security tip: Default password ko login ke baad change karein."
    )
