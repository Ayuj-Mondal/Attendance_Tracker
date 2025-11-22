import sqlite3

# Function to create the database and tables
def create_database():
    # Connect to SQLite database (creates 'attendance_tracker.db' if it doesn't exist)
    conn = sqlite3.connect('attendance_tracker.db')
    cursor = conn.cursor()

    # Create Teacher table
    # Primary key is composite: (T_id, Sem, Subject)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Teacher (
            T_id TEXT NOT NULL,
            password TEXT NOT NULL,
            T_name TEXT NOT NULL,
            Depart_id TEXT NOT NULL,
            Sem TEXT NOT NULL,
            Subject TEXT NOT NULL,
            PRIMARY KEY (T_id, Depart_id, Sem, Subject)
        )
    ''')

    # Create Student table
    # Primary key: S_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Student (
            S_id TEXT PRIMARY KEY,
            S_name TEXT NOT NULL,
            password TEXT NOT NULL,
            Depart_id TEXT NOT NULL,
            Sem TEXT NOT NULL
        )
    ''')

    # Create Department table
    # Primary key is composite: (Depart_id, Sem, Subject)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Department (
            Depart_id TEXT NOT NULL,
            Depart_name TEXT NOT NULL,
            Sem TEXT NOT NULL,
            Subject TEXT NOT NULL,
            PRIMARY KEY (Depart_id, Sem, Subject)
        )
    ''')

    # Create Attendance table
    # Primary key is composite: (S_id, Date, Subject)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Attendance (
            S_id TEXT NOT NULL,
            T_id TEXT NOT NULL,
            Date TEXT NOT NULL,
            Subject TEXT NOT NULL,
            Status TEXT NOT NULL,
            reason TEXT,
            proof TEXT,
            action_taken TEXT,
            PRIMARY KEY (S_id, T_id, Date, Subject)
        )
    ''')

    # Add columns if they don't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE Attendance ADD COLUMN reason TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE Attendance ADD COLUMN proof TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE Attendance ADD COLUMN action_taken TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute('ALTER TABLE Attendance ADD COLUMN read_status INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass

    # Create Notifications table (for students)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            S_id TEXT NOT NULL,
            message TEXT NOT NULL,
            date TEXT NOT NULL,
            read_status INTEGER DEFAULT 0
        )
    ''')

    # Create TeacherNotifications table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TeacherNotifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            T_id TEXT NOT NULL,
            message TEXT NOT NULL,
            date TEXT NOT NULL,
            read_status INTEGER DEFAULT 0
        )
    ''')

    # Commit changes and close connection
    conn.commit()
    conn.close()
    print("Database and tables created successfully!")

# Run the function to create the database
if __name__ == "__main__":
    create_database()