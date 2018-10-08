import requests
from bs4 import BeautifulSoup
import json
import time
import sqlite3 as sql
import base64
import smtplib
from email.mime.text import MIMEText
import requests.exceptions as exceptions

import random_headers


def main():
    EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
    global settings
    with open('settings.json', 'r') as file:
        settings = json.loads(file.read())

    # Find the authentication token
    session = requests.Session()
    session.headers.update(random_headers.get_headers())
    resp = None
    while not resp:
        try:
            resp = session.get('https://my2.ism.lt/Account/Login')
        except EXCEPTIONS:
            wait_for_response()
    soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
    token = soup.find('input', {'name': '__RequestVerificationToken'})['value']

    # Get username and password
    conn = sql.connect('main.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    username, password = cursor.fetchone()
    password = base64.b64decode(password).decode('utf-8')

    # Create grades table
    cursor.execute('CREATE TABLE IF NOT EXISTS grades (username, unid, course, type, lecturer, assessment)')
    conn.commit()
    conn.close()

    # Login to the website
    data = {'Username': username,
            'Password': password,
            '__RequestVerificationToken': token}
    try:
        session.post('https://my2.ism.lt/Account/Login', data=data)
    except EXCEPTIONS:
        wait_for_response()

    # Constantly check for new grades
    while True:
        try:
            resp = session.get('https://my2.ism.lt/StudentGrades/StudentGradesWigets/LastGradesList')
            print(resp.status_code)
        except EXCEPTIONS:
            wait_for_response()

        soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
        if not soup.find('tr', {'class': 'lastGradeRow'}):
            print('no')
        current_grades = [i for i in extract_grades(soup)]

        # Check if there are new grades
        if len(current_grades) > len(get_old_grades(username)):
            new_grades = get_new_grades(current_grades, username)

            # Send email
            send_updates(new_grades, username)

            # Upload current grades to the database
            conn = sql.connect('main.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM grades')
            cursor.executemany('INSERT INTO grades VALUES (?, ?, ?, ?, ?, ?)', [[username] + list(i.values()) for i in current_grades])
            conn.commit()
            conn.close()

        time.sleep(settings['reload_interval'])

def extract_grades(soup):
    """ Parses the grades page source code. """

    for grade in soup.find_all('tr', {'class': 'lastGradeRow'}):
        grade = [i.text.strip() for i in grade.find_all('td')]
        yield {
            'unid': grade[1].replace(' ', '') + grade[2].replace(' ', ''),
            'course': grade[1],
            'type': grade[2],
            'lecturer': grade[3],
            'assessment': grade[4].split('\n')[0]
        }


def get_old_grades(username):
    """ Gets the grades from the database. """

    conn = sql.connect('main.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM grades WHERE username = ?", (username, ))
    grades_old = cursor.fetchall()
    conn.close()

    return grades_old


def get_new_grades(grades, username):
    """ Returns new grades, i.e. the difference between old grades and current grades. """

    return [grade for grade in grades if grade['unid'] not in [i[1] for i in get_old_grades(username)]]


def send_updates(grades, username):
    user_email = '{}@stud.ism.lt'.format(username)
    gmail_user = 'my2.ism@gmail.com'
    gmail_password = 'my2grades'

    if len(grades) == 1:
        grades = grades[0]

        email_text = "You got a grade of {grade} from {subject} {assignment}.".format(grade=grades['assessment'],
                                                                                      subject=grades['course'],
                                                                                      assignment=grades['type'])

        msg = MIMEText(email_text)
        msg['Subject'] = '{grade} from {subject}'.format(grade=grades['assessment'], subject=grades['course'])

    else:
        email_text = ''
        for grade in grades:
            grade_string = '{grade} from {subject} {assignment}'.format(grade=grade['assessment'], subject=grade['course'],
                                                                        assignment=grade['type'])

            email_text = '{}\n{}'.format(email_text, grade_string).strip()

        msg = MIMEText(email_text)
        msg['Subject'] = 'New Grades'

    msg['From'] = 'ISM Grades'
    msg['To'] = user_email
    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, user_email, msg.as_string())
    except Exception as e:
        print(e)


def wait_for_response():
    print('wait')
    while True:
        try:
            resp = requests.get('https://my2.ism.lt/Account/Login')
        except Exception:
            print('waiting')
            time.sleep(settings['connection_check_interval'])
        else:
            break

if __name__ == '__main__':
    main()
