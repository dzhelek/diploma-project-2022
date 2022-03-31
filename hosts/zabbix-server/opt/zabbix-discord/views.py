import datetime
from datetime import datetime as dt
import os

from aiozabbix import ZabbixAPI
from dateutil import parser
from disnake import ui
from disnake import ButtonStyle, SelectOption, TextInputStyle
from disnake.ui import Modal, Select, TextInput, View
import dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

dotenv.load_dotenv()
zapi = ZabbixAPI(f"http://localhost:{os.getenv('ZB_PORT')}/api_jsonrpc.php")


async def login():
    await zapi.login(os.getenv('ZB_USER'), os.getenv('ZB_PASS'))


class HostSelect(Select):
    def __init__(self, hosts):
        for host in hosts:
            host['status'] = f"{'✅' if host['status'] == '0' else '❌'}"
            host['flags'] = f"{'discovered host' if host['flags'] == '4' else 'plain host'}"
        self.hosts = {host['host']: host for host in hosts}
        super().__init__(
            options=[SelectOption(label=host['host'], description=host['name'], emoji=host['status']) for host in hosts],
            placeholder="List of all hosts:"
        )

    async def callback(self, inter):
        host = self.hosts[inter.values[0]]
        msg = f"{host['status']} {host['host']}"
        if host['name'] != host['host']:
            msg += f" ({host['name']})"
        msg += f" - {host['flags']}"
        if host['description']:
            msg += f": \n{host['description']}"
        if host['error']:
            msg += f"\n❗{host['error']}"
        await inter.response.send_message(msg)


class ProblemSelect(Select):
    def __init__(self, problems, timestamp):
        self.severity = ['not classified', 'information', 'warning', 'average', 'high', 'disaster']
        self.severity_emoji = ['❔', 'ℹ️', '❕', '❗', '⚠️', '🛑']
        self.problems = {problem['eventid']: problem for problem in problems}
        self.timestamp = timestamp
        super().__init__(
            options=[SelectOption(label=problem['eventid'], description=problem['name'],
                                  emoji=self.severity_emoji[int(problem['severity'])]) for problem in problems],
            placeholder="List of problems:"
        )

    async def callback(self, inter):
        problem = self.problems[inter.values[0]]
        msg = f"{self.severity_emoji[int(problem['severity'])]}{self.severity[int(problem['severity'])]}"
        msg += f": {problem['name']}"
        if problem['opdata']:
            msg += f" ({problem['opdata']})"
        await login()
        resolved = await zapi.event.get(output=['name'], value=0,
                                        time_from=self.timestamp, objectids=problem['objectid'])
        resolved = [problem['name'] for problem in resolved]
        resolved = any(problem['name'] == name for name in resolved)
        if resolved:
            msg += f" - resolved ✅"
        else:
            msg += f" - not resolved yet ❌"
        await inter.response.send_message(msg)


class DateModal(Modal):
    def __init__(self, time_till, time_from):
        components = [
            TextInput(label="from time", placeholder=time_from, custom_id="time_from",
                      style=TextInputStyle.short, required=False),
            TextInput(label="to time", placeholder=time_till, custom_id="time_till",
                      style=TextInputStyle.short, required=False),
        ]
        super().__init__(title="Change timestamp", custom_id="datemodal", components=components)

    async def callback(self, inter):
        view = await ProblemsView.create(time_from=inter.text_values['time_from'],
                                         time_till=inter.text_values['time_till'])
        print(inter.text_values)
        time = f"Problems from {view.time_from} to {view.time_till}"
        if view.problems:
            await inter.response.send_message(time, view=view)
        else:
            await inter.response.send_message(time + ": None")


class EmailModal(Modal):
    def __init__(self, content):
        self.content = content
        components = [TextInput(label="email", placeholder="Enter your email address",
                      custom_id="email", style=TextInputStyle.short)]
        super().__init__(title="Enter email", custom_id="emailmodal", components=components)

    async def callback(self, inter):
        emails = inter.text_values['email']
        print(emails)
        message = Mail(from_email=os.getenv('FROM_EMAIL'), to_emails=emails,
                       subject='Custom Zabbix Report', html_content=self.content)
        sender = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        response = sender.send(message)
        if response.status_code == 202:
            await inter.response.send_message(f'Successfully sent to {emails}')


class ProblemsView(View):
    @classmethod
    async def create(cls, time_from=None, time_till=None):
        self = cls()
        if time_till:
            time_till = parser.parse(time_till)
        else:
            time_till = dt.now()
        if time_from:
            time_from = parser.parse(time_from)
        else:
            time_from = time_till - datetime.timedelta(days=1)
        timestamp_from = int(time_from.timestamp())
        timestamp_till = int(time_till.timestamp())
        self.time_till = str(time_till)
        self.time_from = str(time_from)
        await login()
        self.problems = await zapi.event.get(value=1, time_from=timestamp_from, time_till=timestamp_till,
                                             output=['eventid', 'name', 'objectid', 'severity', 'opdata'])
        self.add_item(ProblemSelect(self.problems, timestamp_from))
        return self

    @ui.button(label="Change timestamp", style=ButtonStyle.grey)
    async def confirm(self, button, inter):
        modal = DateModal(self.time_till, self.time_from)
        await inter.response.send_modal(modal)

    @ui.button(label="Send over email", style=ButtonStyle.grey)
    async def send(self, button, inter):
        content = f"<h1>Problems from {self.time_from} to {self.time_till}</h1>"
        content += f"<ul>{''.join('<li>' + problem['name'] + '</li>' for problem in self.problems)}</ul>"
        modal = EmailModal(content)
        await inter.response.send_modal(modal)


class HostsView(View):
    @classmethod
    async def create(cls):
        self = cls()
        await login()
        hosts = await zapi.host.get(output=['host', 'name', 'status', 'description', 'error', 'flags'])
        self.add_item(HostSelect(hosts))
        return self
