from datetime import date, timedelta, datetime
import schedule
from threading import Thread
import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from register import Register
from time import sleep
from db import DB
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from requests import post

LOG_FILE = "log.txt"
NEWS_LOG_FILE = "log_newsletter.txt"
EXCEPTION_LOG_FILE = "exceptions.txt"

class Bot:
    bot = None
    token = ""
    users = []
    # user = ""
    # password = ""
    day = {}
    oldDB = {}
    register = None
    db = None
    ids = dict()
    __key = b""      # used to crypt and decrypt passwords
    

    def __init__(self):
        # create bot
        self.token = os.environ['TOKEN']
        self.exit = False

        self.register = Register("", "")
        self.bot = telebot.TeleBot(self.token)

        self.__key = os.environ["key"].encode()

        self.db = DB()
        

        # scheduling newsletter and updates of lessons
        schedule.every(30).minutes.do(self.updateDB)
        schedule.every().day.at("07:00").do(self.newsletter)
        messages_thread = Thread(target=self.handle_messages)
        messages_thread.start()
        Thread(target=self.check_if_bot_down, args=(messages_thread,)).start()

        t_courses = self.db.query("SELECT course FROM users_login;").fetchall()
        t_years = self.db.query("SELECT year FROM users_login;").fetchall()
        t_sections = self.db.query("SELECT section FROM users_login;").fetchall()

        courses = []
        for c in t_courses:
            courses.append(c[0])

        years = []
        for y in t_years:
            years.append(y[0])

        sections = []
        for l in t_sections:
            sections.append(l[0])

        if len(courses) == 0:
            courses = []
            years = []
            sections = []
            return
        
        # creating courses' keys
        for i in range(len(courses)):
            self.create_course_key(courses[i], years[i], sections[i])

        self.updateDB()

    def check_if_bot_down(self, thread : Thread):
        while not self.exit:
            sleep(5)
            if not thread.is_alive() and not self.exit:
                try:
                    server = os.environ["notify_server"]
                    page = os.environ["page"]
                    post(f"http://{server}/{page}", "Bot is down restarting it")
                except Exception as e:
                    with open(EXCEPTION_LOG_FILE, "a") as log:
                        log.write( f"# ---- {str(datetime.today())[:-7]} ---- #\n" )
                        log.write("Bot down. Cannot send notification: \n")
                        log.write( str(e.with_traceback(None)) + "\n")

                thread = Thread(target=self.handle_messages)
                thread.start()

    def start(self):
        while True:
            schedule.run_pending()
            sleep(1)


    def save_user_info(self, user_id : int):

        email   = self.ids[user_id]["email"]
        psw     = self.ids[user_id]["psw"]
        course  = self.ids[user_id]["course"]
        section = self.ids[user_id]["section"]
        year    = self.ids[user_id]["year"]

        login_credentials = (not email == "")

        if login_credentials:
            # if user does not already exists in the db then insert it
            if not self.user_already_exists_in('users_login', user_id):
                self.db.query('INSERT INTO users_login VALUES (?, ?, ?, ?, ?, ?);', (user_id, email, psw, course, year, section))

            self.create_course_key(course, year, section)
            
            #*  update db of the new course
            self.register.set_credential(self.ids[user_id]["email"], self.decrypt_message(self.__key, self.ids[user_id]["psw"]))
            self.day[course][year][section] = self.register.requestGeop(date.today(), date.today()+timedelta(days=1))
            self.oldDB[course][year][section] = self.register.requestGeop()


        self.db.query('INSERT INTO users_newsletter VALUES (?, ?, ?, ?, ?);', [user_id, course, year, section, False])
        with open(LOG_FILE, "a") as log:
            log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] User registered\n")
        
        self.bot.send_message(user_id, 'Account configurato con successo!\nPer ricevere una notifica ogni giorno alle 7 esegui il comando /news')

        # remove user's key from dictionary
        self.ids.pop(user_id, None)

        return

    def get_registered_courses(self):
        lines = []
        res = self.db.query("SELECT course, year, section FROM users_login ORDER BY course").fetchall()
        for _class in res:
            lines.append(f"{_class[0]}, {_class[1]}° anno - sez. {_class[2]}") # format: course, year - section
        return lines

    def register_user(self, message : telebot.types.Message):
        with open(LOG_FILE, "a") as log:
            log.write(f"[{str(datetime.today())[:-7]}] [{message.from_user.id}] Choosing course...\n")
        
        self.ids[message.from_user.id] = {
            "course": "",
            "section": "",
            "year": "",
            "email": "",
            "psw": "",
        }
        self.bot.reply_to(message, "Benvenuto! Per configurare il tuo account, scegli il tuo corso:", reply_markup=self.create_courses_keyboard("course--"))


    def handle_messages(self):
        
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_handler(call):

            if call.data == "1" or  call.data == "2":

                if self.user_already_exists_in('users_newsletter', call.message.chat.id):
                    self.bot.send_message(call.message.chat.id, 'Account già configurato. In caso di problemi contattare lo sviluppatore (/credits)')
                    return

                user_id = call.message.chat.id

                # user has already configured his account
                if self.user_already_exists_in('users_newsletter', user_id):
                    self.bot.send_message(user_id, 'Account già configurato. In caso di problemi contattare lo sviluppatore (/credits)')
                    return

                self.ids[user_id]["year"] = call.data 

                with open(LOG_FILE, "a") as log:
                    log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] Course: {self.ids[user_id]['course']}, {self.ids[user_id]['year']} - {self.ids[user_id]['section']}\n")

                if self.there_is_a_user_configured_for(self.ids[user_id]["course"], self.ids[user_id]['year'], self.ids[user_id]["section"]):
                    self.save_user_info(user_id)
                    return

                self.bot.send_message(user_id, 'Nessun account configurato per questo corso, fornisci le seguenti informazioni:\n\nEmail:')
                self.bot.register_next_step_handler(call.message, self.get_email)

            elif "viewcourse--" in call.data:
                user_id = call.message.chat.id
                course = call.data.split("--")[1].split(", ")[0]
                year = call.data.split(", ")[1].split("°")[0]
                section = call.data.split(" - ")[1].strip()[-1]

                user_course, user_year, user_section = self.db.query("SELECT course, year, section FROM users_newsletter WHERE id=?", [user_id]).fetchone()

                with open(LOG_FILE, "a") as log:
                    log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /show ({course}, {year} - {section}), ({user_course}, {user_year} - {user_section})\n")

                week_lessons = self.oldDB[course][year][section]
                if week_lessons == []:
                    self.bot.send_message(user_id, "Nessuna lezione programmata per i prossimi 7 giorni")
                    return
                
                self.bot_print(week_lessons, user_id)

            elif "section--" in call.data:
                
                user_id = call.message.chat.id
                if self.user_already_exists_in('users_newsletter', user_id):
                    self.bot.send_message(call.message.chat.id, 'Account già configurato. In caso di problemi contattare lo sviluppatore (/credits)')
                    return
                
                sec = call.data.split("section--")[1].strip()
                self.ids[user_id]["section"] = sec

                with open(LOG_FILE, "a") as log:
                    log.write(f"[{str(datetime.today())[:-7]}] [{call.message.chat.id}] Choosing year...\n")

                self.bot.send_message(call.message.chat.id, "Seleziona l'anno", reply_markup=self.create_year_keyboard())

            elif "course--" in call.data:
                user_id = call.message.chat.id
                if self.user_already_exists_in('users_newsletter', user_id):
                    self.bot.send_message(call.message.chat.id, 'Account già configurato. In caso di problemi contattare lo sviluppatore (/credits)')
                    return

                course = call.data.split("course--")[1].strip()
                self.ids[user_id]["course"] = course

                with open(LOG_FILE, "a") as log:
                    log.write(f"[{str(datetime.today())[:-7]}] [{call.message.chat.id}] Choosing section...\n")

                self.bot.send_message(call.message.chat.id, "Seleziona la sezione", reply_markup=self.create_sections_keyboard("section--"))

            return

        @self.bot.message_handler(commands=['help'])
        def handle_help(message):
            help_msg = \
            "/start configura il tuo account\n" + \
            "/help Visualizza questa guida\n" + \
            "/day  Lezione più recente\n" + \
            "/week  Lezione da oggi + 7gg\n" + \
            "/news Notifica alle 7 sulla lezione del giorno\n" + \
            "/unews Non verrà più ricevuto un messaggio sulla lezione del giorno\n" + \
            "/credits Contatti, codice sorgente e info sviluppatori"

            self.bot.reply_to(message, help_msg)


        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{message.from_user.id}] Started the bot\n")

            # user has already configured his account
            if self.user_already_exists_in('users_newsletter', message.from_user.id):
                self.bot.send_message(message.from_user.id, 'Account già configurato. In caso di problemi contattare lo sviluppatore (/credits)')
                return
            
            Thread(target=self.register_user, args=(message,), name="UserRegistration").start()


        @self.bot.message_handler(commands=['day'])
        def handle_day(message : telebot.types.Message):
            user_id = message.from_user.id

            if not self.is_user_registered(user_id):
                self.send_configuration_message(user_id)
                return

            user_course, user_year, user_section = self.db.query("SELECT course, year, section FROM users_newsletter WHERE id=?", [user_id]).fetchone()

            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /day, {user_course}, {user_year}° anno - {user_section}\n")

            today_lessons = self.day[user_course][user_year][user_section]
            if today_lessons == []:
                self.bot.send_message(user_id, "Nessuna lezione programmata per oggi")
                return

            self.bot_print(today_lessons, user_id)

        @self.bot.message_handler(commands=['week'])
        def handle_week(message):
            user_id = message.from_user.id

            if not self.is_user_registered(user_id):
                self.send_configuration_message(user_id)
                return

            user_course, user_year, user_section = self.db.query("SELECT course, year, section FROM users_newsletter WHERE id=?", [user_id]).fetchone()

            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /week, {user_course}, {user_year}° anno - {user_section}\n")

            week_lessons = self.oldDB[user_course][user_year][user_section]
            if week_lessons == []:
                self.bot.send_message(user_id, "Nessuna lezione programmata per i prossimi 7 giorni")
                return

            self.bot_print(week_lessons, user_id)

        @self.bot.message_handler(commands=['news'])
        def echo_news(message):
            user_id = message.from_user.id

            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /news\n")

            if not self.is_user_registered(user_id):
                self.send_configuration_message(user_id)
                return

            # no need to check if the user is not present, because it is automatically inserted into the db during the config stage
            self.db.query("UPDATE users_newsletter SET can_send_news = 1 WHERE id = ?;", [user_id])
            self.bot.send_message(user_id, "Riceverai una notifica sulla lezione del giorno ogni giorno alle 7:00")

        @self.bot.message_handler(commands=['unews'])
        def unews(message):
            user_id = message.from_user.id

            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /unews\n")

            if not self.is_user_registered(user_id):
                self.send_configuration_message(user_id)
                return

            self.db.query("UPDATE users_newsletter SET can_send_news = 0 WHERE id = ?;", [user_id])
            self.bot.send_message(user_id, "Non riceverai più una notifica ogni giorno alle 7:00")

        @self.bot.message_handler(commands=['credits'])
        def show_credits(message):
            user_id = message.from_user.id

            user_course, user_year, user_section = self.db.query("SELECT course, year, section FROM users_newsletter WHERE id=?", [user_id]).fetchone()
            with open(LOG_FILE, "a") as log:
                log.write(f"[{str(datetime.today())[:-7]}] [{user_id}] /credits, {user_course}, {user_year}° anno - {user_section}\n")

            credits_msg = f"\
            Creato e mantenuto da {os.environ['main_developer']}\
            \n\nPer segnalazioni di bug o suggerimenti scrivere una mail a {os.environ['developer_email']} o un messaggio su Google Chat.\
            \n\nIl codice sorgente è disponibile qui: https://github.com/Dadezana/bot-geop\
            "

            self.bot.send_message(user_id, credits_msg, parse_mode='Markdown')

        @self.bot.message_handler(commands=['show'])
        def other_class_lesson(message : telebot.types.Message):
            self.bot.send_message(message.chat.id, "Di quale corso vuoi vedere l'orario?", reply_markup=self.create_courses_keyboard("viewcourse--", course_must_exist=True))

        try:
            self.bot.polling()
        except Exception as e:
            print(e, end="")
            print(", restarting the function")

            with open(EXCEPTION_LOG_FILE, "a") as log:
                log.write( f"# ---- {str(datetime.today())[:-7]} ---- #\n" )
                log.write( str(e.with_traceback(None)) + "\n")

            sleep(2)
            self.handle_messages()
            return


    def newsletter(self):

        t_courses = self.db.query("SELECT course FROM users_login;").fetchall()
        t_years = self.db.query("SELECT year FROM users_login;").fetchall()
        t_sections = self.db.query("SELECT section FROM users_login;").fetchall()

        courses = []
        for c in t_courses:
            courses.append(c[0])

        years = []
        for y in t_years:
            years.append(y[0])

        sections = []
        for l in t_sections:
            sections.append(l[0])

        f = open(NEWS_LOG_FILE, "a")

        # per ogni corso, primo e secondo anno, tutte le sezioni
        for i in range(len(courses)):

            course = courses[i]
            year = years[i]
            section = sections[i]

            t_user_id = self.db.query("SELECT id FROM users_newsletter WHERE course=? AND can_send_news=1 AND year=? AND section=?;", [course, year, section]).fetchall()
            users_id = []
            for c in t_user_id:
                users_id.append(c[0])

            for user_id in users_id:
                self.bot_print(self.day[course][year][section], int(user_id))

            if self.day[course][year][section]:
                f.write(f"[ {date.today()} ] Sent news to {course} course\n")

        f.close()
        self.db.close()
        return

    # Funzione per verificare se le informazioni dell'utente sono già state fornite
    def user_already_exists_in(self, table, user_id):
        res = self.db.query(f"SELECT * FROM {table} WHERE id=?;", [user_id,]).fetchone()
        return res != None


    def updateDB(self, just_today=False):

        for course in self.oldDB.keys():
            for year in self.oldDB[course].keys():
                for section in self.oldDB[course][year].keys():

                    res = self.db.query("SELECT email, psw FROM users_login WHERE course=? and year=? AND section=?", [course, year, section]).fetchone()
                    if res == None: continue

                    email, psw = res[0], res[1]
                    psw = self.decrypt_message(self.__key, psw)
                    self.register.set_credential(email, psw)

                    if not just_today:
                        newDB = self.register.requestGeop()
                        if "list" in str(type(newDB)):              # avoid writing an integer and erase the oldDB
                            self.oldDB[course][year][section] = newDB

                    res = self.register.requestGeop(date.today(), date.today()+timedelta(days=1))
                    if res == self.register.ERROR or res == self.register.CONNECTION_ERROR:
                        return
                    
                    if res == self.register.WRONG_PSW:                  # log written here instead of register.py, so we can have info about the course
                        with open(self.EXCEPTION_LOG_FILE, "a") as log:
                            log.write( f"# ---- {str(datetime.today())[:-7]} ---- #\n" )
                            log.write(f"Wrong password for course {course}")

                    self.day[course][year][section] = res

    # id: user to send the message to
    def bot_print(self, lessons, id):
        try:
            lessons.sort(
                key=lambda l: (
                    int(l["day"][0]),
                    int(l["day"][1]),
                    int(l["day"][2]),
                    int(l["start"].split(":")[0]),
                    int(l["start"].split(":")[1]),
                )
            )
        except AttributeError as ae:
            print(ae)
            return

        for l in lessons:
            canPrintDay = True
            weekday, day, month, start, end = l["weekday"], l["day"], l["month"], l["start"], l["end"]
            teacher, subject, room = l["teacher"], l["subject"], l["room"]
            type_ = l["type"]
            previous_lesson_i = lessons.index(l) - 1

            if previous_lesson_i >= 0:
                previous_lesson = lessons[previous_lesson_i]
                if previous_lesson["day"] == day:
                    canPrintDay = False


            data = "-" * 26
            if canPrintDay:
                data = f"\n*{weekday[:3]} {day[2]} {month} {day[0]}* "

            orario = (f"-- *{start}-{end}*")
            docente = f"\n🧑‍🏫 | {teacher}"
            materia = f"\n📓 | {subject}" if not type_ == "esame" else  f"\n⚠️ | {subject}"
            stanza = f"\n🏢 | {room}"
            msg = data + orario + docente + materia + stanza

            try:
                self.bot.send_message(id, msg, parse_mode='Markdown')

            except telebot.apihelper.ApiTelegramException as e:

                with open(self.EXCEPTION_LOG_FILE, "a") as f:
                    f.write( f"# ---- {str(datetime.today())[:-7]} ---- #\n" )
                    f.write(str(e.with_traceback(None)) + f" ({id})\n")
                    f.flush()

        return

    def get_email(self, message : telebot.types.Message):
        self.ids[message.from_user.id]["email"] = message.text
        
        self.bot.send_message(message.chat.id, 'Password:')
        self.bot.register_next_step_handler(message, self.get_password)

    def get_password(self, message : telebot.types.Message):
        user_id = message.from_user.id
        Thread(target=self.delete_msg, args=[message]).start()

        self.register.set_credential(self.ids[user_id]["email"], message.text)
        res = self.register.requestGeop()

        if (res == self.register.CONNECTION_ERROR) or (res == self.register.ERROR):
            self.bot.send_message(user_id, "Errore nella configurazione nell'account. Per riprovare esegui il comando /start\n In caso di errore persistente contattta gli admin (/credits)")
            with open(LOG_FILE, "a") as f:
                f.write(f"[{str(datetime.today())[:-7]}] [{user_id}] Errore nella configurazione\n")
            return

        if(res == self.register.WRONG_PSW):
            self.bot.send_message(message.chat.id, "Account non configurato: credenziali errate.\nPer riprovare esegui il comando /start")
            with open(LOG_FILE, "a") as f:
                f.write(f"[{str(datetime.today())[:-7]}] [{message.chat.id}] Credenziali errate\n")
            return
        
        
        self.ids[message.from_user.id]["psw"] = self.encrypt_message(self.__key, message.text)
        
        self.save_user_info(message.from_user.id)

    def create_courses_keyboard(self, pre_text="", course_must_exist = False): # text before default callback data

        keyboard = InlineKeyboardMarkup(row_width=2)

        if course_must_exist:                       # for /show command
            courses = self.get_registered_courses()
            for course in courses:
                keyboard.add(
                    InlineKeyboardButton(f"{course}",  callback_data=f'{pre_text}{course}')
                )
            return keyboard
        
        else:
            courses = self.get_courses()            

        for i in range(0, len(courses), 2):   # i add 2 buttons in one call, otherwise every button is displayed in a single row
            try:
                keyboard.add(
                    InlineKeyboardButton(f'{courses[i]}', callback_data=f'{pre_text}{courses[i]}'),
                    InlineKeyboardButton(f'{courses[i+1]}', callback_data=f'{pre_text}{courses[i+1]}')
                )
            except IndexError as ie:
                keyboard.add(
                    InlineKeyboardButton(f'{courses[i]}', callback_data=f'{pre_text}{courses[i]}')
                )
        return keyboard

    def create_sections_keyboard(self, pre_text=""):
        keyboard = InlineKeyboardMarkup(row_width=2)

        sections = self.get_sections()
        try:
            for i in range(0, len(sections), 2):
                keyboard.add(
                    InlineKeyboardButton(f"{sections[i]}", callback_data=f"{pre_text}{sections[i]}"),
                    InlineKeyboardButton(f"{sections[i+1]}", callback_data=f"{pre_text}{sections[i+1]}")
                )
        except IndexError as ie:
                keyboard.add(
                    InlineKeyboardButton(f'{sections[i]}', callback_data=f'{pre_text}{sections[i]}')
                )
        return keyboard

    def create_year_keyboard(self, pre_text=""):
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
                InlineKeyboardButton("1° anno", callback_data=f"{pre_text}1"),
                InlineKeyboardButton("2° anno", callback_data=f"{pre_text}2")
            )
        return keyboard

    def is_user_registered(self, user_id):
        
        res = self.db.query("SELECT * FROM users_newsletter WHERE id=?", [user_id]).fetchone()
        return res != None

    def send_configuration_message(self, user_id):
        self.bot.send_message(user_id, "Configura il tuo account con il comando /start per usare il bot")
    
    def delete_msg(self, message):
        sleep(10)
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except Exception as e:
            with open(EXCEPTION_LOG_FILE, "a") as log:
                log.write( str(e) + f" ({message.chat.id})\n" )
                log.flush()

    def there_is_a_user_configured_for(self, course, year, section):
        
        res = self.db.query("SELECT * FROM users_login WHERE course=? and year=? and section=?;", [course, year, section]).fetchone()
    
        # if there isn't an account configured for that course, return False
        if res == None:
            return False

        return True
    
    # Funzione per verificare se le informazioni dell'utente sono già state fornite
    def user_already_exists_in(self, table, user_id):
        res = self.db.query(f"SELECT * FROM {table} WHERE id=?;", [user_id,]).fetchone()
        return res != None

    def get_courses(self):
        lines = []

        with open("courses.txt", "r") as file:
            lines = file.readlines()

            for i in range(len(lines)):
                lines[i] = lines[i].replace('\n', '')

        return lines

    def get_sections(self):
        lines = []

        with open("sections.txt", "r") as file:
            lines = file.readlines()

            for i in range(len(lines)):
                lines[i] = lines[i].replace('\n', '')

        return lines

    def encrypt_message(self, key, message):
        iv = get_random_bytes(AES.block_size)
        cipher = AES.new(key, AES.MODE_CFB, iv)
        ciphertext = cipher.encrypt(message.encode('utf-8'))
        return (iv + ciphertext)

    def decrypt_message(self, key, ciphertext):
        iv = ciphertext[:AES.block_size]
        cipher = AES.new(key, AES.MODE_CFB, iv)
        plaintext = cipher.decrypt(ciphertext[AES.block_size:]).decode('utf-8')
        return plaintext
    
    def create_course_key(self, course, year, section):
        try:
            temp = self.oldDB[course]
        except KeyError as ke:
            self.oldDB[course] = {}
            self.day[course] = {}

        try:
            temp = self.oldDB[course][year]
        except KeyError as ke:
            self.oldDB[course][year] = {}
            self.day[course][year] = {}

        try:
            temp = self.oldDB[course][year][section]
        except KeyError as ke:
            self.oldDB[course][year][section] = {}
            self.day[course][year][section] = {}