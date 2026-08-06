from pathlib import Path


class ConduitStore: 
    def __init__(self, path: Path):
        self._path = path

    def save_id(self, conduit_id):
        self._path.write_text(conduit_id)

    def read_id(self):
        return self._path.read_text().strip()