from twitch

class Client:
    def __init__(self):
        pass

    def build_client(self, client_id: str, client_secret: str) -> ClientApp:
        pass

    def resolve_broadcaster_ids(self, client, logins) -> dict[str, str]:
        pass

    def get_conduit(self)

