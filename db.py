import sqlite3

class DB:

    """
        The database contains:
        - id
        - email
        - psw
        - course
        of the user that log into the register
        and a table of users to send automatic messages to
    """
    def __init__(self, db_name="database.db"):
        self.db_name = db_name
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_name)
        self.cur = self.conn.cursor()

        self.cur.execute("CREATE TABLE IF NOT EXISTS users_login(id, email, psw, course, section)")     # section contains year and section ->1A, 2A...
        self.cur.execute("CREATE TABLE IF NOT EXISTS users_newsletter(id, course, section, can_send_news)")
    
    def query(self, query, values=[]):
        self.res = self.cur.execute(query, values)

        if "INSERT" in query.upper() or "UPDATE" in query.upper():
            self.conn.commit()

        return self.res    # result of the query

    def close(self):
        self.conn.close()

    def fetch(self):
        return self.res.fetchone()
    
    def fetchall(self):
        return self.res.fetchall()
