from tools.gmail_client import GmailClient


class GmailFetchSkill:
    def execute(self, max_results: int, account_id: str | None = None):
        return GmailClient(account_id=account_id).fetch_emails(max_results=max_results)

    def execute_full_sync(self, progress_callback=None, account_id: str | None = None):
        return GmailClient(account_id=account_id).fetch_full_sync(progress_callback=progress_callback)

    def execute_incremental_sync(self, history_id: str, progress_callback=None, account_id: str | None = None):
        return GmailClient(account_id=account_id).fetch_incremental_changes(
            history_id=history_id,
            progress_callback=progress_callback,
        )
