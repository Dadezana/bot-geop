import sqlite3

class DB:

    """
        The database contains:
        - id
        - email
        - psw
        - course
        - year
        - section
        of the user that logs into the register
        and a table of users to send automatic messages to
    """
    def __init__(self, db_name="database.db"):
        self.db_name = db_name
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_name)
        self.cur = self.conn.cursor()

        self.cur.execute("CREATE TABLE IF NOT EXISTS users_login(id, email, psw, course, year, section)")     # locations contains the name of the city
        self.cur.execute("CREATE TABLE IF NOT EXISTS users_newsletter(id, course, year, section, can_send_news)")
    
    def query(self, query, values=[]):
        self.connect()
        self.res = self.cur.execute(query, values)

        if "INSERT" in query.upper() or "UPDATE" in query.upper():
            self.conn.commit()

        # self.close()
        return self.res    # result of the query

    def close(self):
        self.conn.close()

    def fetch(self):
        return self.res.fetchone()
    
    def fetchall(self):
        return self.res.fetchall()
