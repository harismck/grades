from bs4 import BeautifulSoup
import json
import time
import sqlite3 as sql
import base64
from email.mime.text import MIMEText
import logging
from datetime import datetime
from datetime import timedelta
import os

import send_email
from My2Session import My2Session

GRADES_URL = 'https://my2.ism.lt/StudentGrades/StudentGradesWidgets/LastGradesList'


def main():
    # Set up logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler('logs.log')
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

    # Load settings
    with open('settings.json', 'r') as file:
        settings = json.loads(file.read())
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    logger.info("Starting the script.")

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

    # Get a session object
    session = My2Session(username, password)
    session.login()

    # Constantly check for new grades
    logger.info('Checking for grades every {} seconds.'.format(settings['reload_interval']))
    while True:
        resp = session.get(GRADES_URL)
        if resp.status_code != 200:
            # Re-initialize the session if status code is 500
            if resp.status_code == 500:
                logger.warning("500 status code, restarting session. ")
                session = My2Session(username, password)
                session.login()
                continue
            else:
                logger.warning("{} status code, quitting.".format(resp.status_code))
                exit(1)


        # Check if there are new grades
        soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
        current_grades = [i for i in extract_grades(soup)]
        if len(current_grades) > len(get_old_grades(username)):
            logger.info("Found new grades")
            new_grades = get_new_grades(current_grades, username)

            # Send email
            send_email.email('ISM Grades', '{}@stud.ism.lt'.format(username), grades_to_text(new_grades))
            logger.info('Email sent')

            # Upload new grades to the database
            conn = sql.connect('main.db')
            cursor = conn.cursor()
            cursor.execute('DELETE FROM grades')
            cursor.executemany('INSERT INTO grades VALUES (?, ?, ?, ?, ?, ?)',
                               [[username] + list(i.values()) for i in current_grades])
            conn.commit()
            conn.close()

        # Wait
        time.sleep(settings['reload_interval'])
        if datetime.now().hour == settings['night_hour']:
            logger.info('Resting until {}'.format(datetime.now() + timedelta(hours=settings['night_duration'])))
            time.sleep(settings['night_duration']*60*60)
            logger.info('Continuing.')


def extract_grades(soup):
    """ Parses the grades' page source code. """

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


def grades_to_text(grades):
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


if __name__ == '__main__':
    main()
