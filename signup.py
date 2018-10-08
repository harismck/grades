import sqlite3 as sql
from getpass import getpass
import time
import base64

'''Sign up for the ISM grades tool.'''

def main():
    print("Here you can sign up for e-mail notifications of new grades.")
    username = ''
    while len(username) != 6 and not username.isdigit():
        print('Enter My2 username (six digits): ', end='')
        username = input()

    password = ''
    while len(password) < 8:
        password = getpass('Enter My2 password: ')

    conn = sql.connect('main.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (username, password)')
    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                   (username, base64.b64encode(password.encode('utf-8'))))
    conn.commit()
    conn.close()

    print("Thank you!")
    time.sleep(3)



if __name__ == '__main__':
    main()