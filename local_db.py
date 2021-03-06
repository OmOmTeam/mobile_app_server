"""
Local database interface for server application.
:author: Denis Chernikov
"""

import atexit
import datetime
import postgresql
import secrets

from local_config import configs

POSTGRES_PASS = configs['POSTGRES_PASS']
DB_NAME = configs['DB_NAME']
USER_NAME = configs['USER_NAME']
USER_PASS = configs['USER_PASS']

DB_CONN = None

TTL = datetime.timedelta(hours=12)


class LocalDBQueryFailure(Exception):
    """
    Exception for cases of failed local database query try.
    """
    def __init__(self, message):
        """
        Initialize local database query failure exception with given content.
        :param message: Message to store in this exception
        """
        super(LocalDBQueryFailure, self).__init__(message)
        self.message = message

    def __str__(self):
        return self.message


def configure_db():
    """
    Initialize server's PostgreSQL database from the scratch using configuration data.
    """
    global DB_CONN
    try:
        DB_CONN = postgresql.open(
            'pq://{}:{}@localhost:5432/{}'.format(USER_NAME, USER_PASS, DB_NAME)
        )
    except postgresql.exceptions.ClientCannotConnectError:
        print('Database is unreachable! Trying to initialize it from scratch...')
        try:
            with postgresql.open(
                'pq://{}:{}@localhost:5432'.format('postgres', POSTGRES_PASS)
            ) as db:
                db.execute(
                    'DROP USER IF EXISTS {0};'
                    "CREATE USER {0} WITH password '{1}';"
                    .format(USER_NAME, USER_PASS)
                )
                db.execute(
                    'DROP DATABASE IF EXISTS {0};'
                    .format(DB_NAME)
                )
                db.execute(
                    'CREATE DATABASE {0} WITH OWNER = {1};'
                    .format(DB_NAME, USER_NAME)
                )
        except postgresql.exceptions.ClientCannotConnectError:
            print(
                'Unable to create database!\n'
                'Check if PostgreSQL is running and configurations are correct\n'
                'Terminating application...'
            )
            exit(1)

        with postgresql.open(
            'pq://{}:{}@localhost:5432/{}'.format(USER_NAME, USER_PASS, DB_NAME)
        ) as db:
            db.execute(
                'CREATE TABLE sessions ('
                '  id SERIAL PRIMARY KEY,'
                '  token CHAR(64),'
                '  login CHAR(64),'
                '  role_id INTEGER,'
                '  expires TIMESTAMP(0)'
                ');'
            )
        DB_CONN = postgresql.open(
            'pq://{}:{}@localhost:5432/{}'.format(USER_NAME, USER_PASS, DB_NAME)
        )


def _generate_token():
    """
    For local use.
    Generate almost unique session token.
    NOTE: collision is very improbable, but still may occur.
    :return: String with almost unique token value
    """
    return secrets.token_hex(32)  # TODO implement own


def store_user_auth(login, role_id):
    """
    Store authentication data for a new session and emmit new token for it.
    :param login: Login used for authentication
    :param role_id: `role_id` associated with given user
    :return: New token entry to be used within new session
    """
    assert DB_CONN
    token = _generate_token()
    expires = datetime.datetime.now() + TTL
    req = DB_CONN.prepare(
        'INSERT INTO sessions (token, login, role_id, expires) VALUES ($1, $2, $3, $4);'
    )
    req(token, login, role_id, expires)
    return token


def is_valid_token(token):
    """
    Is given token - valid one?
    :param token: Token to check validity of
    :return: `true` - it is valid and up-to-date, `false` - otherwise
    """
    assert DB_CONN
    req = DB_CONN.prepare(
        'SELECT exists ('
        '  SELECT 1 FROM sessions'
        '  WHERE token = $1 AND expires > current_timestamp LIMIT 1'
        ');'
    )
    res = req(token)
    # TODO more efficient database garbage collection
    DB_CONN.execute('DELETE FROM sessions WHERE expires <= current_timestamp;')
    return res[0][0]


def get_login_by_token(token):
    """
    Get `login` associated with a given session token.
    :param token: Token to search user by
    :return: `login` associated with a given token
    """
    assert DB_CONN
    req = DB_CONN.prepare(
        'SELECT login FROM sessions WHERE token = $1 LIMIT 1;'
    )
    res = req(token)
    return res[0][0].strip()


def get_role_id_by_token(token):
    """
    Get `role_id` associated with a given session token.
    :param token: Token to search user by
    :return: `role_id` associated with a given token
    """
    assert DB_CONN
    req = DB_CONN.prepare(
        'SELECT role_id FROM sessions WHERE token = $1 LIMIT 1;'
    )
    res = req(token)
    return res[0][0]


def remove_token(token):
    """
    Close session associated with a given token and remove the corresponding database record.
    :param token: Token to close session for
    """
    assert DB_CONN
    req = DB_CONN.prepare(
        'DELETE FROM sessions WHERE token = $1;'
    )
    req(token)


def _close_db():
    """
    For local use.
    Close database connection stored globally.
    """
    DB_CONN.close()


atexit.register(_close_db)
