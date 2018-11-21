import requests
import random_headers
from bs4 import BeautifulSoup
import logging
import time


class My2Session(requests.Session):
    """
    A modified requests Session object with:
    Default signing into the My2 website;
    Catching of HTTP and requests errors;
    Retrying for a specified number of times;
    Logging.
    """

    def __init__(self, username, password):
        """
        Returns an instance of My2Session after logging into the My2 website using username and password provided.
        The default number of retries is 3. Use set_max_retries(retries) to modify.
        :param username:
        :param password:
        """
        # Logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler('logs.log')
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.username = username
        self.password = password
        self.login_url = 'https://my2.ism.lt/Account/Login'
        self.max_tries = 3
        self.retry_interval = 600

        super().__init__()
        self.headers.update(random_headers.get_headers())

    def reset(self):
        self.cookies.clear()

    def get(self, url, **kwargs):
        while True:
            try:
                resp = super().get(url, **kwargs)
                if resp.status_code == 200:
                    return resp
                self.logger.error("Non-200 status code during GET: " + str(resp.status_code))
                return resp
            except requests.RequestException as e:
                self.logger.warning("Requests exception during GET: " + str(e))
                return self.wait_for_response(self.login_url)

    def retry_config(self, max_tries, retry_interval):
        self.max_tries = max_tries
        self.retry_interval = retry_interval

    def login(self):
        """
        Logs the session into the My2 website.
        :return: None
        """

        resp = self.get(self.login_url)
        if not resp:
            self.logger.error("Could not reach the log in URL. ")
            exit(1)

        # Find the login token
        soup = BeautifulSoup(resp.content.decode('utf-8'), 'html.parser')
        token = soup.find('input', {'name': '__RequestVerificationToken'})['value']

        # Log in
        self.post(self.login_url, {'Username': self.username,
                                   'Password': self.password,
                                   '__RequestVerificationToken': token})
        self.logger.info("Logged In")

    def wait_for_response(self, url):
        """ Makes requests to a given url until it responds with a 200 OK status code. """

        tries = 0
        while True:
            try:
                self.get(url)
                tries += 1
            except requests.RequestException:
                if tries < self.max_tries:
                    time.sleep(self.retry_interval)
                else:
                    self.logger.error("Exceeded retries, quitting.")
                    exit(1)
            except Exception as e:
                self.logger.error("Error when retrying, quitting: " + str(e))
                exit(1)
            else:
                return True
