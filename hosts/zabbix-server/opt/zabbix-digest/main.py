#!/usr/bin/python3
from datetime import datetime as dt
from datetime import timedelta
import os

import dotenv
import psycopg
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from zabbix.api import ZabbixAPI


severity = ["not classified", "information", "warning", "average", "high", "disaster"]


def main(zapi):
    time_now = dt.now()
    time_yesterday = time_now - timedelta(days=1)
    timestamp_yesterday = int(time_yesterday.timestamp())
    time_now = str(time_now)[:-7]
    time_yesterday = str(time_yesterday)[:-7]
    # problems statistics
    problems_count = zapi.event.get(countOutput=True, time_from=timestamp_yesterday, value=1)
    resolved_problems_count = zapi.event.get(countOutput=True, time_from=timestamp_yesterday, value=0)
    unresolved_problems_content = ""
    unresolved_problems_content_template = " <li>{severity}: {name} - {timestamp};</li>"
    unresolved_problems = zapi.problem.get()
    for problem in unresolved_problems:
        unresolved_problems_content += unresolved_problems_content_template.format(
            severity=severity[int(problem['severity'])], name=problem['name'],
            timestamp=str(dt.fromtimestamp(int(problem['clock'])))
        )
    unresolved_problems_content = f"<ul>{unresolved_problems_content}</ul>"
    # autoregistration statistics
    with psycopg.connect(dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
                         host="localhost", password=os.getenv('DB_PASS')) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT host FROM autoreg_host WHERE registered_at >= timestamp '{time_yesterday}';")
            autoregistered_hosts = ", ".join([host[0] for host in cur.fetchall()])
    # mail sending
    content = f'''
        <h1>Report from {time_yesterday} to {time_now}:</h1>
        <h2>new problems: {problems_count};</h2> <h2>resolved problems: {resolved_problems_count};</h2>
        <h2>unresolved problems: {"</h2>" + unresolved_problems_content if unresolved_problems else "None;</h2>"}
        <h2>new autoregistered hosts: {autoregistered_hosts if autoregistered_hosts else "None"}.</h2>
    '''
    users = zapi.user.get(output="count", selectMedias=["sendto", "mediatypeid", "active"], mediatypeids="1")
    emails = []
    for user in users:
        for media in user['medias']:
            if media['mediatypeid'] == '1' and media['active'] == '0':
                emails.extend(media['sendto'])
    message = Mail(from_email="yoan.dzhelekarski@gmail.com", to_emails=emails,
                   subject="Daily Zabbix Digest", html_content=content)
    sender = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    response = sender.send(message)
    print(f"{response.status_code}: {response.body}")


if __name__ == '__main__':
    dotenv.load_dotenv()
    with ZabbixAPI(url=f"http://localhost:{os.getenv('ZB_PORT')}/api_jsonrpc.php",
                   user=os.getenv('ZB_USER'), password=os.getenv('ZB_PASS')) as zapi:
        main(zapi)
