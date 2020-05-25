from opsdroid.matchers import match_regex, \
        match_parse
from opsdroid.skill import Skill
from opsdroid.logging import logging
from azure.devops.connection import Connection
from azure.devops.exceptions import AzureDevOpsServiceError
from msrest.authentication import \
        BasicTokenAuthentication, \
        BasicAuthentication
from pprint import pprint
import regex
import commonmark
import datetime

from voluptuous import Required

CONFIG_SCHEMA = {
    Required("username"): str,
    Required("pat"): str,
    Required("url"): str,
}


class MSDevelop(Skill):
    def __init__(self, opsdroid, config):
        super(MSDevelop, self).__init__(opsdroid, config)

        # configure logging
        logging.getLogger("azure").setLevel(logging.DEBUG)
        logging.info("ms-develop started ...")

        self.statuslog = []
        self.status_something_wrong = 1

        # configure connection to devops server
        self.credential = BasicAuthentication(self.config['username'], self.config['pat'])
        self.connection = Connection(base_url=self.config['url'], creds=self.credential)
        self.core = self.connection.clients.get_core_client();

        if self.core:
            self.ase(f"connection established to {self.config['url']}")
        else:
            self.ase(f"no connection to {self.config['url']} ... No communication to devops possible.")
            return

        # get project id
        found = False
        projectlist = self.core.get_projects()
        if len(projectlist.value) > 0:
            for project in projectlist.value:
                if project.name == self.config['projectname']:
                    found = True
                    self.projectid = project.id
                    self.ase(f"Project found (id: {self.projectid})")

        if not found:
            self.ase(f"Project '{self.config['projectname']}' not found")
            return

        # get WIT client
        self.wit = self.connection.clients.get_work_item_tracking_client()


    # Add status entry
    def ase(self, text, failure=0):
        self.statuslog += [f"{datetime.datetime.now()}: {text}"]
        self.status_something_wrong |= failure
        return


    @match_parse(r'bot, status please')
    async def bot_status(self, opsdroid, config, message):
        text = ""

        text += f"@{message.user}: Statusreport\n\n"
        text += f"**Healthstate**: {'OK' if self.status_something_wrong else 'Sick'}\n\n"
        text += f"~~~\n"

        for entry in self.statuslog:
            text += f"- {entry}\n"

        text += f"~~~\n"

        text = commonmark.commonmark(text)

        await message.respond(text)


    # We are serach only for one occurent and analyse in this task if it
    # occures more than one time
    @match_regex(r'#(?P<wit>\d+)', matching_condition="match")
    async def wit_parser_function(self, apsdroid, config, message):
        c = message.connector
        text = f"@{message.user}: I have found follwing WITs:\n"

        notfound = ""

        for i in regex.finditer(r'#(?P<wit>\d+)', message.text):
            ids = i.group(0)[1:]
            try:
                value = self.wit.get_work_item(id=ids, project=self.projectid)
            except AzureDevOpsServiceError:
                notfound += f"{ids}, "
                continue

            text += f"* [link]({value.url}) - {ids} - {value.fields['System.Title']}\n"


        notfound = notfound[:-2]

        if len(notfound) > 0:
            text += f"\n"
            text += f"Following WITs not found: {notfound}"
            text += f"\n"

        text = commonmark.commonmark(text)
        await message.respond(text)


