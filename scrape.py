import requests
from bs4 import BeautifulSoup
import json
import time
import sqlite3 as sql
import base64
import smtplib
from email.mime.text import MIMEText
import logging
import random_headers

EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
LOGIN = 'https://my2.ism.lt/Account/Login'

# Load settings
with open('settings.json', 'r') as file:
    settings = json.loads(file.read())

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('logs.log')
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)


def main():
    logger.info("Starting the script.")

    # Initialize a requests Session
    session = requests.Session()
    session.headers.update(random_headers.get_headers())

    # Find the authentication token
    while True:
        try:
            resp = session.get(LOGIN)
            if resp.status_code == 200:
                break
            else:
                send_error_email('Non-200 Status Code', resp.status_code)
                logger.error("NON-200 STATUS CODE: {}".format(resp.status_code))
                exit(1)
        except EXCEPTIONS as e:
            send_error_email('Initial GET Error [Waiting]', e)
            logger.warning(e)
            if not wait_for_response(LOGIN):
                send_error_email('Initial GET Error [Quitting]', e)
                logger.error(e)
                exit(1)
    soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
    token = soup.find('input', {'name': '__RequestVerificationToken'})['value']
    logger.info('Authentication token found')

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
        resp = session.post(LOGIN, data=data)
    except EXCEPTIONS as e:
        send_error_email('Initial POST Error [Waiting]', e)
        logger.warning(e)
        if not wait_for_response(LOGIN):
            send_error_email('Initial POST Error [Quitting]', e)
            logger.error(e)
            exit(1)
    finally:
        logger.info('Successfully logged in')

    # Constantly check for new grades
    logger.info('Checking for grades every {} seconds...'.format(settings['reload_interval']))
    while True:
        try:
            resp = session.get('https://my2.ism.lt/StudentGrades/StudentGradesWidgets/LastGradesList')
            if resp.status_code != 200:
                logger.warning('NON-200 STATUS CODE {}'.format(resp.status_code))
                send_error_email('NON-200 Grades Reload [Quitting]', resp.status_code)
                exit(1)
        except EXCEPTIONS as e:
            send_error_email('Grades Reload Error [Waiting]', e)
            logger.warning(e)
            if not wait_for_response(LOGIN):
                send_error_email('Grades Reload Error [Quitting]', e)
                logger.error(e)
                exit(1)

        soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
        current_grades = [i for i in extract_grades(soup)]

        # Check if there are new grades
        if len(current_grades) > len(get_old_grades(username)):
            logger.info("Found new grades")
            new_grades = get_new_grades(current_grades, username)

            # Send email
            send_email('ISM Grades', '{}@stud.ism.lt'.format(username), grades_body(new_grades))
            logger.info('Email sent')

            # Upload current grades to the database
            conn = sql.connect('main.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM grades')
            cursor.executemany('INSERT INTO grades VALUES (?, ?, ?, ?, ?, ?)',
                               [[username] + list(i.values()) for i in current_grades])
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
    cursor.execute("SELECT * FROM grades WHERE username = ?", (username,))
    grades_old = cursor.fetchall()
    conn.close()

    return grades_old


def get_new_grades(grades, username):
    """ Returns new grades, i.e. the difference between old grades and current grades. """

    return [grade for grade in grades if grade['unid'] not in [i[1] for i in get_old_grades(username)]]


def send_email(from_, to, msg, subject=''):
    """ Sends an email to the specified address. """

    gmail_user = 'my2.ism@gmail.com'
    with open('password') as file:
        gmail_password = base64.b64decode(file.readline()).decode('utf-8')

    if not isinstance(msg, MIMEText):
        msg = MIMEText(msg)
        msg['Suject'] = subject
    msg['From'] = from_
    msg['To'] = to

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to, msg.as_string())
    except Exception as e:
        logger.error(e)


def send_error_email(subject, error):
    send_email('ISM Error', 'haroldas.mackevicius@outlook.com', error, subject)


def grades_body(grades):
    """ Takes an array with new grades as input and returns a MIMEText object. """

    if len(grades) == 1:
        subject = '{grade} from {subject}'.format(grade=grades[0]['assessment'], subject=grades[0]['course'])
        body = "You got a grade of {grade} from {subject} {assignment}.".format(grade=grades[0]['assessment'],
                                                                                subject=grades[0]['course'],
                                                                                assignment=grades[0]['type'])
    else:
        subject = 'New Grades'
        body = ''
        for grade in grades:
            body = '{}\n{}'.format(body, '{grade} from {subject} {assignment}'.format(grade=grade['assessment'],
                                                                                      subject=grade['course'],
                                                                                      assignment=grade['type'])
                                   ).strip()

    msg = MIMEText(body)
    msg['Subject'] = subject

    return msg


def wait_for_response(url):
    """ Makes requests to a given url until it starts to respond. """

    while True:
        try:
            requests.get(url)
        except EXCEPTIONS:
            time.sleep(settings['connection_check_interval'])
        except Exception as e:
            return False
        else:
            return True


if __name__ == '__main__':
    main()
