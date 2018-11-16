import base64
import smtplib
from email.mime.text import MIMEText


def email(from_, to, msg, subject=''):
    """ Sends an email to the specified address. """

    gmail_user = 'my2.ism@gmail.com'
    with open('password') as file:
        gmail_password = base64.b64decode(file.readline()).decode('utf-8')

    if not isinstance(msg, MIMEText):
        msg = MIMEText(str(msg))
        msg['Suject'] = subject
    msg['From'] = from_
    msg['To'] = to

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to, msg.as_string())
    except smtplib.SMTPException as e:
        pass


def error_email(subject, error):
    email('ISM Error', 'haroldas.mackevicius@outlook.com', error, subject)