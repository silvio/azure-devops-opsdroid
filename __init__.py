from azure.devops.connection import \
        Connection
from azure.devops.exceptions import \
        AzureDevOpsServiceError
from msrest.authentication import \
        BasicTokenAuthentication, \
        BasicAuthentication
from opsdroid.events import \
        UserInvite, \
        JoinRoom
from opsdroid.logging import \
        logging
from opsdroid.matchers import \
        match_regex, \
        match_event, \
        match_parse
from opsdroid.skill import \
        Skill
from pprint import \
        pprint
from voluptuous import\
        Required

import regex
import commonmark
import datetime
import git

logger = logging.getLogger(__name__)

CONFIG_SCHEMA = {
    Required("username"): str,
    Required("pat"): str,
    Required("url"): str,
    Required('projectname'): str,
    'join_when_invited': bool,
}


class MSDevelop(Skill):
    def __init__(self, opsdroid, config):
        super(MSDevelop, self).__init__(opsdroid, config)

        self.statuslog = []
        self.status_something_wrong = 1

        # configure logging
        self.ase("ms-develop started ...")

        self.version = None
        try:
            self.version = git.Repo(path=__path__[0], search_parent_directories=True).git.describe('--always', '--tags')
        except:
            self.version = "unknown"
        self.ase(f"Version: {self.version}")


        # configure connection to devops server
        self.credential = BasicAuthentication(config.get('username'), config.get('pat'))
        self.connection = Connection(base_url=config.get('url'), creds=self.credential)
        self.core = self.connection.clients.get_core_client();

        if self.core:
            self.ase(f"connection established to {config.get('url')}")
        else:
            self.ase(f"no connection to {config.get('url')} ... No communication to devops possible.")
            return

        # get project id
        found = False
        projectlist = self.core.get_projects()
        if len(projectlist.value) > 0:
            for project in projectlist.value:
                if project.name == config.get('projectname'):
                    found = True
                    self.projectid = project.id
                    self.ase(f"Project found (id: {self.projectid})")

        if not found:
            self.ase(f"Project '{config.get('projectname')}' not found")
            return

        # get WIT client
        self.wit = self.connection.clients.get_work_item_tracking_client()

        self.join_when_invited = config.get("join_when_invited", False)
        self.ase(f"The bot can join: {self.join_when_invited}")


    # Add status entry
    def ase(self, text, failure=0):
        logger.debug(f"statuslog: {text}")
        self.statuslog += [f"{datetime.datetime.now()}: {text}"]
        self.status_something_wrong |= failure
        return


    @match_event(UserInvite)
    async def on_invite_to_room(self, invite):
        if self.join_when_invited:
            await invite.respond(JoinRoom())

    @match_parse(r'bot, status please')
    async def bot_status(self, opsdroid, config, message):
        text = ""

        text += f"**opsdroid** bot for azure-devops server\n\n"
        text += f"**Sources**: `https://github.com/silvio/azure-devops-opsdroid.git` (**Version**: {self.version})\n\n"

        text += f"@{message.user}: Statusreport\n\n"
        text += f"**Healthstate**: {'OK' if self.status_something_wrong else 'Sick'}\n\n"
        text += f"**Joinable**: {self.join_when_invited}\n\n"
        text += f"~~~\n"

        for entry in self.statuslog:
            text += f"- {entry}\n"

        text += f"~~~\n"

        text = commonmark.commonmark(text)

        await message.respond(text)


    # We are serach only for one occurent and analyse in this task if it
    # occures more than one time
    @match_regex(r'(?s).*#(\d+).*', matching_condition="match")
    async def wit_parser_function(self, apsdroid, config, message):
        c = message.connector
        text = f"@{message.user}: I have found follwing WITs:\n"

        notfound = ""

        for i in regex.finditer(r'#(?P<wit>\d+)', message.text, regex.MULTILINE):
            ids = i.group(0)[1:]
            try:
                value = self.wit.get_work_item(id=ids, project=self.projectid)
            except Exception as e:
                notfound += f"[{ids}](http:// '{e}'), "
                continue

            text += f"* [link]({value._links.additional_properties['html']['href']}) - {ids} - {value.fields['System.Title']}\n"


        notfound = notfound[:-2]

        if len(notfound) > 0:
            text += f"\n"
            text += f"Following WITs not found: {notfound}"
            text += f"\n"

        text = commonmark.commonmark(text)
        await message.respond(text)


