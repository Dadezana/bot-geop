from requests import Session, ConnectionError
from datetime import date, timedelta
from termcolor import colored
import calendar
from utils import *


class Register:
    user = ""
    psw = ""
    session = None

    WRONG_PSW = -3
    CONNECTION_ERROR = -2
    ERROR = -1

    site = "https://itsar.registrodiclasse.it"

    def __init__(self, user, psw):
        self.set_credential(user, psw)

    
    def set_credential(self, user, psw):
        self.user = user
        self.psw = psw
        self.session = Session()
        

    # Request lessons to geop and return a db containing the lessons processed by the function "extract_info()"
    def requestGeop(self, start_date="", end_date=""):
        
        start_date, end_date = self.correct_dates(start_date, end_date)
        lessons_url = f"/geopcfp2/json/fullcalendar_events_alunno.asp?Oggetto=idAlunno&idOggetto=2672&editable=false&z=1665853136739&start={start_date}&end={end_date}&_=1665853136261"

        #* Login
        try:
            if not self.can_login(self.user, self.psw):
                return self.WRONG_PSW
            
            #* Get lessons from the register
            MAX_ATTEMPTS = 3
            oldDB = ""
            url = self.site + lessons_url
            for attempt in range(MAX_ATTEMPTS):
                try:
                    res = self.session.get(url)

                except ConnectionError as e:
                    #// print(colored("Failed to connect. Check your internet connection", "red"))
                    if(attempt == MAX_ATTEMPTS-1):
                        return self.CONNECTION_ERROR

                except Exception as e:
                    #// print(colored(e, "red"))
                    if(attempt == MAX_ATTEMPTS-1):
                        return self.ERROR
                    continue
            
            oldDB = self.extract_info(res.json())
            return oldDB
                    
        except ConnectionError as e:
            print(colored("Failed to connect. Check your internet connection", "red"))
            return self.CONNECTION_ERROR
        except:
            print(colored("Something went wrong", "red"))

            return self.ERROR
            # cookies = session.cookies.get_dict()
            # write_to_file("cookies.json", cookies)

    # checks if all dates are set
    def correct_dates(self, start_date, end_date):

        if start_date == "":
            start_date = date.today()

        if end_date == "":
            end_date = start_date + timedelta(
				days=8
			)  # default is +7, but the register doesn't count the last day provided when fetching the db
        return start_date, end_date

    # take a json "info" and takes lessons info
    def extract_info(self, info):

        WEEKDAY = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
            "Sunday"
        ]

        lessons = [
        ]  # list of dictionaries. used to sort the lessons before displaying them

        for _lesson in info:
            lesson = {}
            lesson["id"] = int(_lesson["id"])
            lesson["subject"] = _lesson["tooltip"].split("Materia:")[1].split("<br>")[0].strip().replace("Ã", "à")
            lesson["teacher"] = _lesson["tooltip"].split("Docente:")[1].split("<br>")[0].strip()
            lesson["start"] = _lesson["start"].split("T")[1][:-3].strip()
            lesson["end"] = _lesson["end"].split("T")[1][:-3].strip()
            lesson["room"] = _lesson["tooltip"].split("Aula:")[1].split("<br>")[0].strip()
            lesson["day"] = _lesson["start"].split("T")[0].split("-")
            lesson["month"] = calendar.month_abbr[int(lesson["day"][1])]
            weekday_num = calendar.weekday(
                                        int(lesson["day"][0]),
                                        int(lesson["day"][1]),
                                        int(lesson["day"][2])
                                        )
            lesson["weekday"] = WEEKDAY[weekday_num]
            lesson["type"] = _lesson["ClasseEvento"].lower()

            lessons.append(lesson)

        return lessons
    

    # Check if the credentials are corrects
    def can_login(self, username, psw):
        login_url = "/geopcfp2/update/login.asp?1=1&ajax_target=DIVHidden&ajax_tipotarget=login"
        body = {'username': username, 'password': psw}

        url = self.site + login_url
        res = self.session.post(url, data=body)

        if res.status_code == 200:
            if "Username e password non validi" in res.text:  # valid password, ready to save cookies
                return False
            return True
        else:
            print(colored(str(res.status) + " " + res.reason, "red"))
        return False
