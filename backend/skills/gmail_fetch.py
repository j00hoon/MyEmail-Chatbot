from tools.gmail_client import GmailClient


class GmailFetchSkill:
    def execute(self, max_results: int):
        return GmailClient().fetch_emails(max_results=max_results)
