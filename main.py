from termcolor import colored
from bot import Bot
from utils import *


def main():

    # bot request
    bot = Bot()
    print(colored("[+] Bot started", "green"))

    try:
        bot.start()
    except KeyboardInterrupt:
        print(colored("[+] Bot terminated", "red"))
        bot.exit = True
        exit(0)
    


if __name__ == '__main__':
    main()
